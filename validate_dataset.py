import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


REQUIRED_TOP_LEVEL = {
    "timestamp",
    "session_id",
    "instance_id",
    "episode_id",
    "step_index",
    "terminal",
    "floor",
    "act",
    "screen_type",
    "action",
    "explanation",
    "state",
}

REQUIRED_STATE_KEYS = {
    "deck_card_ids",
    "relic_ids",
    "choice_available",
    "_decision_reason",
    "full_map",
}

SCREEN_ACTION_RULES = {
    "CARD_REWARD": ("choose_card_reward_", "skip_card_reward"),
    "COMBAT_REWARD": ("take_combat_reward_", "skip_combat_reward", "proceed_combat_reward"),
    "BOSS_REWARD": ("take_boss_reward_", "proceed"),
    "MAP": ("choose_map_node_", "choose_map_boss", "wait"),
    "REST": ("rest_", "proceed"),
    "SHOP_SCREEN": ("buy_card_", "buy_relic_", "shop_purge", "shop_leave"),
    "SHOP_ROOM": ("enter_shop", "proceed"),
    "EVENT": ("choose_event_", "proceed"),
    "CHEST": ("open_chest", "proceed"),
    "GRID": ("grid_select_", "proceed"),
    "HAND_SELECT": ("hand_select_", "proceed"),
    "GAME_OVER": ("proceed",),
    "COMPLETE": ("proceed",),
    "COMBAT": ("play_card_", "end_turn"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate STS bot JSONL training data.")
    parser.add_argument(
        "--data-dir",
        default="training_data",
        help="Root training_data directory or a specific session directory.",
    )
    parser.add_argument(
        "--session",
        default="",
        help="Optional explicit session id directory under --data-dir.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of records to inspect.",
    )
    return parser.parse_args()


def resolve_session_dir(data_dir: Path, session: str) -> Path:
    if session:
        session_dir = data_dir / session
        if not session_dir.exists():
            raise SystemExit(f"Session directory not found: {session_dir}")
        return session_dir

    if data_dir.is_dir() and any(p.suffix == ".jsonl" for p in data_dir.glob("*.jsonl")):
        return data_dir

    sessions = [p for p in data_dir.iterdir() if p.is_dir()]
    if not sessions:
        raise SystemExit(f"No session directories found under: {data_dir}")
    return max(sessions, key=lambda p: p.stat().st_mtime)


def iter_jsonl_records(session_dir: Path):
    for jsonl_path in sorted(session_dir.glob("*.jsonl")):
        if jsonl_path.name.endswith(".episodes.jsonl"):
            continue
        if jsonl_path.name == "training_table.jsonl":
            continue
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, start=1):
                yield jsonl_path, line_no, line.rstrip("\n")


def action_matches_screen(screen_type: str, action: str) -> bool:
    rules = SCREEN_ACTION_RULES.get(screen_type)
    if not rules:
        return True
    return any(action == rule or action.startswith(rule) for rule in rules)


def candidate_contains_action(candidates, action: str) -> bool:
    if not isinstance(candidates, list):
        return False
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("action") == action:
            return True
    return False


def detect_leakage(record: dict) -> list[str]:
    issues = []
    action = record.get("action", "")
    state = record.get("state", {})
    deck_ids = state.get("deck_card_ids", [])
    relic_ids = state.get("relic_ids", [])

    if action.startswith("choose_card_reward_"):
        reward_cards = state.get("reward_cards", [])
        try:
            idx = int(action.split("_")[-1])
        except ValueError:
            idx = -1
        if 0 <= idx < len(reward_cards):
            chosen = reward_cards[idx]
            chosen_id = ""
            if isinstance(chosen, dict):
                chosen_id = chosen.get("card_id", "")
            if chosen_id and deck_ids.count(chosen_id) > _starter_expected_count(chosen_id):
                issues.append(f"possible_card_reward_state_leak:{chosen_id}")

    if action.startswith("take_boss_reward_"):
        boss_relics = state.get("boss_relics", [])
        try:
            idx = int(action.split("_")[-1])
        except ValueError:
            idx = -1
        if 0 <= idx < len(boss_relics):
            chosen = boss_relics[idx]
            chosen_id = ""
            if isinstance(chosen, dict):
                chosen_id = chosen.get("relic_id", "")
            if chosen_id and chosen_id in relic_ids:
                issues.append(f"possible_boss_relic_state_leak:{chosen_id}")

    return issues


def _starter_expected_count(card_id: str) -> int:
    if card_id == "Strike_R":
        return 5
    if card_id == "Defend_R":
        return 4
    if card_id == "Bash":
        return 1
    return 0


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        raise SystemExit(f"Data directory does not exist: {data_dir}")

    session_dir = resolve_session_dir(data_dir, args.session)

    counts = Counter()
    screen_counts = Counter()
    action_counts = Counter()
    candidate_presence = Counter()
    issues: dict[str, list[str]] = defaultdict(list)

    previous_by_instance: dict[str, dict] = {}

    for index, (jsonl_path, line_no, line) in enumerate(iter_jsonl_records(session_dir), start=1):
        if args.limit and index > args.limit:
            break

        counts["records_seen"] += 1

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            issues["json_parse_error"].append(f"{jsonl_path.name}:{line_no}: {exc}")
            continue

        missing = sorted(REQUIRED_TOP_LEVEL - set(record))
        if missing:
            issues["missing_top_level"].append(f"{jsonl_path.name}:{line_no}: {','.join(missing)}")
            continue

        state = record.get("state")
        if not isinstance(state, dict):
            issues["state_not_object"].append(f"{jsonl_path.name}:{line_no}")
            continue

        missing_state = sorted(REQUIRED_STATE_KEYS - set(state))
        if missing_state:
            issues["missing_state_keys"].append(f"{jsonl_path.name}:{line_no}: {','.join(missing_state)}")

        screen_type = str(record.get("screen_type", ""))
        action = str(record.get("action", ""))
        instance_id = str(record.get("instance_id", ""))

        screen_counts[screen_type] += 1
        action_counts[action] += 1

        if not action_matches_screen(screen_type, action):
            issues["screen_action_mismatch"].append(
                f"{jsonl_path.name}:{line_no}: screen={screen_type} action={action}"
            )

        candidates = state.get("_decision_candidates")
        if candidates is not None:
            candidate_presence["with_candidates"] += 1
            if not candidate_contains_action(candidates, action):
                issues["chosen_action_missing_from_candidates"].append(
                    f"{jsonl_path.name}:{line_no}: action={action}"
                )
        else:
            candidate_presence["without_candidates"] += 1

        for leak in detect_leakage(record):
            issues["possible_state_leak"].append(f"{jsonl_path.name}:{line_no}: {leak}")

        previous = previous_by_instance.get(instance_id)
        if previous:
            prev_state = previous.get("state", {})
            prev_action = previous.get("action", "")
            prev_screen = previous.get("screen_type", "")
            if prev_screen == "CARD_REWARD" and prev_action.startswith("choose_card_reward_"):
                prev_deck = prev_state.get("deck_card_ids", [])
                curr_deck = state.get("deck_card_ids", [])
                if curr_deck == prev_deck:
                    issues["card_reward_not_reflected_next_state"].append(
                        f"{jsonl_path.name}:{line_no}: prev_action={prev_action}"
                    )

        previous_by_instance[instance_id] = record

    print(f"[session] {session_dir.name}")
    print(f"[records] {counts['records_seen']}")
    print(f"[candidates] with={candidate_presence['with_candidates']} without={candidate_presence['without_candidates']}")

    print("[top_screens]")
    for screen, count in screen_counts.most_common(10):
        print(f"  {screen}: {count}")

    print("[top_actions]")
    for action, count in action_counts.most_common(15):
        print(f"  {action}: {count}")

    print("[checks]")
    if not issues:
        print("  PASS: no validation issues found")
        return

    total_issues = sum(len(items) for items in issues.values())
    print(f"  FAIL: {total_issues} issue(s) across {len(issues)} category(ies)")
    for category, items in sorted(issues.items()):
        print(f"  - {category}: {len(items)}")
        for sample in items[:5]:
            print(f"    {sample}")


if __name__ == "__main__":
    main()
