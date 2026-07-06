# Setup Guide

Everything runs locally with Docker Compose — one command brings up the database,
backend, and frontend.

## Prerequisites

- **Docker Desktop** (with the WSL2 backend on Windows), running.
- An **OpenAI API key** (`https://platform.openai.com/api-keys`). The app uses
  `text-embedding-3-small` and `gpt-4o-mini`; a full demo costs well under $0.10.

## Steps

1. **Configure secrets**

   ```bash
   cp .env.example .env
   ```

   Edit `.env`:
   - `OPENAI_API_KEY` — your real key (required for ingestion and chat).
   - `ADMIN_PASSWORD` — pick a real password (the admin account is created from it,
     and re-synced from it on every restart).
   - `JWT_SECRET` — any long random string.

2. **Build and start**

   ```bash
   docker compose up --build
   ```

   First boot takes a few minutes (image pulls + installs). The backend then runs
   Alembic migrations (enabling the `vector` extension and creating all five tables),
   seeds the admin account from `.env`, and starts serving.

3. **Verify**

   ```bash
   curl http://localhost:8000/api/health     # -> {"status":"ok"}
   ```

   - Customer chat: <http://localhost:5173/>
   - Admin dashboard: click **"Login as Admin"** in the chat page header, or go to
     <http://localhost:5173/admin/login> directly (log in with
     `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env`)

4. **Load the demo corpus** (optional but recommended)

   ```bash
   docker compose exec backend python -m scripts.seed_content
   ```

   Uploads two generated PDFs and two reference images through the real admin API
   (idempotent — safe to re-run). Alternatively, upload your own PDFs/images by
   drag-and-drop at `/admin/content`.

5. **Run the tests**

   ```bash
   docker compose exec -T backend pytest -q
   ```

   All 58 tests should pass. DB-backed tests run against the compose database; the
   suite seeds and cleans its own fixtures.

## Development mode

`docker-compose.override.yml` (applied automatically by `docker compose up`)
bind-mounts the source into both containers: backend code hot-reloads via
`uvicorn --reload`, frontend via Vite HMR. Delete or rename the override file to run
the plain production-shaped configuration. If you change `.env`, recreate the
backend: `docker compose up -d --force-recreate backend`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `error during connect: ... dockerDesktopLinuxEngine` | Docker Desktop isn't running — start it and retry |
| Port `8000` or `5173` already in use | Stop the conflicting process, or change the port mapping in `docker-compose.yml` |
| Upload stuck on `failed` | Almost always a missing/invalid `OPENAI_API_KEY` — check `docker compose logs backend`, fix `.env`, recreate the backend, delete and re-upload |
| Chat answers "I don't have information…" to everything | No content indexed yet — run the seed script or upload documents in the admin dashboard |
| `429` on login or chat | Per-IP rate limits (`LOGIN_RATE_LIMIT`, `CHAT_RATE_LIMIT`) — wait a minute |
| First chat answer feels slow | Cold start on the first OpenAI call after boot — subsequent answers stream in ~2s |
| Start completely fresh | `docker compose down -v` (deletes the database **and** uploaded files), then `docker compose up --build` |
