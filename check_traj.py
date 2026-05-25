import json
from datetime import datetime, timezone, timedelta

BANGKOK_OFFSET = timedelta(hours=7)
now_bkk = datetime.now(timezone.utc) + BANGKOK_OFFSET
print(f"Current BKK time: {now_bkk.strftime('%H:%M:%S')}")

with open("trajectories.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total active trajectories: {len(data)}")
for t in data[:20]:  # first 20
    meta = t.get("meta", {})
    frames = t.get("frames", [])
    if not frames: continue
    print(f"Train {meta.get('train_number')} | {meta.get('origin_station')} -> {meta.get('destination_station')} | Delay: {meta.get('delay_minutes')} | Geom: {frames[0]['geom_fraction']}")
