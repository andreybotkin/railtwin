import json
with open("trajectories.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for t in data:
    if t.get("meta", {}).get("train_number") == "136":
        print(json.dumps(t.get("meta"), indent=2))
        print(json.dumps(t.get("frames", [])[0], indent=2))
        break
