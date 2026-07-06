"""Auto-seed the default demo corpus on a fresh (empty) database.

Launched in the background from the backend startup command. It waits for the
local API to come up and, only if NO content exists yet, seeds the canonical
demo corpus by delegating to ``scripts.seed_content``. On any database that
already holds a document or image this is a no-op, so it never touches
admin-managed content or re-adds files an admin deliberately deleted.

Best-effort by design: every failure (API never comes up, bad admin creds,
missing/invalid ``OPENAI_API_KEY``, upload error) is logged and swallowed. It
must never crash the container or block uvicorn — it runs detached from the
serving process, so the app always comes up regardless of seeding outcome.

    docker compose exec backend python -m scripts.seed_content_on_boot  # manual run
"""

import time

import httpx

from app.config import settings
from scripts import seed_content

BASE = "http://localhost:8000/api"
HEALTH_TIMEOUT_S = 90


def _log(msg: str) -> None:
    print(f"[seed-on-boot] {msg}", flush=True)


def _wait_for_api(client: httpx.Client) -> bool:
    """Poll /api/health until the API answers or the timeout elapses."""
    for _ in range(HEALTH_TIMEOUT_S):
        try:
            if client.get(f"{BASE}/health").status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def _content_is_empty(client: httpx.Client) -> bool:
    resp = client.post(
        f"{BASE}/admin/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    resp.raise_for_status()
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    documents = client.get(f"{BASE}/admin/documents", headers=headers).json()
    images = client.get(f"{BASE}/admin/images", headers=headers).json()
    return not documents and not images


def main() -> None:
    client = httpx.Client(timeout=30)
    if not _wait_for_api(client):
        _log(f"API did not become healthy within {HEALTH_TIMEOUT_S}s; skipping auto-seed.")
        return

    try:
        if not _content_is_empty(client):
            _log("Database already has content — nothing to seed.")
            return
    except Exception as exc:  # noqa: BLE001 - best-effort, never crash the container
        _log(f"Could not check existing content ({exc!r}); skipping auto-seed.")
        return

    _log("Empty database detected — seeding the default demo corpus...")
    try:
        seed_content.main()
        _log("Auto-seed complete.")
    except Exception as exc:  # noqa: BLE001 - e.g. missing/invalid OPENAI_API_KEY
        _log(
            f"Auto-seed failed ({exc!r}). The app is running normally; seed manually "
            "with 'docker compose exec backend python -m scripts.seed_content'."
        )


if __name__ == "__main__":
    main()
