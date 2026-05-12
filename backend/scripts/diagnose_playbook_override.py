"""Read-only: check if system_prompt_override on Warrior Babe contains old wording."""
import asyncio
import asyncpg

DB_URL = "postgresql://attora:Attora-123@attora-db.cp8ooqrtonyo.us-east-1.rds.amazonaws.com:5432/attora"
WB_ORG_UUID = "88351387-8882-49e0-a976-d5ef477a6309"


async def main():
    conn = await asyncpg.connect(DB_URL)
    row = await conn.fetchrow(
        """
        SELECT
            system_prompt_override,
            char_length(coalesce(system_prompt_override, '')) AS override_len,
            char_length(coalesce(conversion_playbook, '')) AS playbook_len
        FROM ai_config
        WHERE org_id = $1
        """,
        WB_ORG_UUID,
    )

    print(f"system_prompt_override length: {row['override_len']}")
    print(f"conversion_playbook length:    {row['playbook_len']}\n")

    override = row['system_prompt_override'] or ''
    if not override:
        print("system_prompt_override is empty / null — not the culprit.")
    else:
        print("=== FIRST 1500 chars of system_prompt_override ===")
        print(override[:1500])
        print("\n=== TAIL 500 chars ===")
        print(override[-500:])
        print("\n=== Old-wording markers (should ideally all be False) ===")
        print(f"  Contains 'Drop the booking link inline':    {'Drop the booking link inline' in override}")
        print(f"  Contains 'build a plan around it':          {'build a plan around it' in override}")
        print(f"  Contains 'Grab a time here: [CALL_LINK]':   {'Grab a time here: [CALL_LINK]' in override}")
        print("\n=== New-wording markers (True means already updated) ===")
        print(f"  Contains 'TWO-STEP':                        {'TWO-STEP' in override}")
        print(f"  Contains 'would you be open to':            {'would you be open to' in override}")
        print(f"  Contains 'ASK PERMISSION FIRST':            {'ASK PERMISSION FIRST' in override}")

    # Also check the campaign-level conversation_script (takes priority over playbook per prompt_builder.py:332)
    print("\n=== ad_campaigns with non-null conversation_script ===")
    rows = await conn.fetch(
        """
        SELECT id, name, char_length(coalesce(conversation_script, '')) AS script_len
        FROM ad_campaigns
        WHERE org_id = $1 AND conversation_script IS NOT NULL AND conversation_script <> ''
        ORDER BY name
        """,
        WB_ORG_UUID,
    )
    if not rows:
        print("  (none — conversion_playbook will be used)")
    else:
        for r in rows:
            print(f"  {r['name']} (id={r['id']}): {r['script_len']} chars")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
