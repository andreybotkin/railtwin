"""TTS (Train Tracking System) Scraper Service.

Connects to the State Railway of Thailand real-time tracking system
via Socket.IO to fetch live train delay data. Runs hourly and stores
delay corrections in Redis for use by the simulation service.
"""

import asyncio
import contextlib
import json
from typing import Any

import socketio
from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger(__name__)

TTS_SERVER_URL = "https://ttsview.railway.co.th:5000"
TTS_EVENT_MAIN = "ttsMain"
REDIS_DELAYS_KEY = "tts:train_delays"
REDIS_DELAYS_TTL = 7200  # 2 hours


async def fetch_tts_delays() -> dict[str, int] | None:
    """Fetch real-time train delay data from TTS via Socket.IO.

    Connects to the State Railway of Thailand tracking system,
    emits the ttsMain event, and parses the returned train data
    to extract delay information.

    Returns:
        Dict mapping train_code -> delay_minutes, or None on failure.
    """
    sio = socketio.AsyncClient(
        ssl_verify=False,
        logger=False,
        engineio_logger=False,
    )
    result: dict[str, int] | None = None
    done_event = asyncio.Event()

    @sio.event
    async def connect() -> None:
        logger.info("TTS Socket.IO connected")
        try:
            data = await sio.call(TTS_EVENT_MAIN, timeout=30)
            nonlocal result
            result = _parse_tts_data(data)
            logger.info(
                "TTS data fetched",
                train_count=len(result) if result else 0,
            )
        except Exception as exc:  # noqa: BLE001 - external Socket.IO callback boundary
            logger.warning("Failed to call ttsMain", error=str(exc))
        finally:
            done_event.set()

    @sio.event
    async def connect_error(data: Any) -> None:
        logger.warning("TTS connection error", data=str(data))
        done_event.set()

    try:
        await sio.connect(
            TTS_SERVER_URL,
            transports=["websocket"],
            headers={
                "Origin": "https://ttsview.railway.co.th",
                "Referer": "https://ttsview.railway.co.th/v3/",
            },
            wait_timeout=15,
        )
        await asyncio.wait_for(done_event.wait(), timeout=40)
    except TimeoutError:
        logger.warning("TTS Socket.IO timed out")
    except Exception as exc:  # noqa: BLE001 - external Socket.IO client boundary
        logger.warning("TTS Socket.IO error", error=str(exc))
    finally:
        with contextlib.suppress(Exception):
            await sio.disconnect()

    return result


def _parse_tts_data(data: Any) -> dict[str, int]:
    """Parse raw TTS data into train_code -> delay_minutes mapping.

    The TTS API returns a list of train objects with fields:
    - train_code: Train number as shown on timetables
    - act_arr_late: Actual arrival delay in minutes
    - act_dep_late: Actual departure delay in minutes
    - delay_cause_th / delay_cause_en: Reason for delay

    Args:
        data: Raw data from ttsMain Socket.IO callback.

    Returns:
        Dict mapping train_code to delay in minutes.
    """
    delays: dict[str, int] = {}

    if not isinstance(data, list):
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        else:
            logger.warning("Unexpected TTS data format", data_type=type(data).__name__)
            return delays

    for item in data:
        if not isinstance(item, dict):
            continue
        train_code = str(item.get("train_code", "")).strip()
        if not train_code:
            continue
        # Prefer departure delay, fall back to arrival delay
        delay = item.get("act_dep_late") or item.get("act_arr_late") or 0
        try:
            delay_minutes = int(delay)
        except (ValueError, TypeError):
            delay_minutes = 0
        # Keep both delays and early departures so simulation reflects
        # the actual running state against the timetable.
        if delay_minutes != 0:
            delays[train_code] = delay_minutes

    return delays


async def store_delays_in_redis(
    redis_client: Redis,
    delays: dict[str, int],
) -> None:
    """Store train delays in Redis for retrieval by simulation service.

    Args:
        redis_client: Async Redis client.
        delays: Dict mapping train_code to delay_minutes.
    """
    await redis_client.set(
        REDIS_DELAYS_KEY,
        json.dumps(delays),
        ex=REDIS_DELAYS_TTL,
    )
    logger.info("Stored TTS delays in Redis", count=len(delays))


async def get_delays_from_redis(redis_client: Redis) -> dict[str, int]:
    """Retrieve stored train delays from Redis.

    Args:
        redis_client: Async Redis client.

    Returns:
        Dict mapping train_code to delay_minutes, empty if not cached.
    """
    try:
        raw = await redis_client.get(REDIS_DELAYS_KEY)
        if raw:
            data: dict[str, int] = json.loads(raw)
            return data
    except Exception as exc:  # noqa: BLE001 - Redis cache failure is non-fatal
        logger.warning("Failed to read TTS delays from Redis", error=str(exc))
    return {}


async def run_tts_scraper_once(redis_client: Redis) -> None:
    """Fetch TTS delays and store them in Redis (single run).

    Args:
        redis_client: Async Redis client.
    """
    logger.info("Starting TTS scraper run")
    delays = await fetch_tts_delays()
    if delays is not None:
        await store_delays_in_redis(redis_client, delays)
    else:
        logger.warning("TTS scraper returned no data; keeping previous cached value")


async def tts_scraper_loop(redis_client: Redis, interval_seconds: int = 3600) -> None:
    """Periodic loop that fetches TTS delays every interval_seconds.

    Starts an immediate fetch, then repeats on the given interval.

    Args:
        redis_client: Async Redis client.
        interval_seconds: Interval between fetches (default: 1 hour).
    """
    while True:
        try:
            await run_tts_scraper_once(redis_client)
        except Exception as exc:
            logger.error("TTS scraper loop error", error=str(exc), exc_info=exc)
        await asyncio.sleep(interval_seconds)
