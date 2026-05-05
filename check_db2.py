import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://attora:Attora-123@attora-db.cp8ooqrtonyo.us-east-1.rds.amazonaws.com:5432/attora')
    
    print('=== ad_campaigns ===')
    rows = await conn.fetch('SELECT * FROM ad_campaigns LIMIT 5')
    for r in rows: print(dict(r))
    
    print('=== campaign_metrics ===')
    rows = await conn.fetch('SELECT * FROM campaign_metrics ORDER BY date DESC LIMIT 5')
    for r in rows: print(dict(r))
    
    print('=== campaign_breakdowns ===')
    rows = await conn.fetch('SELECT * FROM campaign_breakdowns ORDER BY date DESC LIMIT 5')
    for r in rows: print(dict(r))
    
    print('=== daily_analytics channel values ===')
    rows = await conn.fetch('SELECT DISTINCT channel FROM daily_analytics')
    for r in rows: print(dict(r))

    await conn.close()

asyncio.run(main())
