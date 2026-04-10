"""TTS (Train Tracking System) delay scraper.

Connects to the State Railway of Thailand real-time tracking system at
https://ttsview.railway.co.th:5000 via Socket.IO to fetch current train
delay data and stores it in Redis under the key shared with the backend
simulation service.

Adapted from backend/app/services/tts_scraper.py.
"""

import asyncio
import contextlib
from typing import Any

import socketio

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def fetch_tts_delays() -> dict[str, int] | None:
    """Fetch real-time train delay data from TTS via Socket.IO.

    Returns:
        Dict mapping train_code -> delay_minutes, or None on connection failure.
    """
    sio = socketio.AsyncClient(
        ssl_verify=False,
        logger=False,
        engineio_logger=False,
    )
    result: dict[str, int] | None = None
    done = asyncio.Event()

    @sio.event
    async def connect() -> None:
        nonlocal result
        logger.info("TTS Socket.IO connected")
        try:
            data = await sio.call("ttsMain", timeout=30)
            result = _parse_delays(data)
            logger.info(
                "TTS delays fetched",
                total=len(data) if isinstance(data, list) else "?",
                delayed=len(result) if result else 0,
            )
        except Exception as exc:
            logger.warning("TTS ttsMain call failed", error=str(exc))
        finally:
            done.set()

    @sio.event
    async def connect_error(data: Any) -> None:
        logger.warning("TTS connection error", data=str(data))
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
    except TimeoutError:
        logger.warning("TTS Socket.IO timed out")
    except Exception as exc:
        logger.warning("TTS Socket.IO connection failed", error=str(exc))
    finally:
        with contextlib.suppress(Exception):
            await sio.disconnect()

    return result


def _parse_delays(data: Any) -> dict[str, int]:
    delays: dict[str, int] = {}

    if not isinstance(data, list):
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        else:
            logger.warning(
                "Unexpected TTS response format", data_type=type(data).__name__
            )
            return delays

    for item in data:
        if not isinstance(item, dict):
            continue
        train_code = str(item.get("train_code", "")).strip()
        if not train_code:
            continue
        delay = item.get("act_dep_late") or item.get("act_arr_late") or 0
        try:
            delay_minutes = int(delay)
        except (ValueError, TypeError):
            delay_minutes = 0
        if delay_minutes > 0:
            delays[train_code] = delay_minutes

    return delays
