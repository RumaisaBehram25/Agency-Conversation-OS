"""Read-only: dump the REAL Warrior Babe org's playbook and override."""
import asyncio
import asyncpg

DB_URL = "postgresql://attora:Attora-123@attora-db.cp8ooqrtonyo.us-east-1.rds.amazonaws.com:5432/attora"
REAL_WB_ORG_UUID = "b45a859a-ae50-4c0a-885a-c9fe5d357981"  # slug='warrior-babe'


async def main():
    conn = await asyncpg.connect(DB_URL)
    row = await conn.fetchrow(
        "SELECT system_prompt_override, conversion_playbook FROM ai_config WHERE org_id = $1",
        REAL_WB_ORG_UUID,
    )
    print("=" * 70)
    print("system_prompt_override (FULL) - REAL warrior-babe org")
    print("=" * 70)
    print(row['system_prompt_override'])
    print("\n" + "=" * 70)
    print("conversion_playbook (FULL) - REAL warrior-babe org")
    print("=" * 70)
    print(row['conversion_playbook'])
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
