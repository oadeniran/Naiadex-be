# oah-assist-api

FastAPI backend for the OAH Assist project (Phase 0 skeleton).

Serves a health endpoint and CORS-enabled API for the separate frontend app
(`oah-assist-web`). AI (Gemini) endpoints are added in Phase 1.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional; defaults already allow localhost:5173
uvicorn app.main:app --reload      # serves on http://localhost:8000
```

Check it:
- Health: http://localhost:8000/api/health
- Swagger UI: http://localhost:8000/docs   <- always available at the app root

## Deploy to Heroku (dashboard, no CLI)

1. Push this folder to its own GitHub repo.
2. Heroku dashboard -> New -> Create new app (e.g. `oah-assist-api`).
3. Deploy tab -> Deployment method -> GitHub -> connect this repo.
4. Settings -> Config Vars, add:
   - `CORS_ORIGINS = https://oah-assist-web.herokuapp.com`
     (use the real frontend URL; no trailing slash; comma-separate if several)
5. Deploy tab -> Enable Automatic Deploys (branch: main) -> Deploy Branch.
6. Confirm `https://oah-assist-api.herokuapp.com/api/health` and `/docs` load.

Heroku auto-detects Python from `requirements.txt` + `.python-version`,
and runs the `Procfile` web command. No Procfile changes needed later.

## Deploy order (important)

Deploy this backend FIRST, copy its live URL, then set that URL as
`VITE_API_BASE` on the frontend app BEFORE the frontend builds — Vite bakes
that value into the bundle at build time.
