import base64
from datetime import datetime, timezone

from bson import ObjectId

from app.prompts.assess import build_group_prompt
from app.schemas.rubric import QuestionType
from app.services import gemini
from app.services import rubric as rubric_service
from app.services.db import submissions
from app.prompts.assess import build_gate_prompt, build_synthesis_prompt  # add to existing imports


# ---- grouping ----------------------------------------------------------

def _group_key(source_photos: list[str]) -> str:
    """Canonical group id derived from a question's source photos."""
    s = set(source_photos)
    if s & {"upstream", "downstream"} and not (s & {"context", "biodiversity"}):
        return "channel"
    if s & {"biodiversity"}:
        return "margins"
    if s & {"context"}:
        return "pressures" if not (s & {"biodiversity"}) else "margins"
    return "channel"


def build_groups():
    """{group_key: [Question]} for AI-enabled questions, from the live rubric."""
    groups: dict[str, list] = {}
    for q in rubric_service.get_rubric():
        if not q.ai_enabled:
            continue
        groups.setdefault(_group_key(q.source_photos), []).append(q)
    return groups


# group -> which media labels it needs
_GROUP_PHOTOS = {
    "channel": ["upstream", "downstream"],
    "pressures": ["context", "downstream"],
    "margins": ["context", "biodiversity"],
}


# ---- creation ----------------------------------------------------------

def create_submission(payload, username: str | None) -> dict:
    """Persist immediately with AI questions seeded 'pending', return the doc."""
    answers = {k: v.model_dump() for k, v in payload.answers.items()}

    # seed every AI-enabled question as a pending placeholder
    for q in rubric_service.get_rubric():
        if q.ai_enabled and q.key not in answers:
            answers[q.key] = {
                "value": None, "side": None, "source": "ai",
                "ai_status": "pending", "ai_suggestion": None,
                "ai_confidence": None, "ai_reason": None, "needs_human": False,
            }

    doc = {
        "created_at": datetime.now(timezone.utc),
        "username": username,
        "status": "processing",
        "site": payload.site.model_dump(),
        "answers": answers,
        "water_height": payload.water_height,
        "feelings": payload.feelings.model_dump() if payload.feelings else None,
        "media": payload.media,
        "photo_mode": payload.photo_mode,
        "overall": None,
    }
    res = submissions.insert_one(doc)
    return _to_public(submissions.find_one({"_id": res.inserted_id}))


# ---- the background job -----------------------------------------------

def _data_uri_to_part(data_uri: str) -> tuple[bytes, str]:
    """'data:image/jpeg;base64,XXXX' -> (bytes, mime)."""
    header, b64 = data_uri.split(",", 1)
    mime = header.split(";")[0].removeprefix("data:") or "image/jpeg"
    return base64.b64decode(b64), mime

def _gate_photos(media: dict) -> dict:
    """One cheap call. Returns {label: {ok: bool, reason: str}} for provided photos."""
    labeled = []
    labels = []
    for label, uri in media.items():
        if not uri:
            continue
        if label == "video": continue
        data, mime = _data_uri_to_part(uri)
        labeled.append((label, data, mime))
        labels.append(label)

    if not labeled:
        return {}

    try:
        prompt = build_gate_prompt(labels)
        data = gemini.json_from_labeled_images(labeled, prompt)
        out = {}
        for entry in data.get("photos", []):
            if isinstance(entry, dict) and entry.get("label") in media:
                out[entry["label"]] = {
                    "ok": bool(entry.get("ok", False)),
                    "reason": str(entry.get("reason", "")),
                }
        # any photo the model forgot to rate → treat as ok (lenient default)
        for label in labels:
            out.setdefault(label, {"ok": True, "reason": ""})
        return out
    except Exception as e:
        # if the gate itself errors, don't block the user — pass everything through
        return {label: {"ok": True, "reason": f"gate skipped: {e}"} for label in labels}

def apply_review(submission_id: str, patch) -> dict:
    oid = ObjectId(submission_id)
    doc = submissions.find_one({"_id": oid})
    if not doc:
        return None

    updates = {}

    if patch.title is not None:
        updates["title"] = patch.title

    if patch.feelings is not None:
        updates["feelings"] = patch.feelings.model_dump()

    if patch.overall is not None:
        updates["overall"] = patch.overall.model_dump()

    # merge confirmed answers, preserving the AI audit trail
    if patch.answers:
        for key, decision in patch.answers.items():
            existing = doc.get("answers", {}).get(key, {})
            new_value = decision.get("value") if isinstance(decision, dict) else decision
            updates[f"answers.{key}.value"] = new_value
            updates[f"answers.{key}.source"] = "human"
            updates[f"answers.{key}.needs_human"] = False
            # ai_suggestion / ai_reason / ai_confidence are left intact

    if patch.finalize:
        if doc.get("status") in ("processing", "needs_photo_review", "needs_retake"):
            raise ValueError("Cannot finalize before the assessment has been analyzed.")
        updates["status"] = "finalized"
        updates["finalized_at"] = datetime.now(timezone.utc)

        # generate the synthesis over the human-confirmed answers (merged view)
        merged = dict(doc.get("answers", {}))
        if patch.answers:
            for k, decision in patch.answers.items():
                val = decision.get("value") if isinstance(decision, dict) else decision
                merged.setdefault(k, {})["value"] = val
        overall_val = (patch.overall.value if patch.overall else
                       (doc.get("overall") or {}).get("value"))

        try:
            summary_text = _summarize_answers(merged)
            if not summary_text.strip():
                updates["synthesis"] = (
                    "This assessment has no confirmed findings yet — the photos could not be "
                    "analysed, so there is nothing to summarise."
                )
            else:
                site_name = (doc.get("site") or {}).get("name") or (doc.get("site") or {}).get("code") or "this stream"
                synthesis = gemini.text_from_prompt(
                    build_synthesis_prompt(site_name, overall_val, summary_text)
                )
                updates["synthesis"] = synthesis
        except Exception:
            updates["synthesis"] = None   # non-fatal; finalize still succeeds

    if updates:
        submissions.update_one({"_id": oid}, {"$set": updates})

    return get_submission(submission_id)

def _suggest_overall_for(oid) -> None:
    """Populate overall.ai_suggested from the AI's confirmed-so-far answers."""
    doc = submissions.find_one({"_id": oid})
    if not doc or doc.get("status") in ("needs_retake", "needs_photo_review"):
        return

    # build a compact answer map for the prompt: {question_key: value}
    answers = {
        k: a.get("value")
        for k, a in doc.get("answers", {}).items()
        if a.get("value") is not None and a.get("ai_status") != "skipped"
    }
    if not answers:
        return

    try:
        result = suggest_overall(answers)   # existing function -> OverallResponse
        submissions.update_one(
            {"_id": oid},
            {"$set": {"overall": {"value": None, "ai_suggested": result.value,
                                  "ai_reason": result.reason, "source": "ai"}}},
        )
    except Exception:
        # non-fatal: review just won't show a suggestion
        pass


def run_assessment(submission_id: str) -> None:
    """Run each topic group, writing results incrementally. Safe to re-run."""
    oid = ObjectId(submission_id)
    doc = submissions.find_one({"_id": oid})
    if not doc:
        return

    media = dict(doc.get("media", {}))

    # --- gate: run once, unless we're resuming a photo-review decision ---
    if doc.get("status") == "needs_photo_review":
        # user chose "Run with usable photos": drop gate-failed photos, proceed
        gate = doc.get("gate") or {}
        media = {k: v for k, v in media.items() if gate.get(k, {}).get("ok", True)}
    elif doc.get("gate") is None:
        gate = _gate_photos(media)
        submissions.update_one({"_id": oid}, {"$set": {"gate": gate}})

        usable = [k for k, v in gate.items() if v.get("ok")]
        failed = [k for k, v in gate.items() if not v.get("ok")]

        if gate and not usable:
            # nothing usable → don't spend any classification calls
            reason = "None of the photos appeared to show a stream or were clear enough to assess."
            for q in rubric_service.get_rubric():
                if q.ai_enabled:
                    _write_question(oid, q.key, selection=None, conf=0.0,
                                    reason=reason, needs_human=True, status="skipped")
            submissions.update_one(
                {"_id": oid},
                {"$set": {"status": "needs_retake", "reason": reason}},
            )
            return

        if failed:
            # some usable, some not → pause and ask the user
            submissions.update_one({"_id": oid}, {"$set": {"status": "needs_photo_review"}})
            return
        # all usable → fall through to the groups with full media
    else:
        # gate already recorded and status isn't photo_review (e.g. a plain resume):
        # honour prior gate verdict and drop any failed photos
        gate = doc.get("gate") or {}
        media = {k: v for k, v in media.items() if gate.get(k, {}).get("ok", True)}


    groups = build_groups()

    for group_key, questions in groups.items():
        # skip questions already done (resume-safe)
        pending = [q for q in questions
                   if doc["answers"].get(q.key, {}).get("ai_status") == "pending"]
        if not pending:
            continue

        # gather this group's photos; if none present, mark needs_human and move on
        labeled_imgs = []
        if doc.get("photo_mode") == "unlabeled":
            # feed every usable photo to every group; labels are generic
            for label, uri in media.items():
                if label == "video":        # never send video to the AI
                    continue
                data, mime = _data_uri_to_part(uri)
                labeled_imgs.append((label, data, mime))
        else:
            for label in _GROUP_PHOTOS.get(group_key, []):
                uri = media.get(label)
                if uri:
                    data, mime = _data_uri_to_part(uri)
                    labeled_imgs.append((label, data, mime))

        if not labeled_imgs:
            for q in pending:
                _write_question(oid, q.key, selection=None, conf=0.0,
                                reason="No relevant photo provided.",
                                needs_human=True, status="done")
            continue

        try:
            prompt, ref_images = build_group_prompt(pending)
            # attach reference images (label + bytes) after the citizen photos
            for label, uri in ref_images:
                data, mime = _data_uri_to_part(uri)
                labeled_imgs.append((label, data, mime))

            data = gemini.json_from_labeled_images(labeled_imgs, prompt)
            by_key = {s.get("key"): s for s in data.get("suggestions", [])
                      if isinstance(s, dict)}

            for q in pending:
                s = by_key.get(q.key, {})
                selection = _validate_selection(q, s.get("selection"))
                conf = _coerce_conf(s.get("confidence", 0.0))
                needs_human = bool(s.get("needs_human", False)) or selection is None
                _write_question(oid, q.key, selection=selection, conf=conf,
                                reason=s.get("reason"), needs_human=needs_human,
                                status="done")
        except Exception as e:
            for q in pending:
                _write_question(oid, q.key, selection=None, conf=0.0,
                                reason=f"AI error: {e}", needs_human=True,
                                status="failed")

        _recompute_status(oid)

    _recompute_status(oid)
    _suggest_overall_for(oid)


def _write_question(oid, key, *, selection, conf, reason, needs_human, status):
    """Atomic per-field update — disjoint paths, no clobber between questions."""
    submissions.update_one(
        {"_id": oid},
        {"$set": {
            f"answers.{key}.ai_status": status,
            f"answers.{key}.ai_suggestion": selection,
            f"answers.{key}.value": selection,        # AI fills value; human overrides later
            f"answers.{key}.ai_confidence": conf,
            f"answers.{key}.ai_reason": reason,
            f"answers.{key}.needs_human": needs_human,
        }},
    )


def _recompute_status(oid) -> None:
    """Derive submission status from question states — never assumed."""
    doc = submissions.find_one({"_id": oid}, {"answers": 1})
    if not doc:
        return
    ai_states = [a.get("ai_status") for a in doc["answers"].values()
                 if a.get("source") == "ai" or a.get("ai_status") in ("pending", "done", "failed")]
    if any(st == "pending" for st in ai_states):
        status = "processing"
    elif any(st == "failed" for st in ai_states):
        status = "partial"
    else:
        status = "complete"
    submissions.update_one({"_id": oid}, {"$set": {"status": status}})


# ---- reads / overall ---------------------------------------------------

def get_submission(submission_id: str) -> dict | None:
    doc = submissions.find_one({"_id": ObjectId(submission_id)})
    return _to_public(doc) if doc else None


def list_submissions(username: str | None = None, limit: int = 50) -> list[dict]:
    query = {"username": username} if username else {}
    query["deleted"] = {"$ne": True}
    docs = submissions.find(query, {"media": 0}).sort("created_at", -1).limit(limit)
    return [_to_public(d) for d in docs]


def pending_submission_ids() -> list[str]:
    """For the startup sweep: anything still processing."""
    docs = submissions.find({"status": "processing"}, {"_id": 1})
    return [str(d["_id"]) for d in docs]


def _to_public(doc: dict) -> dict:
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    return d


# --- helpers -------------------------------------------------------------

def _coerce_conf(v) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if v > 1:            # model returned 0-100 instead of 0-1
        v = v / 100
    return max(0.0, min(1.0, v))


def _validate_selection(q, selection):
    if selection is None:
        return None
    if q.type == QuestionType.yesno:
        s = str(selection).strip().upper()
        return s if s in ("YES", "NO") else None
    if q.type == QuestionType.single:
        codes = {o.code for o in q.options}
        return selection if selection in codes else None
    if q.type == QuestionType.multi:
        if not isinstance(selection, list):
            selection = [selection]
        codes = {o.code for o in q.options}
        cleaned = [c for c in selection if c in codes]
        return cleaned or None
    return None  # value type: AI never fills

def _summarize_answers(merged: dict) -> str:
    """Human-readable 'Question: answer' lines from merged answers, for the synthesis prompt."""
    lines = []
    for q in rubric_service.get_rubric():
        a = merged.get(q.key)
        if not a:
            continue
        val = a.get("value")
        if val is None or val == "":
            continue
        # decode option codes to display names
        if q.type in ("single", "multi") and q.options:
            code_map = {o.code: o.display_name for o in q.options}
            if isinstance(val, dict):  # side_split {L,R}
                rendered = "; ".join(f"{side}: {code_map.get(v, v)}" for side, v in val.items())
            elif isinstance(val, list):
                rendered = ", ".join(code_map.get(v, str(v)) for v in val)
            else:
                rendered = code_map.get(val, str(val))
        elif isinstance(val, dict):  # side_split yes/no
            rendered = "; ".join(f"{side}: {v}" for side, v in val.items())
        else:
            rendered = str(val)
        lines.append(f"- {q.prompt} {rendered}")
    return "\n".join(lines)