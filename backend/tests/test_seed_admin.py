from passlib.context import CryptContext
from sqlalchemy import text

from app.config import settings
from scripts.seed_admin import main

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _fetch_admin(db_engine):
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*), max(password_hash) FROM admins WHERE username = :u"),
            {"u": settings.ADMIN_USERNAME},
        ).first()


def test_seed_admin_idempotent(db_engine):
    main()
    main()  # second run must not duplicate

    count, _ = _fetch_admin(db_engine)
    assert count == 1


def test_seed_admin_upserts_rotated_password(db_engine, monkeypatch):
    """Plan says 'upsert': changing ADMIN_PASSWORD in env must update the stored hash."""
    original_password = settings.ADMIN_PASSWORD
    main()

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "rotated-pass-123")
    main()

    count, rotated_hash = _fetch_admin(db_engine)
    assert count == 1
    assert pwd_context.verify("rotated-pass-123", rotated_hash)

    # restore the original credential so the dev login keeps working after the test
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", original_password)
    main()
    _, restored_hash = _fetch_admin(db_engine)
    assert pwd_context.verify(original_password, restored_hash)
