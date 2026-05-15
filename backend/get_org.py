import asyncio
from app.database import async_session_factory
from sqlalchemy import text

async def main():
    async with async_session_factory() as db:
        result = await db.execute(text("SELECT o.id, o.name FROM organizations o JOIN org_users ou ON ou.org_id = o.id WHERE ou.user_id = '036803da-960f-40a6-851d-d673158a8de4'"))
        for row in result.all():
            print(row)

asyncio.run(main())
