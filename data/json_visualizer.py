import argparse
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


def print_overview(value, name="root", indent=0, max_depth=4, max_items=20):
    """Print a compact structure overview (types, counts, and sample keys)."""
    pad = "  " * indent
    if indent > max_depth:
        print(f"{pad}- {name}: (max depth reached)")
        return

    if isinstance(value, dict):
        keys = list(value.keys())
        print(f"{pad}- {name}: dict ({len(keys)} keys)")
        for key in keys[:max_items]:
            print_overview(value[key], key, indent + 1, max_depth, max_items)
        if len(keys) > max_items:
            print(f"{pad}  ... and {len(keys) - max_items} more keys")
    elif isinstance(value, list):
        print(f"{pad}- {name}: list ({len(value)} items)")
        for i, item in enumerate(value[:max_items]):
            print_overview(item, f"[{i}]", indent + 1, max_depth, max_items)
        if len(value) > max_items:
            print(f"{pad}  ... and {len(value) - max_items} more items")
    else:
        print(f"{pad}- {name}: {type(value).__name__}")

def print_shots(entry, max_shots=4):
    insights = entry.get("payload", {}).get("insights", {})
    shots = []
    for rally in insights.get("rallies", []):
        shots.extend(rally.get("shots", []))

    if not shots:
        print("No shots present")
        return

    for i, shot in enumerate(shots[:max_shots]):
        print(f"\nShot {i}")
        for k, v in shot.items():
            if isinstance(v, list):
                print(f"  - {k}: list ({len(v)} items)")
                for j, item in enumerate(v[:3]):
                    print(f"      [{j}]: {item}")
                if len(v) > 8:
                    print(f"      ... and {len(v) - 8} more items")
            elif isinstance(v, dict):
                print(f"  - {k}: dict ({len(v)} keys)")
                for dict_k, dict_v in list(v.items())[:3]:
                    print(f"      {dict_k}: {dict_v}")
                if len(v) > 8:
                    print(f"      ... and {len(v) - 8} more keys")
            else:
                print(f"  - {k}: {v}")

def print_highlights(entry, max_highlights=10):
    insights = entry.get("payload", {}).get("insights", {})
    highlights = insights.get("highlights", [])

    if not highlights:
        print("No highlights present")
        return

    print(f"Total highlights: {len(highlights)}")
    for i, highlight in enumerate(highlights[:max_highlights]):
        print(f"\nHighlight {i}")
        for k, v in highlight.items():
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
    
    if len(highlights) > max_highlights:
        print(f"\n... and {len(highlights) - max_highlights} more highlights")

def print_game_data(entry):
    insights = entry.get("payload", {}).get("insights", {})
    game_data = insights.get("game_data", {})

    if not game_data:
        print("No game_data present")
        return

    print(f"Game Data ({len(game_data)} keys)")
    for k, v in game_data.items():
        if isinstance(v, list):
            print(f"  - {k}: list ({len(v)} items)")
            for j, item in enumerate(v[:5]):
                if isinstance(item, dict):
                    print(f"      [{j}]: dict ({len(item)} keys)")
                    for dict_k, dict_v in list(item.items())[:3]:
                        print(f"          {dict_k}: {dict_v}")
                    if len(item) > 3:
                        print(f"          ... and {len(item) - 3} more keys")
                else:
                    print(f"      [{j}]: {item}")
            if len(v) > 5:
                print(f"      ... and {len(v) - 5} more items")
        elif isinstance(v, dict):
            print(f"  - {k}: dict ({len(v)} keys)")
            for dict_k, dict_v in v.items():
                print(f"      {dict_k}: {dict_v}")
        else:
            print(f"  - {k}: {v}")

def print_kitchen_arrival(entry, player_id=None):
    insights = entry.get("payload", {}).get("insights", {})
    players = insights.get("player_data", [])

    if not players:
        print("No player_data present")
        return

    if player_id is not None:
        players = [p for p in players if p.get("player_id") == player_id]
        if not players:
            print(f"No player_data found for player_id={player_id}")
            return

    for player in players:
        pid = player.get("player_id", "unknown")
        print(f"\nPlayer {pid}")
        for k, v in player.items():
            print(f"  - {k}: {v}")

def parse_args():
    parser = argparse.ArgumentParser(description="PB Vision JSON inspector")
    parser.add_argument("--json-path", default="data/stats/stats.json", help="Path to JSONL file")
    parser.add_argument("--overview", action="store_true", help="Print a structure overview")
    parser.add_argument("--shots", action="store_true", help="Print sample shots")
    parser.add_argument("--max-shots", type=int, default=4, help="Max shots to print")
    parser.add_argument("--highlights", action="store_true", help="Print highlights from insights")
    parser.add_argument("--max-highlights", type=int, default=10, help="Max highlights to print")
    parser.add_argument("--game-data", action="store_true", help="Print game data from insights")
    parser.add_argument(
        "--kitchen-arrival",
        action="store_true",
        help="Print kitchen arrival values from insights.player_data",
    )
    parser.add_argument("--player-id", type=int, help="Filter kitchen arrival by player_id")
    parser.add_argument("--max-depth", type=int, default=4, help="Max overview depth")
    parser.add_argument("--max-items", type=int, default=10, help="Max items per level")
    return parser.parse_args()

def main():
    args = parse_args()
    data = load_pbvision_json(args.json_path)

    print(f"Loaded {len(data)} PB Vision payloads")
    if not data:
        return

    entry = data[0]

    if args.kitchen_arrival:
        print_kitchen_arrival(entry, player_id=args.player_id)
        return

    if args.game_data:
        print_game_data(entry)
        return

    if args.highlights:
        print_highlights(entry, max_highlights=args.max_highlights)
        return

    if args.shots:
        print_shots(entry, max_shots=args.max_shots)
        return

    print("\nOverview of first entry")
    print_overview(entry, max_depth=args.max_depth, max_items=args.max_items)

if __name__ == "__main__":
    main()
