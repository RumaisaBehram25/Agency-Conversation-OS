"""Read-only: figure out which UUID is the real Warrior Babe org and check both ai_configs."""
import asyncio
import asyncpg

DB_URL = "postgresql://attora:Attora-123@attora-db.cp8ooqrtonyo.us-east-1.rds.amazonaws.com:5432/attora"


async def main():
    conn = await asyncpg.connect(DB_URL)

    print("=== ALL organizations ===")
    rows = await conn.fetch("SELECT id, name, slug FROM organizations ORDER BY name")
    for r in rows:
        print(f"  {r['id']}  |  slug={r['slug']!r:25}  |  name={r['name']!r}")

    print("\n=== ai_config rows ===")
    rows = await conn.fetch(
        """
        SELECT
            ac.org_id,
            o.name AS org_name,
            o.slug AS org_slug,
            char_length(coalesce(ac.system_prompt_override, '')) AS override_len,
            char_length(coalesce(ac.conversion_playbook, '')) AS playbook_len,
            'TWO-STEP' = ANY(string_to_array(ac.system_prompt_override, E'\n')) AS override_has_two_step_line,
            position('TWO-STEP exchange' in coalesce(ac.system_prompt_override, '')) > 0 AS override_has_two_step,
            position('TWO-STEP' in coalesce(ac.conversion_playbook, '')) > 0 AS playbook_has_two_step,
            position('Drop the booking link inline' in coalesce(ac.system_prompt_override, '')) > 0 AS override_has_old_wording
        FROM ai_config ac
        JOIN organizations o ON o.id = ac.org_id
        ORDER BY o.name
        """
    )
    for r in rows:
        print(f"\n  org_id:                       {r['org_id']}")
        print(f"  org_name:                     {r['org_name']!r}")
        print(f"  org_slug:                     {r['org_slug']!r}")
        print(f"  system_prompt_override len:   {r['override_len']}")
        print(f"  conversion_playbook len:      {r['playbook_len']}")
        print(f"  override has 'TWO-STEP':      {r['override_has_two_step']}")
        print(f"  playbook  has 'TWO-STEP':     {r['playbook_has_two_step']}")
        print(f"  override has OLD wording:     {r['override_has_old_wording']}")

    # Which org owns the playground test subscriber?
    sub = await conn.fetchrow(
        """
        SELECT s.id AS sub_id, s.org_id, o.name AS org_name, o.slug AS org_slug
        FROM subscribers s
        JOIN organizations o ON o.id = s.org_id
        WHERE s.manychat_subscriber_id LIKE 'attora_test%'
        ORDER BY s.created_at DESC
        LIMIT 5
        """
    )
    print("\n=== Recent playground subscribers and their org ===")
    rows = await conn.fetch(
        """
        SELECT s.manychat_subscriber_id AS msid, s.org_id, o.name AS org_name, o.slug AS org_slug
        FROM subscribers s
        JOIN organizations o ON o.id = s.org_id
        WHERE s.manychat_subscriber_id LIKE 'attora_test%'
        ORDER BY s.created_at DESC
        LIMIT 5
        """
    )
    for r in rows:
        print(f"  {r['msid']:30} -> {r['org_id']} ({r['org_name']!r}, slug={r['org_slug']!r})")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
