# RailDataCollector — Data Collection Notes

## Overview

This microservice collects and maintains railroad data for the backend.

## Data sources

| Data | Source | Frequency |
|---|---|---|
| Railroad network (routes + stations) | Local KML → Google My Maps (fallback) | Once at startup (if DB empty) |
| Train timetables | `schedule/schedules_seed.json` → TTS socket.io (fallback) | Daily at 03:00 Asia/Bangkok |
| Train delays | TTS socket.io (`ttsview.railway.co.th:5000`) | Every 30 minutes |

## Local data files

### Railroad network
`railroad/20260410RailwayMapofThailand.kml`  
KML export from Google My Maps. Used on first startup instead of downloading.

### Timetables
`schedule/schedules_seed.json`  
Bundled seed timetable with 16 SRT trains. Loaded when no daily scraped file exists.

`schedule/timetable_YYYYMMDD.json`  
Daily-scraped timetable files (created automatically after each successful remote fetch).

## Startup sequence

1. DB empty → load KML from local file (or download and cache it)
2. Kick off timetable update in background (loads from local seed or fetches remote)
3. Kick off initial delay fetch from TTS
4. Start APScheduler

## Manual triggers

```bash
# Trigger railroad re-initialization (force overwrite):
curl -X POST "http://localhost:8001/api/v1/collect/railroad?force=true"

# Trigger timetable update:
curl -X POST "http://localhost:8001/api/v1/collect/schedules"

# Trigger delay fetch:
curl -X POST "http://localhost:8001/api/v1/collect/delays"

# Check job status:
curl "http://localhost:8001/api/v1/status"
```

## Running locally (outside Docker)

```bash
cd raildatacollector
pip install -e .
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/railway_db" \
REDIS_URL="redis://localhost:6379/0" \
uvicorn app.main:app --port 8001 --reload
```
