"""
ai/explanation.py  --  Template-based explanation (Milestone 2)

Uses the decision reason stored by decide_action() to produce a
context-aware one-sentence explanation. No LLM yet -- that is Milestone 3.
"""

from typing import Any, Dict


def explain_action(game_state: Dict[str, Any], action: str) -> str:
    hand         = game_state.get("hand") or []
    enemy_intent = game_state.get("enemy_intent") or "unknown"
    reason       = game_state.get("_decision_reason", "priority_list")

    # ── End turn ─────────────────────────────────────────────────────────────
    if action == "end_turn":
        if reason in ("no_energy", "no_playable"):
            return f"No playable cards (energy=0 or no legal plays). Ending turn. Enemy: {enemy_intent}."
        return f"Ending turn. Enemy: {enemy_intent}."

    # ── Play card ─────────────────────────────────────────────────────────────
    card_name = _card_name(action, hand)

    reason_map = {
        "dfs_plan":  f"DFS: playing {card_name} as first card of optimal sequence. Enemy: {enemy_intent}.",
        "sequence":  f"Sequence: playing {card_name} (planned). Enemy: {enemy_intent}.",
    }

    return reason_map.get(reason,
                          f"Playing {card_name}. Enemy: {enemy_intent}.")


def _card_name(action: str, hand: list) -> str:
    """Extract display name from action string and hand list."""
    if action.startswith("play_card_"):
        try:
            idx = int(action.split("_")[-1])
            if 0 <= idx < len(hand):
                return hand[idx]
        except (ValueError, IndexError):
            pass
    return "chosen card"
