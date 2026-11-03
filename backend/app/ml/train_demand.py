"""Train/evaluate from a business's real sales history outside the request path."""

import argparse
import asyncio
import json
from uuid import UUID

from app.db.session import SessionFactory
from app.services.forecasting import ForecastingService


async def run(business_id: UUID, product_id: UUID, actor_id: UUID | None) -> dict:
    async with SessionFactory() as session:
        return await ForecastingService(session).train(business_id, actor_id, product_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--business-id", required=True, type=UUID)
    parser.add_argument("--product-id", required=True, type=UUID)
    parser.add_argument("--actor-id", type=UUID, help="Optional user UUID for audit attribution")
    args = parser.parse_args()
    report = asyncio.run(run(args.business_id, args.product_id, args.actor_id))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
