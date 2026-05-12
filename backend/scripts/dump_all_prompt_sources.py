"""Read-only: dump system_prompt_override and both campaign conversation_scripts in full."""
import asyncio
import asyncpg

DB_URL = "postgresql://attora:Attora-123@attora-db.cp8ooqrtonyo.us-east-1.rds.amazonaws.com:5432/attora"
WB_ORG_UUID = "88351387-8882-49e0-a976-d5ef477a6309"


async def main():
    conn = await asyncpg.connect(DB_URL)

    override = await conn.fetchval(
        "SELECT system_prompt_override FROM ai_config WHERE org_id = $1",
        WB_ORG_UUID,
    )
    print("=" * 70)
    print("system_prompt_override (FULL)")
    print("=" * 70)
    print(override)

    rows = await conn.fetch(
        "SELECT id, name, conversation_script FROM ad_campaigns "
        "WHERE org_id = $1 AND conversation_script IS NOT NULL AND conversation_script <> '' "
        "ORDER BY name",
        WB_ORG_UUID,
    )
    for r in rows:
        print("\n" + "=" * 70)
        print(f"ad_campaigns.conversation_script for: {r['name']}")
        print(f"  id: {r['id']}")
        print("=" * 70)
        print(r['conversation_script'])

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
