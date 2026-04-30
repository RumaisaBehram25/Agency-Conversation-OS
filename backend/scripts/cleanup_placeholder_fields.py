"""
Data Cleanup — Sanitize ManyChat placeholder variables in subscriber fields.

This script finds and nulls out any subscriber first_name, last_name, email, or phone
fields that contain unreplaced ManyChat template placeholders like {{first_name}},
{{email}}, {{phone}}, etc.

ManyChat sends placeholders when the corresponding field is not available in the
subscriber's profile. These should be treated as missing data (NULL) rather than
literal text.

Run with:
    docker compose exec api python scripts/cleanup_placeholder_fields.py
"""

import asyncio
import sys
import os
sys.path.insert(0, "/app")

from app.database import async_session_factory
from app.models.subscriber import Subscriber
from sqlalchemy import select, update, and_, or_


async def cleanup():
    async with async_session_factory() as db:
        # Count placeholders before cleanup
        before_first_name = await db.execute(
            select(Subscriber).where(
                or_(
                    Subscriber.first_name.like("{{%}}"),
                    Subscriber.first_name == "{{first_name}}",
                )
            )
        )
        before_fn_count = len(before_first_name.scalars().all())

        before_last_name = await db.execute(
            select(Subscriber).where(
                or_(
                    Subscriber.last_name.like("{{%}}"),
                    Subscriber.last_name == "{{last_name}}",
                )
            )
        )
        before_ln_count = len(before_last_name.scalars().all())

        before_email = await db.execute(
            select(Subscriber).where(
                or_(
                    Subscriber.email.like("{{%}}"),
                    Subscriber.email == "{{email}}",
                )
            )
        )
        before_email_count = len(before_email.scalars().all())

        before_phone = await db.execute(
            select(Subscriber).where(
                or_(
                    Subscriber.phone.like("{{%}}"),
                    Subscriber.phone == "{{phone}}",
                )
            )
        )
        before_phone_count = len(before_phone.scalars().all())

        print(f"\n📊 Placeholder Fields Found:")
        print(f"   first_name: {before_fn_count}")
        print(f"   last_name:  {before_ln_count}")
        print(f"   email:      {before_email_count}")
        print(f"   phone:      {before_phone_count}")
        print(f"   total:      {before_fn_count + before_ln_count + before_email_count + before_phone_count}")

        # Null out placeholder fields for first_name
        if before_fn_count > 0:
            await db.execute(
                update(Subscriber)
                .where(
                    or_(
                        Subscriber.first_name.like("{{%}}"),
                        Subscriber.first_name == "{{first_name}}",
                    )
                )
                .values(first_name=None)
            )
            print(f"\n✅ Cleaned first_name: {before_fn_count} records")

        # Null out placeholder fields for last_name
        if before_ln_count > 0:
            await db.execute(
                update(Subscriber)
                .where(
                    or_(
                        Subscriber.last_name.like("{{%}}"),
                        Subscriber.last_name == "{{last_name}}",
                    )
                )
                .values(last_name=None)
            )
            print(f"✅ Cleaned last_name: {before_ln_count} records")

        # Null out placeholder fields for email
        if before_email_count > 0:
            await db.execute(
                update(Subscriber)
                .where(
                    or_(
                        Subscriber.email.like("{{%}}"),
                        Subscriber.email == "{{email}}",
                    )
                )
                .values(email=None)
            )
            print(f"✅ Cleaned email: {before_email_count} records")

        # Null out placeholder fields for phone
        if before_phone_count > 0:
            await db.execute(
                update(Subscriber)
                .where(
                    or_(
                        Subscriber.phone.like("{{%}}"),
                        Subscriber.phone == "{{phone}}",
                    )
                )
                .values(phone=None)
            )
            print(f"✅ Cleaned phone: {before_phone_count} records")

        # Commit changes
        await db.commit()
        print("\n💾 All changes committed to database.\n")


if __name__ == "__main__":
    asyncio.run(cleanup())
