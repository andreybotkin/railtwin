"""Fetch all train timetables from thaitrainguide.com and save as schedules_seed.json.

Usage:
    python scripts/fetch_schedules.py [--output schedule/schedules_seed.json] [--raw-dir schedule/raw]

The script probes https://www.thaitrainguide.com/timetable/{line}/train{N}.json
for N in 1..999 across five rail lines, downloads found JSON files, converts
them to the internal timetable format and writes a single schedules_seed.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import date, datetime
from pathlib import Path

import aiohttp

BASE_URL = "https://www.thaitrainguide.com/timetable"

LINES = ["northern", "northeastern", "southern", "eastern", "western"]

# Probe ranges known to contain trains per line (wide → avoids missing any)
PROBE_RANGES: dict[str, list[tuple[int, int]]] = {
    "northern": [(1, 50), (101, 170)],
    "northeastern": [(1, 90), (101, 250), (400, 460)],
    "southern": [(31, 90), (167, 260), (420, 490)],
    "eastern": [(270, 300), (360, 400), (990, 999)],
    "western": [(1, 30), (420, 440)],
}

CONCURRENT = 12  # parallel HTTP requests
TIMEOUT = 15  # seconds per request
DELAY_SEC = 0.05  # polite pause between batches


# ──────────────────────────────────────────────────────────────────────────── #
# Time helpers                                                                  #
# ──────────────────────────────────────────────────────────────────────────── #


def _time_to_minutes(t: str | None) -> int | None:
    """HH:MM → total minutes, or None."""
    if not t or t.strip() == "-":
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})$", t.strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _compute_day_offsets(stops: list[dict]) -> list[dict]:
    """
    Fill arrival_day_offset / departure_day_offset.
    Walk stops in order; whenever the next "raw" time (HH:MM minutes, 0–1439)
    jumps *earlier* than the previous raw time by more than 60 minutes we
    assume a midnight crossing and bump the offset.  We always compare raw
    times (not offset-adjusted), so a single midnight crossing produces
    exactly +1 regardless of how many stops follow it.
    """
    result = []
    offset = 0
    prev_raw: int | None = None  # raw minutes of the previous reference time

    for s in stops:
        arr_str = s.get("arrival")
        dep_str = s.get("departure")

        arr_min = _time_to_minutes(arr_str)
        dep_min = _time_to_minutes(dep_str)

        # Use arrival as reference when available, else departure
        cur_raw = arr_min if arr_min is not None else dep_min

        if prev_raw is not None and cur_raw is not None:
            if cur_raw < prev_raw - 60:
                offset += 1

        result.append(
            {
                "arrival": arr_str,
                "departure": dep_str,
                "arr_day_offset": offset if arr_min is not None else 0,
                "dep_day_offset": offset if dep_min is not None else 0,
            }
        )

        if cur_raw is not None:
            prev_raw = cur_raw

    return result


# ──────────────────────────────────────────────────────────────────────────── #
# Train type / name helpers                                                     #
# ──────────────────────────────────────────────────────────────────────────── #


def _classify_train(name: str, train_number: int) -> str:
    n = name.lower()
    if "special express" in n:
        return "special_express"
    if "express" in n:
        return "express"
    if "rapid" in n:
        return "rapid"
    if "local" in n or "ordinary" in n or "commuter" in n:
        return "ordinary"
    # Fallback by number convention
    if train_number <= 50:
        return "special_express"
    if train_number <= 100:
        return "express"
    if train_number <= 200:
        return "rapid"
    return "ordinary"


# ──────────────────────────────────────────────────────────────────────────── #
# Conversion: thaitrainguide JSON → internal format                             #
# ──────────────────────────────────────────────────────────────────────────── #


def _convert(line: str, number: int, raw: dict) -> dict:
    name = raw.get("name", f"Train {number}")
    timetable = raw.get("timetable", [])
    notes = raw.get("notes", [])
    link = raw.get("link", "")

    offsets = _compute_day_offsets(timetable)
    schedules = []
    for seq, (stop, off) in enumerate(zip(timetable, offsets)):
        arr = off["arrival"]
        dep = off["departure"]
        schedules.append(
            {
                "sequence": seq,
                "station_name": stop["station"],
                "arrival_time": None if arr in (None, "-") else arr,
                "departure_time": None if dep in (None, "-") else dep,
                "arrival_day_offset": off["arr_day_offset"],
                "departure_day_offset": off["dep_day_offset"],
                "day_of_week": list(range(7)),
            }
        )

    return {
        "train_number": str(number),
        "train_type": _classify_train(name, number),
        "name": name,
        "route_type": line,
        "operator": "State Railway of Thailand",
        "source_url": link,
        "service_notes": {"notes": notes} if notes else None,
        "schedules": schedules,
    }


# ──────────────────────────────────────────────────────────────────────────── #
# HTTP fetcher                                                                  #
# ──────────────────────────────────────────────────────────────────────────── #


async def _fetch_train(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    line: str,
    number: int,
    raw_dir: Path | None,
) -> dict | None:
    url = f"{BASE_URL}/{line}/train{number}.json"
    async with sem:
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    return None
                raw: dict = await resp.json(content_type=None)
        except Exception:
            return None

    # Validate minimal structure
    if "timetable" not in raw or not raw["timetable"]:
        return None

    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"{line}_train{number}.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return _convert(line, number, raw)


async def _fetch_line(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    line: str,
    raw_dir: Path | None,
    verbose: bool,
) -> list[dict]:
    ranges = PROBE_RANGES.get(line, [(1, 100)])
    numbers = []
    for lo, hi in ranges:
        numbers.extend(range(lo, hi + 1))

    found: list[dict] = []
    total = len(numbers)
    for i in range(0, total, CONCURRENT):
        batch = numbers[i : i + CONCURRENT]
        tasks = [_fetch_train(session, sem, line, n, raw_dir) for n in batch]
        results = await asyncio.gather(*tasks)
        for n, train in zip(batch, results):
            if train is not None:
                found.append(train)
                if verbose:
                    print(f"  ✓ {line}/train{n}  — {train['name']}")
        await asyncio.sleep(DELAY_SEC)

    return found


def _load_from_raw(raw_dir: Path, verbose: bool) -> list[dict]:
    """Reconstruct train list from already-downloaded raw JSON files."""
    all_trains: list[dict] = []
    import re as _re

    pat = _re.compile(r"^(.+)_train(\d+)\.json$")
    for p in sorted(raw_dir.glob("*.json")):
        m = pat.match(p.name)
        if not m:
            continue
        line, number = m.group(1), int(m.group(2))
        raw = json.loads(p.read_text(encoding="utf-8"))
        if "timetable" not in raw or not raw["timetable"]:
            continue
        train = _convert(line, number, raw)
        all_trains.append(train)
        if verbose:
            print(f"  ✓ {line}/train{number}  — {train['name']}")
    return all_trains


async def run(
    output: Path, raw_dir: Path | None, verbose: bool, from_raw: bool = False
) -> None:
    all_trains: list[dict] = []

    if from_raw and raw_dir and raw_dir.exists():
        print(f"[Re-converting from {raw_dir}]")
        all_trains = _load_from_raw(raw_dir, verbose)
    else:
        sem = asyncio.Semaphore(CONCURRENT)
        headers = {
            "User-Agent": "raildatacollector/1.0 (github.com/andreybotkin/railtwin)"
        }
        connector = aiohttp.TCPConnector(limit=CONCURRENT)

        async with aiohttp.ClientSession(
            headers=headers, connector=connector
        ) as session:
            for line in LINES:
                if verbose:
                    print(f"\n[{line.upper()}]")
                trains = await _fetch_line(session, sem, line, raw_dir, verbose)
                all_trains.extend(trains)
                if verbose:
                    print(f"  → {len(trains)} trains found")

    payload = {
        "version": date.today().isoformat(),
        "source": "thaitrainguide.com (scraped)",
        "fetched_at": datetime.now(tz=__import__("datetime").timezone.utc).isoformat(),
        "description": (
            "All available train timetables from thaitrainguide.com. "
            "Station names as published by Richard Barrow."
        ),
        "trains": all_trains,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nSaved {len(all_trains)} trains → {output}")


# ──────────────────────────────────────────────────────────────────────────── #
# CLI                                                                           #
# ──────────────────────────────────────────────────────────────────────────── #


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path(__file__).parent.parent / "schedule" / "schedules_seed.json",
        help="Output JSON file (default: schedule/schedules_seed.json)",
    )
    p.add_argument(
        "--raw-dir",
        "-r",
        type=Path,
        default=Path(__file__).parent.parent / "schedule" / "raw",
        help="Directory to save raw per-train JSON files (default: schedule/raw/). Pass empty string to disable.",
    )
    p.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress per-train output",
    )
    p.add_argument(
        "--from-raw",
        action="store_true",
        help="Re-convert from already-downloaded raw files (no network requests)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    raw_dir = args.raw_dir if str(args.raw_dir) else None
    asyncio.run(
        run(
            output=args.output,
            raw_dir=raw_dir,
            verbose=not args.quiet,
            from_raw=args.from_raw,
        )
    )
