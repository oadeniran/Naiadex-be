import json

from app.schemas.rubric import Question, QuestionType


def build_analyze_prompt(questions: list[Question]) -> str:
    lines = [
        "You are assisting a citizen-science assessment of an urban freshwater stream. "
        "You are shown several labeled photos taken by a citizen (upstream, downstream, "
        "context, biodiversity). Classify what the photos show for each question below.\n",
        "CRITICAL RULES:",
        "- Judge each question only from the photos listed as relevant to it.",
        "- If the relevant photo is missing or the feature is not clearly visible, set "
        "needs_human=true and do NOT guess.",
        "- Never decide left vs right bank; assess the channel as a whole. The human assigns side.",
        "- Return calibrated confidence between 0 and 1.",
        "- Use ONLY the exact option codes provided.\n",
        "QUESTIONS:",
    ]
    for q in questions:
        relevant = ", ".join(q.source_photos) if q.source_photos else "any"
        lines.append(f"\n- key: {q.key}")
        lines.append(f"  prompt: {q.prompt}")
        lines.append(f"  type: {q.type.value}")
        lines.append(f"  relevant_photos: {relevant}")
        if q.type in (QuestionType.single, QuestionType.multi):
            opts = "; ".join(f"{o.code}={o.display_name}" for o in q.options)
            lines.append(f"  options: {opts}")
        elif q.type == QuestionType.yesno:
            lines.append("  options: YES, NO")
        if q.ai_hint:
            lines.append(f"  hint: {q.ai_hint}")

    lines.append(
        '\nReturn ONLY a JSON object of this exact shape:\n'
        '{ "suggestions": [ { "key": "<question key>", '
        '"selection": <one code string for single, "YES"/"NO" for yesno, '
        'a list of code strings for multi, or null>, '
        '"confidence": <0..1>, "reason": "<short justification>", '
        '"needs_human": <true|false> } ] }\n'
        "Include exactly one entry for every question listed above."
    )
    return "\n".join(lines)


def build_overall_prompt(answers: dict) -> str:
    return (
        "Based on this citizen stream assessment, provide an overall ecosystem health "
        "rating. Worse health: artificial/concrete channel and banks, no riparian "
        "vegetation, turbid/foamy/discoloured water, pipes or sewage discharge, "
        "construction, invasive species. Better health: natural channel, layered riparian "
        "vegetation (trees/shrubs), clear water, varied habitats and natural debris.\n\n"
        f"Answers: {json.dumps(answers, default=str)}\n\n"
        'Return ONLY JSON: {"value": "GOOD"|"MODERATE"|"POOR", "reason": "<short>"}'
    )


def build_group_prompt(questions: list[Question]) -> tuple[str, list[tuple[str, str]]]:
    """Build the classification prompt for one topic group.

    Returns (prompt_text, reference_images) where reference_images is a list of
    (label, data_uri) to attach to the call so the model can see each cue.
    """
    ref_images: list[tuple[str, str]] = []
    lines = [
        "You are assisting a citizen-science assessment of an urban freshwater stream. "
        "You are shown the citizen's photos, then a set of labeled REFERENCE images "
        "showing what each answer option or cue looks like. Classify the citizen's "
        "photos against the questions below.\n",
        "RULES:",
        "- Judge each question only from the citizen photos relevant to it.",
        "- If the relevant photo is missing or the feature isn't clearly visible, set "
        "needs_human=true and do NOT guess.",
        "- Never decide left vs right bank; assess the channel as a whole.",
        "- Confidence is 0..1. Use ONLY the exact option codes given.\n",
        "QUESTIONS:",
    ]
    for q in questions:
        relevant = ", ".join(q.source_photos) if q.source_photos else "any"
        lines.append(f"\n- key: {q.key}")
        lines.append(f"  prompt: {q.prompt}")
        lines.append(f"  type: {q.type.value}")
        lines.append(f"  relevant_photos: {relevant}")
        if q.type in (QuestionType.single, QuestionType.multi):
            opts = "; ".join(f"{o.code}={o.display_name}" for o in q.options)
            lines.append(f"  options: {opts}")
            for o in q.options:
                for img in o.images:
                    ref_images.append((f"reference — {o.display_name} ({o.code})", img.image))
        elif q.type == QuestionType.yesno:
            lines.append("  options: YES, NO")
            for ex in q.example_images:
                ref_images.append((f"reference — example of {q.prompt!r}: {ex.label}", ex.image))
        if q.ai_hint:
            lines.append(f"  hint: {q.ai_hint}")

    lines.append(
        '\nReturn ONLY JSON: { "suggestions": [ { "key": "...", "selection": '
        '<code | ["codes"] | "YES"/"NO" | null>, "confidence": <0..1>, '
        '"reason": "...", "needs_human": <bool> } ] } — one entry per question above.'
    )
    return "\n".join(lines), ref_images

def build_gate_prompt(labels: list[str]) -> str:
    """Cheap relevance/quality check, one call over all provided photos.

    Be LENIENT: urban streams are often heavily modified — concrete channels,
    culverts, duct-like canals all count as valid. Reject only photos that
    clearly do NOT show a stream/waterway or its immediate surroundings, or
    that are too dark/blurry/small to assess.
    """
    photos = ", ".join(labels)
    return (
        "You are screening citizen photos before an urban-stream assessment. "
        "For EACH labeled photo, decide if it is usable: does it show a stream, "
        "river, canal, ditch or its immediate surroundings (banks, margins, nearby "
        "roads/buildings), AND is it clear enough to assess?\n\n"
        "IMPORTANT: urban streams are often heavily modified. Concrete-lined channels, "
        "culverts, canals and duct-like waterways ARE valid streams — do not reject "
        "them. The 'context'/surroundings photo may show roads or buildings near the "
        "water and is still valid. Be lenient: reject a photo only if it clearly does "
        "NOT show a waterway or its surroundings (e.g. indoor scenes, people, objects, "
        "unrelated subjects), or is too dark/blurry/small to judge.\n\n"
        f"Photos provided (each precedes its image): {photos}\n\n"
        'Return ONLY JSON: { "photos": [ { "label": "<label>", "ok": <true|false>, '
        '"reason": "<short reason>" } ] } — one entry per provided photo.'
    )

def build_synthesis_prompt(site_name: str, overall: str | None, answers_summary: str) -> str:
    return (
        "Write a short, plain-language summary of a citizen's urban-stream health "
        "assessment, for a general audience. Use the confirmed findings below.\n\n"
        f"Site: {site_name}\n"
        f"Overall rating: {overall or 'not specified'}\n"
        f"Confirmed findings:\n{answers_summary}\n\n"
        "Write 2–4 short paragraphs in Markdown. Start with the overall picture, then "
        "note what's healthy and what's degraded (channel, banks, water, vegetation, "
        "habitats, pressures like pipes/construction). Connect it briefly to why it "
        "matters for the stream and the community (the One Health idea). Be factual and "
        "readable — no headings, no bullet lists, just clear prose. Do not invent details "
        "not in the findings.\n\n"
        "Return ONLY the Markdown text — no preamble, no code fences."
        "Base the summary ONLY on the findings listed. If a characteristic isn't in the findings, do not mention or invent it."
    )