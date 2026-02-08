import json
def load_pbvision_json(path):
    objects = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            objects.append(json.loads(line))
    return objects


JSON_PATH = "data/stats.json"
data = load_pbvision_json(JSON_PATH)

print(f"Loaded {len(data)} PB Vision payloads")

entry = data[0]
insights = entry["payload"]["insights"]

shots = []
for rally in insights.get("rallies", []):
    shots.extend(rally.get("shots", []))

if not shots:
    print("❌ No shots present")
else:
    for i, shot in enumerate(shots[:4]):
        print(f"\n📌 Shot {i}")
        for k, v in shot.items():
            if isinstance(v, list):
                print(f"  - {k}: list ({len(v)} items)")
                for j, item in enumerate(v[:3]):
                    print(f"      [{j}]: {item}")
                if len(v) > 3:
                    print(f"      ... and {len(v) - 3} more items")
            elif isinstance(v, dict):
                print(f"  - {k}: dict ({len(v)} keys)")
                for dict_k, dict_v in list(v.items())[:3]:
                    print(f"      {dict_k}: {dict_v}")
                if len(v) > 3:
                    print(f"      ... and {len(v) - 3} more keys")
            else:
                print(f"  - {k}: {v}")
