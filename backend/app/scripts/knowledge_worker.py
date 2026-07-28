from __future__ import annotations

import argparse
import asyncio

from app.knowledge.jobs.runner import run_worker_forever, run_worker_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the knowledge indexing worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    parser.add_argument("--worker-id", default=None, help="Explicit worker identifier")
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_worker_once(worker_id=args.worker_id))
        return
    asyncio.run(run_worker_forever(worker_id=args.worker_id))


if __name__ == "__main__":
    main()
