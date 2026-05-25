import asyncio
from pathlib import Path
from app.infrastructure.parsers.raw_schedule_reader import _parse_raw_file

async def main():
    p = Path("/app/schedule/raw/northern_train111.json")
    if not p.exists():
        print(f"File {p} does not exist!")
        return
    train = _parse_raw_file(p)
    if train is None:
        print("Train 111 failed to parse!")
    else:
        print(f"Train 111 parsed successfully! {len(train.stops)} stops.")

asyncio.run(main())
