"""Read-only check: confirm the 025 wording is live on RDS."""
import asyncio
import asyncpg

DB_URL = "postgresql://attora:Attora-123@attora-db.cp8ooqrtonyo.us-east-1.rds.amazonaws.com:5432/attora"
WB_ORG_UUID = "88351387-8882-49e0-a976-d5ef477a6309"


async def main():
    conn = await asyncpg.connect(DB_URL)
    row = await conn.fetchrow(
        "SELECT conversion_playbook FROM ai_config WHERE org_id = $1",
        WB_ORG_UUID,
    )
    pb = row[0]
    print(f"Total chars: {len(pb)}\n")

    print("NEW (should all be True):")
    print(f"  'TWO-STEP':                              {'TWO-STEP' in pb}")
    print(f"  'STEP 1 - Acknowledge':                  {'STEP 1 — Acknowledge' in pb}")
    print(f"  'would you be open to a quick 15 min':   {'would you be open to a quick 15 min' in pb}")
    print(f"  'ASK PERMISSION FIRST':                  {'ASK PERMISSION FIRST' in pb}")

    print("\nOLD (should all be False):")
    print(f"  'Drop the booking link inline':                          {'Drop the booking link inline' in pb}")
    print(f"  'build a plan around it. Grab a time here: [CALL_LINK]': {'build a plan around it. Grab a time here: [CALL_LINK]' in pb}")

    ver = await conn.fetchval("SELECT version_num FROM alembic_version")
    print(f"\nalembic_version: {ver}")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
