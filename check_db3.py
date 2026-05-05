import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://attora:Attora-123@attora-db.cp8ooqrtonyo.us-east-1.rds.amazonaws.com:5432/attora')
    
    print('=== ad_campaigns for Matt org b45a859a ===')
    rows = await conn.fetch("SELECT id, name, meta_campaign_id, is_attora_managed FROM ad_campaigns WHERE org_id='b45a859a-ae50-4c0a-885a-c9fe5d357981'")
    for r in rows: print(dict(r))
    
    print('=== campaign_metrics for Matt org (count) ===')
    val = await conn.fetchval("SELECT COUNT(*) FROM campaign_metrics WHERE org_id='b45a859a-ae50-4c0a-885a-c9fe5d357981'")
    print('total rows:', val)
    
    print('=== distinct meta_campaign_ids in campaign_metrics for Matt ===')
    rows = await conn.fetch("SELECT DISTINCT meta_campaign_id, meta_campaign_name FROM campaign_metrics WHERE org_id='b45a859a-ae50-4c0a-885a-c9fe5d357981'")
    for r in rows: print(dict(r))

    await conn.close()

asyncio.run(main())
