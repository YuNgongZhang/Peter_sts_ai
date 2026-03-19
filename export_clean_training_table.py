import argparse
import json
from collections import Counter
from pathlib import Path

from export_training_table import (
    build_training_record,
    iter_step_records,
    load_episode_summaries,
    resolve_session_dir,
)


MECHANICAL_SCREENS = {"GAME_OVER", "COMPLETE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean STS training traces into behavior-cloning-ready JSONL tables."
    )
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
        "--all-output",
        default="",
        help="Optional output path for the cleaned all-screen table.",
    )
    parser.add_argument(
        "--noncombat-output",
        default="",
        help="Optional output path for the cleaned non-combat table.",
    )
    parser.add_argument(
        "--report-output",
        default="",
        help="Optional output path for the dataset report.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of raw step records to inspect.",
    )
    return parser.parse_args()


def _card_ids(cards) -> list[str]:
    ids: list[str] = []
    if not isinstance(cards, list):
        return ids
    for card in cards:
        if isinstance(card, dict):
            card_id = card.get("card_id")
            if isinstance(card_id, str) and card_id:
                ids.append(card_id)
    return ids


def _relic_ids(relics) -> list[str]:
    ids: list[str] = []
    if not isinstance(relics, list):
        return ids
    for relic in relics:
        if isinstance(relic, dict):
            relic_id = relic.get("relic_id")
            if isinstance(relic_id, str) and relic_id:
                ids.append(relic_id)
    return ids


def _potion_ids(potions) -> list[str]:
    ids: list[str] = []
    if not isinstance(potions, list):
        return ids
    for potion in potions:
        if isinstance(potion, dict):
            potion_id = potion.get("potion_id")
            if isinstance(potion_id, str) and potion_id:
                ids.append(potion_id)
    return ids


def _reward_types(rewards) -> list[str]:
    reward_types: list[str] = []
    if not isinstance(rewards, list):
        return reward_types
    for reward in rewards:
        if isinstance(reward, dict):
            reward_type = reward.get("reward_type")
            if isinstance(reward_type, dict):
                reward_type = reward_type.get("name")
            if isinstance(reward_type, str) and reward_type:
                reward_types.append(reward_type)
    return reward_types


def _normalize_candidates(candidates) -> list[dict]:
    normalized = []
    if not isinstance(candidates, list):
        return normalized
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        normalized.append(
            {
                "action": candidate.get("action"),
                "score": candidate.get("score"),
                "reason": candidate.get("reason"),
            }
        )
    return normalized


def _starter_expected_count(card_id: str) -> int:
    if card_id == "Strike_R":
        return 5
    if card_id == "Defend_R":
        return 4
    if card_id == "Bash":
        return 1
    return 0


def _detect_state_leak(record: dict) -> str | None:
    state = record.get("state", {}) if isinstance(record.get("state"), dict) else {}
    action = str(record.get("action", ""))
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
            if isinstance(chosen, dict):
                chosen_id = str(chosen.get("card_id", ""))
                if chosen_id and deck_ids.count(chosen_id) > _starter_expected_count(chosen_id):
                    return f"possible_state_leak:card_reward:{chosen_id}"

    if action.startswith("take_boss_reward_"):
        boss_relics = state.get("boss_relics", [])
        try:
            idx = int(action.split("_")[-1])
        except ValueError:
            idx = -1
        if 0 <= idx < len(boss_relics):
            chosen = boss_relics[idx]
            if isinstance(chosen, dict):
                chosen_id = str(chosen.get("relic_id", ""))
                if chosen_id and chosen_id in relic_ids:
                    return f"possible_state_leak:boss_relic:{chosen_id}"

    return None


def _clean_state_features(state: dict) -> dict:
    return {
        "player_hp": state.get("player_hp"),
        "current_hp": state.get("current_hp"),
        "max_hp": state.get("max_hp"),
        "gold": state.get("gold"),
        "energy": state.get("energy"),
        "turn": state.get("turn"),
        "in_combat": state.get("in_combat"),
        "room_phase": state.get("room_phase"),
        "room_type": state.get("room_type"),
        "character": state.get("character"),
        "seed": state.get("seed"),
        "enemy_intent": state.get("enemy_intent"),
        "choice_available": state.get("choice_available"),
        "potions_full": state.get("potions_full"),
        "boss_available": state.get("boss_available"),
        "act_boss": state.get("act_boss"),
        "map_nodes": state.get("map_nodes"),
        "map_current_node": state.get("map_current_node"),
        "full_map": state.get("full_map"),
        "deck_card_ids": state.get("deck_card_ids", []),
        "relic_ids": state.get("relic_ids", []),
        "hand": state.get("hand", []),
        "reward_card_ids": _card_ids(state.get("reward_cards")),
        "reward_types": _reward_types(state.get("combat_rewards")),
        "boss_relic_ids": _relic_ids(state.get("boss_relics")),
        "shop_card_ids": _card_ids(state.get("shop_cards")),
        "shop_relic_ids": _relic_ids(state.get("shop_relics")),
        "shop_potion_ids": _potion_ids(state.get("shop_potions")),
        "grid_card_ids": _card_ids(state.get("grid_cards")),
        "hand_select_card_ids": _card_ids(state.get("hand_select_cards")),
        "grid_num_cards": state.get("grid_num_cards"),
        "hand_select_num": state.get("hand_select_num"),
        "card_reward_can_skip": state.get("card_reward_can_skip"),
        "card_reward_can_bowl": state.get("card_reward_can_bowl"),
        "purge_available": state.get("purge_available"),
        "purge_cost": state.get("purge_cost"),
        "has_rested": state.get("has_rested"),
        "for_upgrade": state.get("for_upgrade"),
        "for_purge": state.get("for_purge"),
        "event_id": state.get("event_id"),
    }


def _clean_record(record: dict) -> dict:
    state = record.get("state", {}) if isinstance(record.get("state"), dict) else {}
    return {
        "timestamp": record.get("timestamp"),
        "session_id": record.get("session_id"),
        "instance_id": record.get("instance_id"),
        "episode_id": record.get("episode_id"),
        "step_index": record.get("step_index"),
        "terminal": record.get("terminal"),
        "screen_type": record.get("screen_type"),
        "floor": record.get("floor"),
        "act": record.get("act"),
        "action": record.get("action"),
        "state_features": _clean_state_features(state),
        "decision_metadata": {
            "decision_reason": record.get("decision_reason"),
            "candidate_actions": _normalize_candidates(record.get("candidate_actions")),
            "candidate_count": len(_normalize_candidates(record.get("candidate_actions"))),
        },
        "outcome": record.get("outcome", {}),
    }


def _is_noncombat(record: dict) -> bool:
    return str(record.get("screen_type")) != "COMBAT"


def _drop_reason(record: dict) -> str | None:
    screen_type = str(record.get("screen_type", ""))
    if screen_type in MECHANICAL_SCREENS:
        return f"mechanical_screen:{screen_type}"
    leak_reason = _detect_state_leak(record)
    if leak_reason:
        return leak_reason
    return None


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", errors="backslashreplace") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")


def _build_report(
    session_dir: Path,
    raw_count: int,
    kept_all: list[dict],
    kept_noncombat: list[dict],
    drop_reasons: Counter,
) -> str:
    all_screen_counts = Counter(str(record.get("screen_type", "")) for record in kept_all)
    all_action_counts = Counter(str(record.get("action", "")) for record in kept_all)
    noncombat_screen_counts = Counter(str(record.get("screen_type", "")) for record in kept_noncombat)

    lines = [
        f"# Dataset Report: {session_dir.name}",
        "",
        "## Summary",
        f"- Raw step records: {raw_count}",
        f"- Cleaned BC records (all screens): {len(kept_all)}",
        f"- Cleaned BC records (non-combat only): {len(kept_noncombat)}",
        f"- Dropped records: {sum(drop_reasons.values())}",
        "",
        "## Drop Reasons",
    ]

    if drop_reasons:
        for reason, count in sorted(drop_reasons.items()):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Screen Counts (all-screen cleaned table)",
        ]
    )
    for screen, count in all_screen_counts.most_common():
        lines.append(f"- {screen}: {count}")

    lines.extend(
        [
            "",
            "## Action Counts (top 25, all-screen cleaned table)",
        ]
    )
    for action, count in all_action_counts.most_common(25):
        lines.append(f"- {action}: {count}")

    lines.extend(
        [
            "",
            "## Screen Counts (non-combat cleaned table)",
        ]
    )
    for screen, count in noncombat_screen_counts.most_common():
        lines.append(f"- {screen}: {count}")

    lines.extend(
        [
            "",
            "## Training Guidance",
            "- Suitable now for first-pass behavior cloning.",
            "- Prefer structured fields only: screen_type, numeric state, ids, map, action, outcome.",
            "- Do not rely on explanation text, localized names, or event option text as model inputs.",
            "- If you want a first stable model, start with the non-combat cleaned table.",
            "- The all-screen cleaned table can be used for broader BC once combat labeling quality is acceptable.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        raise SystemExit(f"Data directory does not exist: {data_dir}")

    session_dir = resolve_session_dir(data_dir, args.session)
    episode_summaries = load_episode_summaries(session_dir)

    all_output = (
        Path(args.all_output).resolve()
        if args.all_output
        else session_dir / "training_table.bc_all.jsonl"
    )
    noncombat_output = (
        Path(args.noncombat_output).resolve()
        if args.noncombat_output
        else session_dir / "training_table.bc_noncombat.jsonl"
    )
    report_output = (
        Path(args.report_output).resolve()
        if args.report_output
        else session_dir / "dataset_report.md"
    )

    raw_count = 0
    kept_all: list[dict] = []
    kept_noncombat: list[dict] = []
    drop_reasons: Counter = Counter()

    for _, line in iter_step_records(session_dir):
        if args.limit and raw_count >= args.limit:
            break
        raw_count += 1
        try:
            step = json.loads(line)
        except json.JSONDecodeError:
            drop_reasons["json_parse_error"] += 1
            continue

        episode_id = str(step.get("episode_id", ""))
        summary = episode_summaries.get(episode_id)
        merged = build_training_record(step, summary)

        drop_reason = _drop_reason(merged)
        if drop_reason:
            drop_reasons[drop_reason] += 1
            continue

        cleaned = _clean_record(merged)
        kept_all.append(cleaned)
        if _is_noncombat(cleaned):
            kept_noncombat.append(cleaned)

    _write_jsonl(all_output, kept_all)
    _write_jsonl(noncombat_output, kept_noncombat)
    report_output.write_text(
        _build_report(session_dir, raw_count, kept_all, kept_noncombat, drop_reasons),
        encoding="utf-8",
    )

    print(f"[session] {session_dir.name}")
    print(f"[raw_records] {raw_count}")
    print(f"[bc_all] {all_output} rows={len(kept_all)}")
    print(f"[bc_noncombat] {noncombat_output} rows={len(kept_noncombat)}")
    print(f"[report] {report_output}")


if __name__ == "__main__":
    main()
