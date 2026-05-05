import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://attora:Attora-123@attora-db.cp8ooqrtonyo.us-east-1.rds.amazonaws.com:5432/attora')
    print('=== ALL TABLES ===')
    rows = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    for r in rows: print(r['table_name'])
    print('=== daily_analytics sample ===')
    rows = await conn.fetch('SELECT date, channel, ad_spend, conversions, new_conversations FROM daily_analytics ORDER BY date DESC LIMIT 5')
    for r in rows: print(dict(r))
    await conn.close()

asyncio.run(main())
