"""Upsert the single admin account from env vars (spec §12). Idempotent — safe on every boot.

Env is the source of truth for the credential: if ADMIN_PASSWORD changes, the
stored hash is updated on the next run.
"""

from app.config import settings
from app.core.security import hash_password, verify_password
from app.database import SessionLocal
from app.models import Admin


def main() -> None:
    db = SessionLocal()
    try:
        admin = db.query(Admin).filter(Admin.username == settings.ADMIN_USERNAME).first()
        if admin is None:
            db.add(
                Admin(
                    username=settings.ADMIN_USERNAME,
                    password_hash=hash_password(settings.ADMIN_PASSWORD),
                )
            )
            db.commit()
            print(f"Seeded admin '{settings.ADMIN_USERNAME}'.")
        elif not verify_password(settings.ADMIN_PASSWORD, admin.password_hash):
            admin.password_hash = hash_password(settings.ADMIN_PASSWORD)
            db.commit()
            print(f"Updated password for admin '{settings.ADMIN_USERNAME}' from env.")
        else:
            print(f"Admin '{settings.ADMIN_USERNAME}' is up to date — nothing to do.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
