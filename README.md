# Naiadex — API 

The backend for **Naiadex**, a citizen-science companion for urban streams built for the
IEEE OneAquaHealth Global Hackathon 2026. It powers three things:

- **Identify** — AI identification of stream organisms from a photo, with a community
  review loop (suggest / accept / comment).
- **Assess** — AI-assisted stream-health assessment against a structured ecological
  rubric, run asynchronously in the background, with a human review-and-finalize step.
- **Explore** — a feed of finalized assessments, filterable by rubric criteria and
  location, each with an AI-written plain-language summary.

The guiding principle throughout is **AI with a human in the loop**: the AI drafts,
explains its reasoning and confidence, and declines to guess when a photo can't support
an answer — a person always confirms.

---

## Stack

- **FastAPI** (Python 3.12)
- **MongoDB** (via `pymongo`) — all application data
- **Google Gemini** (via `google-genai`) — vision + text generation
- **Mapbox** — geocoding is called from the frontend; the backend only stores coordinates

---

## Architecture

Strict separation of concerns — routers do HTTP only, services hold logic, schemas live
in their own folder, prompts are isolated so they're easy to tune:

```
app/
  main.py              # app wiring, CORS, router registration, startup resume sweep
  ai_client.py         # Gemini client wrapper (vision, multi-image, text)
  routers/             # HTTP only — no business logic
    identify.py        # identify + observation community loop (suggest/accept/comment/location)
    assess.py          # /assess/analyze, /assess/overall
    submissions.py     # create/list/get/patch/delete + resume; review + finalize
    rubric.py          # GET the active rubric
    sites.py           # official sites + user sites
    admin.py           # rubric & site management (token-gated)
    explore.py         # finalized-only public feed
    feedback.py        # feedback capture
  services/            # the logic
    identify.py        # observation CRUD + community ops
    assess.py          # the async engine (gate -> topic groups -> incremental writes)
    rubric.py          # loads + caches the rubric from Mongo
    gemini.py          # structured/text helpers over ai_client
    db.py              # one Mongo client; exposes collections
  prompts/             # prompt text, kept out of logic
    identify.py
    assess.py          # analyze (grouped), gate, overall, synthesis
  schemas/             # ALL Pydantic models live here (never inline in routers)
    identify.py
    assess.py
    rubric.py
    sites.py
    feedback.py
  data/                # static reference data (if used)
init_env.py            # loads .env + downloads Vertex credentials before anything else
seed_rubric.py         # seed the rubric (questions, options, reference images)
seed_sites.py          # seed the official monitoring sites
seed_submissions.py    # seed demo finalized assessments through the real pipeline
```

### Key design decisions

- **Rubric lives in Mongo, not code.** Questions, options, and reference images are
  seeded into a collection so organizers can edit the assessment criteria (via the admin
  endpoints) without a code change. The analyze prompt is *generated from* the rubric, so
  adding a question automatically makes the AI attempt it.
- **Assessment is asynchronous.** `POST /api/submissions` returns in milliseconds with
  status `processing`; a background task runs a cheap **photo-relevance gate** first
  (rejecting non-stream photos before spending AI credits), then **topic-grouped** Gemini
  calls (channel / pressures / margins) that write each question's result back
  incrementally via atomic per-field `$set`. The frontend polls to watch findings fill
  in. A startup sweep re-runs anything left `processing` after a restart.
- **Photos are base64 in the document** (demo simplicity). Lists therefore **project out
  `media`** to stay fast; only single-item fetches return photos. Production would move
  media to object storage (Cloudinary) and keep only URLs.
- **Human-in-the-loop is recorded.** AI suggestions are stored alongside the human's
  final value with a `source` flag, so the "AI said X, human chose Y" trail is preserved.

---

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then fill in the values below
uvicorn app.main:app --reload      # http://localhost:8000
```

- Health: `http://localhost:8000/api/health`
- Interactive docs: `http://localhost:8000/docs`

### Environment variables

Set in `.env` locally, and as Config Vars on Heroku:

| Variable | Purpose |
|---|---|
| `MONGO_URI` | MongoDB connection string |
| `DB_NAME` | database name (default `naiadex`) |
| `CORS_ORIGINS` | comma-separated allowed frontend origins, no trailing slash (e.g. `http://localhost:5173,https://naiadex-web.herokuapp.com`) |
| `JSON_URL` | URL to download the Vertex/Gemini service-account JSON |
| `GOOGLE_APPLICATION_CREDENTIALS` | path the downloaded creds are written to (e.g. `creds.json`) |
| `ADMIN_TOKEN` | optional; when set, admin routes require the `X-Admin-Token` header. Unset = admin open (dev convenience) |

`init_env.py` runs first (imported for its side effect) and downloads the Vertex
credentials from `JSON_URL` before the Gemini client is constructed.

---

## Seeding

Run **after** the backend can reach Mongo and Gemini. Both rubric/sites seeders support a
dry run (default) and `--commit`:

```bash
python seed_sites.py                 # dry run — prints what would be written
python seed_sites.py --commit        # persist official sites

python seed_rubric.py                # dry run — reports option images + warnings
python seed_rubric.py --commit       # persist rubric + embedded reference images
```

Reference images live under `images/<question_key>/`, matched to option codes
case-insensitively (`sb.jpg`, `sb_1.jpg` → option `SB`); yes/no questions use any image
in the folder as a labeled example, with the filename becoming the caption.

**Demo assessments** are seeded by running real photos through the live pipeline (not by
inserting fake documents), so they exercise the real gate, AI, and synthesis:

```
seed_photos/<name>/
  1.jpg 2.jpg ...        # up to 5 photos, any names (unlabeled mode)
  meta.json              # { "site_code": "C5" } OR { "lat":.., "lng":.., "name":".." }, + optional "overall_hint"
```

```bash
python seed_submissions.py --finalize                               # local
python seed_submissions.py --api https://<api>.herokuapp.com --finalize   # deployed
```

> Seeding spends AI credits (gate + topic-group calls + synthesis per submission). Seed
> deliberately — a handful spanning Good/Moderate/Poor is enough for a lively Explore.

---

## Deploy (Heroku, dashboard / no CLI)

1. Push this repo to GitHub.
2. Heroku → New → Create app (e.g. `naiadex-api`).
3. Deploy tab → connect the GitHub repo → Enable Automatic Deploys (branch `main`).
4. Settings → Config Vars → add the variables above (set `CORS_ORIGINS` to the live
   frontend URL).
5. Deploy. Heroku auto-detects Python from `requirements.txt` + `.python-version` and
   runs the `Procfile`:
   ```
   web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

**Deploy the backend first**, copy its URL, then set it as `VITE_API_BASE` on the
frontend before the frontend builds.

---

## Gotchas worth knowing

- **Heroku filesystem is ephemeral** — nothing is written to disk and expected to persist;
  all state is in Mongo.
- **Lists must project out `media`** — a list endpoint returning base64 photos will hang
  the client (a submission with photos is ~750 KB+). The submissions and explore list
  queries exclude `media` (and `gate`) deliberately.
- **Route ordering** — `/observations/all` must be declared *before* `/observations/{id}`
  or `all` is captured as an id.
- **The async engine is in-process** (`BackgroundTasks`) — tolerant of restarts via the
  resume endpoint + startup sweep, but not a durable queue. Production would use a worker
  dyno + Redis/RQ.