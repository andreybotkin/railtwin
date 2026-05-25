import json
with open("trajectories.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for t in data:
    meta = t.get("meta", {})
    frames = t.get("frames", [])
    if not frames: continue
    frac = frames[0].get("geom_fraction", 0)
    if frac >= 1.0 or frac <= 0.0:
        print(f"Train {meta.get('train_number')} | {meta.get('origin_station')} -> {meta.get('destination_station')} | Delay: {meta.get('delay_minutes')} | Geom: {frac}")
