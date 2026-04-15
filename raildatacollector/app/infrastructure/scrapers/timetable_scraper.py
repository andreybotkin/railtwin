"""Timetable scraper for State Railway of Thailand.

Data source priority:
  1. Today's cached timetable file  (schedule/timetable_YYYYMMDD.json)
  2. Most recent cached timetable file
  3. Bundled seed file               (schedule/schedules_seed.json)
  4. TTS socket.io  — ttsTimetable event (may not be available on all servers)
  5. Empty result   — logged as a warning; data consumers fall back to DB state

On a successful remote fetch the result is saved to
  schedule/timetable_YYYYMMDD.json
so subsequent restarts within the same day are served from disk.
"""

import asyncio
import contextlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import socketio

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.schedule.entities import ScheduleStopData, TrainData

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Local file helpers                                                            #
# --------------------------------------------------------------------------- #


def _find_latest_local_schedule() -> Path | None:
    d = settings.schedule_data_dir
    if not d.exists():
        return None

    today_str = date.today().strftime("%Y%m%d")
    today_file = d / f"timetable_{today_str}.json"
    if today_file.exists():
        return today_file

    scraped = sorted(d.glob("timetable_*.json"), reverse=True)
    if scraped:
        return scraped[0]

    seed = d / "schedules_seed.json"
    if seed.exists():
        return seed

    return None


def _load_trains_from_json(path: Path) -> list[TrainData]:
    data = json.loads(path.read_text(encoding="utf-8"))
    trains: list[TrainData] = []
    for t in data.get("trains", []):
        stops = [
            ScheduleStopData(
                station_name=s["station_name"],
                sequence=s["sequence"],
                arrival_time=s.get("arrival_time"),
                departure_time=s.get("departure_time"),
                arrival_day_offset=s.get("arrival_day_offset", 0),
                departure_day_offset=s.get("departure_day_offset", 0),
                day_of_week=s.get("day_of_week", list(range(7))),
                platform=s.get("platform"),
                distance_from_origin_km=s.get("distance_from_origin_km"),
            )
            for s in t.get("schedules", [])
        ]
        trains.append(
            TrainData(
                train_number=str(t["train_number"]),
                train_type=t["train_type"],
                route_type=t.get("route_type", "other"),
                name=t.get("name"),
                operator=t.get("operator", "State Railway of Thailand"),
                source="local_cache",
                source_url=str(path),
                service_notes=t.get("service_notes"),
                stops=stops,
            )
        )
    return trains


def _save_timetable_cache(trains: list[TrainData]) -> None:
    d = settings.schedule_data_dir
    d.mkdir(parents=True, exist_ok=True)
    today_str = date.today().strftime("%Y%m%d")
    path = d / f"timetable_{today_str}.json"
    payload = {
        "version": today_str,
        "source": "tts_timetable",
        "fetched_at": datetime.utcnow().isoformat(),
        "trains": [
            {
                "train_number": t.train_number,
                "train_type": t.train_type,
                "route_type": t.route_type,
                "name": t.name,
                "operator": t.operator,
                "source": t.source,
                "schedules": [
                    {
                        "station_name": s.station_name,
                        "sequence": s.sequence,
                        "arrival_time": s.arrival_time,
                        "departure_time": s.departure_time,
                        "arrival_day_offset": s.arrival_day_offset,
                        "departure_day_offset": s.departure_day_offset,
                        "day_of_week": s.day_of_week,
                        "platform": s.platform,
                        "distance_from_origin_km": s.distance_from_origin_km,
                    }
                    for s in t.stops
                ],
            }
            for t in trains
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Timetable cached to disk", path=str(path), trains=len(trains))


# --------------------------------------------------------------------------- #
# Remote TTS socket.io fetch                                                   #
# --------------------------------------------------------------------------- #


async def _fetch_tts_timetable() -> list[TrainData] | None:
    """Attempt to query the TTS socket.io server for timetable data.

    The TTS server may expose a 'ttsTimetable' event in addition to the
    standard 'ttsMain' delay event.  We attempt the call and return None
    if unavailable so the caller can fall back to a local file.
    """
    sio = socketio.AsyncClient(ssl_verify=False, logger=False, engineio_logger=False)
    raw_result: list[dict] | None = None
    done = asyncio.Event()

    @sio.event
    async def connect() -> None:
        nonlocal raw_result
        try:
            data = await sio.call("ttsTimetable", timeout=30)
            if isinstance(data, (list, dict)):
                raw_result = data if isinstance(data, list) else [data]
                logger.info("TTS timetable event returned data", count=len(raw_result))
        except Exception as exc:
            logger.debug("ttsTimetable event not available", error=str(exc))
        finally:
            done.set()

    @sio.event
    async def connect_error(data: Any) -> None:
        done.set()

    try:
        await sio.connect(
            settings.tts_server_url,
            transports=["websocket"],
            headers={
                "Origin": "https://ttsview.railway.co.th",
                "Referer": "https://ttsview.railway.co.th/v3/",
            },
            wait_timeout=15,
        )
        await asyncio.wait_for(done.wait(), timeout=40)
    except Exception as exc:
        logger.debug("TTS timetable connection failed", error=str(exc))
    finally:
        with contextlib.suppress(Exception):
            await sio.disconnect()

    if not raw_result:
        return None

    return _parse_tts_timetable(raw_result)


def _parse_tts_timetable(data: list[dict]) -> list[TrainData]:
    trains: dict[str, TrainData] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        train_code = str(item.get("train_code", "")).strip()
        if not train_code:
            continue
        if train_code not in trains:
            trains[train_code] = TrainData(
                train_number=train_code,
                train_type=_infer_train_type(train_code),
                route_type="other",
                source="tts_timetable",
                source_url=settings.tts_server_url,
                stops=[],
            )
        station_name = str(
            item.get("sta_name_en") or item.get("sta_name_th") or ""
        ).strip()
        if station_name:
            seq = int(item.get("seq", len(trains[train_code].stops)))
            trains[train_code].stops.append(
                ScheduleStopData(
                    station_name=station_name,
                    sequence=seq,
                    departure_time=item.get("dep_time") or item.get("sch_dep"),
                    arrival_time=item.get("arr_time") or item.get("sch_arr"),
                )
            )
    return list(trains.values())


def _infer_train_type(train_number: str) -> str:
    try:
        n = int(train_number)
        if n <= 20:
            return "special_express"
        if n <= 100:
            return "express"
        if n <= 200:
            return "rapid"
        return "ordinary"
    except ValueError:
        return "ordinary"


# --------------------------------------------------------------------------- #
# Public entry point                                                            #
# --------------------------------------------------------------------------- #


async def fetch_timetable() -> list[TrainData]:
    """Return a list of TrainData with full schedule stops.

    Sources are tried in priority order: local cache → TTS remote.
    An empty list is returned only when all sources fail.
    """
    local_path = _find_latest_local_schedule()
    if local_path:
        logger.info("Loading timetable from local file", path=str(local_path))
        try:
            trains = _load_trains_from_json(local_path)
            if trains:
                logger.info("Timetable loaded from local cache", trains=len(trains))
                return trains
        except Exception as exc:
            logger.warning("Failed to parse local timetable file", error=str(exc))

    logger.info("Attempting remote TTS timetable fetch")
    tts_trains = await _fetch_tts_timetable()
    if tts_trains:
        _save_timetable_cache(tts_trains)
        return tts_trains

    logger.warning(
        "No timetable data available from any source; "
        "existing schedule data in the database will be preserved"
    )
    return []
