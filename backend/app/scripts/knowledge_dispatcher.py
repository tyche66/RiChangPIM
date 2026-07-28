from __future__ import annotations

import argparse
import asyncio

from app.knowledge.jobs.runner import run_dispatcher_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch pending knowledge indexing jobs")
    parser.parse_args()
    asyncio.run(run_dispatcher_once())


if __name__ == "__main__":
    main()
