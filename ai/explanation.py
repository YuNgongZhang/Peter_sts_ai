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

    if action == "skip_card_reward":
        return f"Skipping card reward. Reason: {reason}."

    if action == "skip_combat_reward":
        return f"Skipping remaining combat rewards. Reason: {reason}."

    if action.startswith("choose_card_reward_"):
        card_name = _screen_card_name(action, game_state.get("reward_cards") or [])
        return f"Taking reward card {card_name}. Reason: {reason}."

    if action.startswith("buy_card_"):
        card_name = _screen_card_name(action, game_state.get("shop_cards") or [], prefix="buy_card_")
        return f"Buying shop card {card_name}. Reason: {reason}."

    if action == "shop_purge":
        return f"Using shop purge. Reason: {reason}."

    if action == "shop_leave":
        return "Leaving shop because no purchase met the threshold."

    if action.startswith("rest_"):
        return f"Taking rest action {action[5:]}. Reason: {reason}."

    if action.startswith("grid_select_"):
        return f"Selecting grid cards. Reason: {reason}."

    if action.startswith("take_combat_reward_"):
        return f"Claiming combat reward. Reason: {reason}."

    if action.startswith("take_boss_reward_"):
        return f"Taking boss relic reward. Reason: {reason}."

    if action.startswith("choose_event_"):
        return f"Choosing event option. Reason: {reason}."

    if action.startswith("choose_map_node_") or action == "choose_map_boss":
        return f"Choosing map path. Reason: {reason}."

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


def _screen_card_name(action: str, cards: list, prefix: str = "choose_card_reward_") -> str:
    if action.startswith(prefix):
        try:
            idx = int(action[len(prefix):])
            if 0 <= idx < len(cards):
                card = cards[idx]
                return getattr(card, "card_id", getattr(card, "name", "chosen card"))
        except (ValueError, IndexError):
            pass
    return "chosen card"
