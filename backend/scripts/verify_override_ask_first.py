"""Read-only: verify the override now uses the ask-first wording."""
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
    print(f"Total chars: {len(override)}\n")

    print("NEW (should all be True):")
    print(f"  'TWO-STEP exchange':                      {'TWO-STEP exchange' in override}")
    print(f"  'STEP 1 - Acknowledge':                   {'STEP 1 — Acknowledge' in override}")
    print(f"  'would you be open to a quick 15 min':    {'would you be open to a quick 15 min' in override}")
    print(f"  'POST-PURCHASE TEAM-CALL OFFER':          {'POST-PURCHASE TEAM-CALL OFFER' in override}")

    print("\nOLD inline-link wording (should all be False):")
    print(f"  'build a plan around it':                                 {'build a plan around it' in override}")
    print(f"  'Grab a time here: https://www.warriorbabe.com/schedule': {'Grab a time here: https://www.warriorbabe.com/schedule' in override}")
    print(f"  'it might be worth a quick 15-minute chat':               {'it might be worth a quick 15-minute chat' in override}")

    print("\nPreserved bottom (should all be True):")
    print(f"  '7-DAY METABOLISM RESET' qualifier:       {'7-DAY METABOLISM RESET' in override}")
    print(f"  'MACRO METHOD' qualifier:                 {'MACRO METHOD' in override}")
    print(f"  'TONE NOTES SPECIFIC TO THIS CLIENT':     {'TONE NOTES SPECIFIC TO THIS CLIENT' in override}")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
