"""Create (or reset) the SPARK admin user in the configured MongoDB."""

from __future__ import annotations

import asyncio
import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "python-shared"))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from instascope_shared.core.security import hash_password
from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.models import DEFAULT_ORG_ID, User, UserRole, UserSettings

EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@spark.example.com").lower().strip()
PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "Admin1234!")
NAME = os.environ.get("SEED_ADMIN_NAME", "Admin")


async def main() -> None:
    await connect_db()
    try:
        user = await User.find_one(User.email == EMAIL)
        if user:
            user.password_hash = hash_password(PASSWORD)
            user.name = NAME
            user.role = UserRole.ADMIN
            user.org_id = getattr(user, "org_id", None) or DEFAULT_ORG_ID
            user.is_active = True
            await user.save()
            print(f"Updated admin: {EMAIL} (role=admin, org={user.org_id})")
        else:
            user = User(
                email=EMAIL,
                password_hash=hash_password(PASSWORD),
                name=NAME,
                role=UserRole.ADMIN,
                org_id=DEFAULT_ORG_ID,
            )
            await user.insert()
            existing_settings = await UserSettings.find_one(UserSettings.user_id == str(user.id))
            if not existing_settings:
                await UserSettings(user_id=str(user.id)).insert()
            print(f"Created admin: {EMAIL} (role=admin, org={DEFAULT_ORG_ID})")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
