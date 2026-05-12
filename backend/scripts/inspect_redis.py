"""Read-only: list orgconfig keys in Redis to verify caching state."""
import asyncio
import redis.asyncio as redis_async


async def main():
    client = await redis_async.from_url("redis://redis:6379/0", decode_responses=True)
    keys = await client.keys("orgconfig:*")
    print(f"orgconfig:* keys in Redis: {keys}")
    for k in keys:
        ttl = await client.ttl(k)
        val_len = await client.strlen(k)
        print(f"  {k}: ttl={ttl}s, value_size={val_len} bytes")
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
