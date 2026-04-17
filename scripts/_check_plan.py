"""Ad-hoc check for Fase 1b: verify businesses.plan column + business_subscriptions table."""
import asyncio, asyncpg, os, json


async def main():
    c = await asyncpg.connect(os.environ["DATABASE_PUBLIC_URL"])
    try:
        r1 = await c.fetch(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='businesses' "
            "AND column_name IN ('plan','plan_type','subscription_plan')"
        )
        r2 = await c.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables "
            "WHERE table_name='business_subscriptions')"
        )
        r3 = []
        if any(row["column_name"] == "plan" for row in r1):
            r3 = await c.fetch(
                "SELECT plan FROM businesses WHERE slug='xcleaners-demo'"
            )
        print(json.dumps({
            "businesses_plan_cols": [dict(x) for x in r1],
            "business_subscriptions_table_exists": r2,
            "xcleaners_demo_plan": [dict(x) for x in r3],
        }, indent=2, default=str))
    finally:
        await c.close()


asyncio.run(main())
