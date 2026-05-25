import asyncio
from pathlib import Path

from app.infrastructure.parsers.raw_schedule_reader import _parse_raw_file


async def main():
    p = Path("/app/schedule/raw/northern_train111.json")
    if not p.exists():
        return
    train = _parse_raw_file(p)
    if train is None:
        pass
    else:
        pass

asyncio.run(main())
