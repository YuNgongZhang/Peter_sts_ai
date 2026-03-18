"""
ai/decision.py -- 决策入口（全屏幕覆盖）

screen_type 分发:
  MAP           -> _decide_map
  CARD_REWARD   -> _decide_card_reward
  COMBAT_REWARD -> _decide_combat_reward
  BOSS_REWARD   -> _decide_boss_reward
  CHEST         -> _decide_chest
  EVENT         -> _decide_event
  REST          -> _decide_rest
  SHOP_ROOM     -> _decide_shop_room
  SHOP_SCREEN   -> _decide_shop_screen
  GRID          -> _decide_grid
  HAND_SELECT   -> _decide_hand_select
  其他（战斗）   -> _decide_combat

战斗决策：DFS 序列规划 (simulator.py)
"""

from __future__ import annotations
from itertools import combinations
from typing import Any, Dict

from ai.card_stats import JUNK_IDS
from ai.card_rewards import (
    card_priority_score,
    estimate_purge_gain,
    estimate_best_upgrade_gain,
    pick_grid_cards,
    score_reward_options,
    score_shop_card_options,
)
from ai.simulator import get_last_plan_metadata, plan_best_sequence
from spirecomm.spire.screen import RestOption
from spirecomm.ai.priorities import IroncladPriority

_priority = IroncladPriority()

# ── 全局状态 ──────────────────────────────────────────────────────────────────
_planned_uuids: list[str] = []
_visited_shop: bool = False       # 防止重复进店循环
_skipped_card_reward_pending: bool = False

# 危险事件 -> 选最后一个选项（通常为"离开/跳过"）
# 来源：spirecomm SimpleAgent + bottled_ai CommonEventHandler
_DANGEROUS_EVENTS = frozenset({
    "Vampires", "Masked Bandits", "Knowing Skull", "Ghosts",
    "Liars Game", "Golden Idol", "Drug Dealer", "The Library",
    "Cursed Tome", "Nloth", "Secret Portal", "Ancient Writing",
    "Dead Adventurer", "Duplicator",
})


def _set_candidates(game_state: Dict[str, Any], candidates: list[tuple[float, str, str]]) -> None:
    game_state["_decision_candidates"] = [
        {
            "score": round(float(score), 3) if score != float("-inf") else score,
            "action": action,
            "reason": reason,
        }
        for score, action, reason in sorted(candidates, key=lambda item: item[0], reverse=True)
    ]


def _pick_scored_action(
    game_state: Dict[str, Any],
    candidates: list[tuple[float, str, str]],
    default_action: str,
    default_reason: str,
) -> str:
    if not candidates:
        _set_candidates(game_state, [])
        game_state["_decision_reason"] = default_reason
        return default_action

    _set_candidates(game_state, candidates)
    score, action, reason = max(candidates, key=lambda item: item[0])
    if score == float("-inf"):
        game_state["_decision_reason"] = default_reason
        return default_action

    game_state["_decision_reason"] = reason
    return action


def _score_map_node(symbol: str, game_state: Dict[str, Any]) -> float:
    hp_ratio = (game_state.get("current_hp", 1) or 1) / (game_state.get("max_hp", 80) or 80)
    gold = game_state.get("gold", 0) or 0
    floor = game_state.get("floor", 0) or 0

    base_scores = {
        "E": 26.0,
        "R": 17.0,
        "?": 16.0,
        "T": 15.0,
        "$": 14.0,
        "M": 12.0,
    }
    score = base_scores.get(symbol, 0.0)

    if symbol == "E":
        score += 6.0 if hp_ratio >= 0.70 else -10.0
    if symbol == "R":
        score += 12.0 if hp_ratio < 0.45 else 0.0
        score += 8.0 if floor % 17 == 15 and hp_ratio < 0.85 else 0.0
    if symbol == "$":
        score += 8.0 if gold >= 150 else -4.0
    if symbol == "?":
        score += 4.0 if hp_ratio >= 0.60 else -3.0

    return score


def _score_shop_relic(relic, gold: int) -> tuple[float, str]:
    price = int(getattr(relic, "price", 9999) or 9999)
    if gold < price:
        return float("-inf"), "shop_relic_unaffordable"

    relic_id = getattr(relic, "relic_id", "?")
    score = 8.0 - (price / 55.0)
    if gold - price < 75:
        score -= 2.5

    premium_ids = {
        "Bag of Preparation", "Lantern", "Anchor", "Preserved Insect",
        "Oddly Smooth Stone", "Pen Nib", "Horn Cleat", "Orichalcum",
        "Membership Card", "Vajra", "Happy Flower",
    }
    if relic_id in premium_ids:
        score += 5.0

    return score, f"shop_relic_{relic_id}_price={price}"


def _score_event_option(event_id: str, option: dict[str, Any], index: int, total_options: int) -> tuple[float, str]:
    if option.get("disabled", False):
        return float("-inf"), f"event_option_{index}_disabled"

    text = str(option.get("text", "") or "").lower()
    score = 3.0 - (index * 0.2)
    reason = f"event_pick_{index}"

    if event_id in _DANGEROUS_EVENTS:
        score = 10.0 if index == total_options - 1 else -8.0
        reason = f"event_avoid_{event_id}_{index}"

    leave_words = ("leave", "skip", "ignore", "walk away")
    reward_words = ("gold", "relic", "card", "max hp", "remove", "transform", "upgrade")
    downside_words = ("curse", "damage", "lose hp", "regret", "pain", "wound")

    if any(word in text for word in reward_words):
        score += 2.5
        reason = f"event_reward_{index}"
    if any(word in text for word in downside_words):
        score -= 3.0
        reason = f"event_risky_{index}"
    if any(word in text for word in leave_words):
        score -= 1.0
        reason = f"event_leave_{index}"

    return score, reason


def _score_hand_select_combo(combo: tuple[int, ...], cards: list, for_exhaust: bool = True) -> tuple[float, str]:
    score = 0.0
    parts = []
    for idx in combo:
        card = cards[idx]
        priority = card_priority_score(card)
        if priority == float("inf"):
            priority = 250.0
        score += float(priority)
        parts.append(getattr(card, "card_id", "?"))
    if for_exhaust:
        return score, f"hand_select_exhaust_{'_'.join(parts)}"
    return score, f"hand_select_{'_'.join(parts)}"


# =============================================================================
# 公开接口
# =============================================================================

def decide_action(game_state: Dict[str, Any]) -> str:
    """
    顶层分发：根据 screen_type 调用对应子决策器。
    返回 spirecomm action 字符串，并将原因写入 game_state["_decision_reason"]。
    """
    global _skipped_card_reward_pending
    screen_type = game_state.get("screen_type", "")

    if screen_type not in {"CARD_REWARD", "COMBAT_REWARD"}:
        _skipped_card_reward_pending = False

    if screen_type == "MAP":           return _decide_map(game_state)
    if screen_type == "CARD_REWARD":   return _decide_card_reward(game_state)
    if screen_type == "COMBAT_REWARD": return _decide_combat_reward(game_state)
    if screen_type == "BOSS_REWARD":   return _decide_boss_reward(game_state)
    if screen_type == "CHEST":         return _decide_chest(game_state)
    if screen_type == "EVENT":         return _decide_event(game_state)
    if screen_type == "REST":          return _decide_rest(game_state)
    if screen_type == "SHOP_ROOM":     return _decide_shop_room(game_state)
    if screen_type == "SHOP_SCREEN":   return _decide_shop_screen(game_state)
    if screen_type == "GRID":          return _decide_grid(game_state)
    if screen_type == "HAND_SELECT":   return _decide_hand_select(game_state)
    if screen_type == "GAME_OVER":     return _decide_game_over(game_state)
    if screen_type == "COMPLETE":      return _decide_complete(game_state)

    # 未知屏幕有选项 -> 选第一个（Neow 开局奖励等）
    if game_state.get("choice_available", False):
        game_state["_decision_reason"] = "unknown_choice_0"
        return "choose_0"

    return _decide_combat(game_state)


# =============================================================================
# 战斗奖励 / 卡牌奖励
# =============================================================================

def _decide_combat_reward(game_state: Dict[str, Any]) -> str:
    """对战斗奖励候选动作打分，允许“跳过剩余奖励”作为显式决策。"""
    global _skipped_card_reward_pending
    rewards = game_state.get("combat_rewards", [])
    if not rewards:
        _skipped_card_reward_pending = False
        game_state["_decision_reason"] = "proceed_rewards"
        return "proceed_combat_reward"

    potions_full = bool(game_state.get("potions_full", False))
    candidates: list[tuple[float, str, str]] = []
    for i, r in enumerate(rewards):
        rtype = getattr(getattr(r, "reward_type", None), "name", "")
        if rtype == "CARD":
            score = -25.0 if _skipped_card_reward_pending else 20.0
            candidates.append((score, f"take_combat_reward_{i}", "open_card_reward"))
            continue
        if rtype == "POTION":
            if potions_full:
                continue
            candidates.append((11.0, f"take_combat_reward_{i}", "take_reward_potion"))
            continue
        if rtype == "RELIC":
            candidates.append((18.0, f"take_combat_reward_{i}", "take_reward_relic"))
            continue
        if rtype == "SAPPHIRE_KEY":
            candidates.append((16.0, f"take_combat_reward_{i}", "take_reward_key"))
            continue
        if rtype in {"GOLD", "STOLEN_GOLD"}:
            gold_amount = float(getattr(r, "gold", 0) or 0)
            candidates.append((12.0 + min(gold_amount / 25.0, 6.0), f"take_combat_reward_{i}", "take_reward_gold"))
            continue
        candidates.append((8.0, f"take_combat_reward_{i}", f"take_reward_{rtype.lower()}"))

    if _skipped_card_reward_pending:
        has_non_card_claim = any(
            action.startswith("take_combat_reward_") and reason != "open_card_reward"
            for _, action, reason in candidates
        )
        skip_score = 1.0 if has_non_card_claim else 14.0
        candidates.append((skip_score, "skip_combat_reward", "skip_remaining_rewards"))

    action = _pick_scored_action(
        game_state,
        candidates,
        default_action="skip_combat_reward",
        default_reason="skip_unclaimable_rewards",
    )
    if action == "skip_combat_reward":
        _skipped_card_reward_pending = False
    return action


def _decide_card_reward(game_state: Dict[str, Any]) -> str:
    """把“拿哪张卡”和“跳过”统一成同一个打分决策。"""
    global _skipped_card_reward_pending
    cards = game_state.get("reward_cards", [])
    scored_cards, skip_threshold = score_reward_options(
        cards,
        deck_cards=game_state.get("deck_cards", []),
        relic_ids=game_state.get("relic_ids", []),
        floor=game_state.get("floor"),
        act=game_state.get("act"),
    )

    candidates = [
        (score - skip_threshold, f"choose_card_reward_{idx}", f"reward_{getattr(card, 'card_id', '?')}_{reason}")
        for score, idx, card, reason in scored_cards
    ]
    if game_state.get("card_reward_can_skip", True):
        candidates.append((0.0, "skip_card_reward", "reward_skip_threshold"))

    action = _pick_scored_action(
        game_state,
        candidates,
        default_action="skip_card_reward",
        default_reason="reward_skip_empty",
    )
    if action == "skip_card_reward":
        _skipped_card_reward_pending = True
        game_state["_decision_reason"] = f"{game_state['_decision_reason']}_skip"
        return action

    _skipped_card_reward_pending = False
    return action


# =============================================================================
# Boss 遗物奖励
# =============================================================================

def _decide_boss_reward(game_state: Dict[str, Any]) -> str:
    """用 IroncladPriority.get_best_boss_relic 选最优 Boss 遗物。"""
    relics = game_state.get("boss_relics", [])
    if not relics:
        game_state["_decision_reason"] = "boss_reward_proceed"
        return "proceed"
    best = _priority.get_best_boss_relic(relics)
    idx = relics.index(best)
    game_state["_decision_reason"] = f"boss_relic_{getattr(best, 'relic_id', '?')}"
    return f"take_boss_reward_{idx}"


# =============================================================================
# 地图导航
# =============================================================================

def _decide_map(game_state: Dict[str, Any]) -> str:
    """地图路线选择也走候选动作打分。"""
    map_nodes      = game_state.get("map_nodes", [])
    boss_available = game_state.get("boss_available", False)
    choice_available = game_state.get("choice_available", False)

    if boss_available and not map_nodes:
        game_state["_decision_reason"] = "map_boss"
        return "choose_map_boss"
    if not map_nodes:
        game_state["_decision_reason"] = (
            "map_wait_transition" if not choice_available else "map_no_nodes"
        )
        return "wait"

    candidates = []
    for idx, node in enumerate(map_nodes):
        symbol = node.get("symbol", "?")
        score = _score_map_node(symbol, game_state)
        candidates.append((score, f"choose_map_node_{idx}", f"map_{symbol}"))

    return _pick_scored_action(
        game_state,
        candidates,
        default_action="wait",
        default_reason="map_wait_transition",
    )


# =============================================================================
# 宝箱
# =============================================================================

def _decide_chest(game_state: Dict[str, Any]) -> str:
    """宝箱也作为显式动作候选处理。"""
    candidates: list[tuple[float, str, str]] = []
    if game_state.get("chest_open", False):
        candidates.append((8.0, "proceed", "chest_proceed"))
    else:
        candidates.append((10.0, "open_chest", "open_chest"))
        candidates.append((-2.0, "proceed", "chest_skip"))
    return _pick_scored_action(
        game_state,
        candidates,
        default_action="proceed",
        default_reason="chest_proceed",
    )


# =============================================================================
# 事件
# =============================================================================

def _decide_event(game_state: Dict[str, Any]) -> str:
    """
    危险事件选最后一项（通常是离开）；其余事件选第一个未禁用选项。
    危险事件列表来自 spirecomm SimpleAgent + bottled_ai CommonEventHandler。
    """
    event_id = game_state.get("event_id", "")
    options  = game_state.get("event_options", [])

    if not options:
        game_state["_decision_reason"] = "event_proceed"
        return "proceed"
    candidates = []
    for i, opt in enumerate(options):
        score, reason = _score_event_option(event_id, opt, i, len(options))
        candidates.append((score, f"choose_event_{i}", reason))
    return _pick_scored_action(
        game_state,
        candidates,
        default_action="choose_event_0",
        default_reason="event_fallback",
    )


# =============================================================================
# 休息点（篝火）
# =============================================================================

def _decide_rest(game_state: Dict[str, Any]) -> str:
    """
    优先级（来自 spirecomm SimpleAgent）：
      1. HP < 50%                 -> REST
      2. Boss 前一层 & HP < 90%   -> REST
      3. 有 SMITH（升级）          -> SMITH
      4. LIFT / DIG / TOKE / RECALL 按序
      5. HP 未满                  -> REST
      6. 其他                     -> proceed
    """
    has_rested   = game_state.get("has_rested", False)
    rest_options = game_state.get("rest_options", [])
    current_hp   = game_state.get("current_hp", 1) or 1
    max_hp       = game_state.get("max_hp", 80) or 80
    act          = game_state.get("act", 1)
    floor_num    = game_state.get("floor", 1)
    deck_cards   = game_state.get("deck_cards", [])
    upgrade_gain = estimate_best_upgrade_gain(
        deck_cards,
        deck_cards=deck_cards,
        relic_ids=game_state.get("relic_ids", []),
        floor=floor_num,
        act=act,
    )

    if has_rested or not rest_options:
        game_state["_decision_reason"] = "rest_proceed"
        return "proceed"

    hp_ratio = current_hp / max_hp
    candidates: list[tuple[float, str, str]] = [(0.0, "proceed", "rest_proceed")]

    if RestOption.REST in rest_options:
        rest_score = (1.0 - hp_ratio) * 30.0
        if hp_ratio < 0.50:
            rest_score += 12.0
        if act > 1 and floor_num % 17 == 15 and hp_ratio < 0.90:
            rest_score += 10.0
        candidates.append((rest_score, "rest_REST", "rest_heal"))

    if RestOption.SMITH in rest_options:
        smith_score = upgrade_gain - max(0.0, (0.60 - hp_ratio) * 20.0)
        candidates.append((smith_score, "rest_SMITH", "rest_smith"))

    for option in (RestOption.LIFT, RestOption.DIG, RestOption.TOKE, RestOption.RECALL):
        if option in rest_options:
            candidates.append((6.0, f"rest_{option.name}", f"rest_{option.name}"))

    return _pick_scored_action(
        game_state,
        candidates,
        default_action="proceed",
        default_reason="rest_proceed",
    )


# =============================================================================
# 商店
# =============================================================================

def _decide_shop_room(game_state: Dict[str, Any]) -> str:
    """商店房间的进入/离开也显式进入决策。"""
    global _visited_shop
    gold = game_state.get("gold", 0) or 0
    hp_ratio = (game_state.get("current_hp", 1) or 1) / (game_state.get("max_hp", 80) or 80)
    if _visited_shop:
        _visited_shop = False
        return _pick_scored_action(
            game_state,
            [(8.0, "proceed", "shop_leave_room"), (-4.0, "enter_shop", "shop_reenter_loop")],
            default_action="proceed",
            default_reason="shop_leave_room",
        )

    enter_score = 6.0 + min(gold / 60.0, 5.0)
    if hp_ratio < 0.35:
        enter_score -= 2.0
    candidates = [
        (enter_score, "enter_shop", "enter_shop"),
        (1.0, "proceed", "shop_skip_room"),
    ]
    action = _pick_scored_action(
        game_state,
        candidates,
        default_action="enter_shop",
        default_reason="enter_shop",
    )
    if action == "enter_shop":
        _visited_shop = True
    return action


def _decide_shop_screen(game_state: Dict[str, Any]) -> str:
    """商店里的买/不买/净化/离开统一走候选动作打分。"""
    gold         = game_state.get("gold", 0)
    shop_cards   = game_state.get("shop_cards", [])
    shop_relics  = game_state.get("shop_relics", [])
    deck_cards   = game_state.get("deck_cards", [])
    relic_ids    = game_state.get("relic_ids", [])
    floor_num    = game_state.get("floor", 1)
    act          = game_state.get("act", 1)
    purge_avail  = game_state.get("purge_available", False)
    purge_cost   = game_state.get("purge_cost", 9999)
    candidates: list[tuple[float, str, str]] = [(0.0, "shop_leave", "shop_leave")]

    if purge_avail and gold >= purge_cost:
        purge_gain = estimate_purge_gain(
            deck_cards,
            deck_cards=deck_cards,
            relic_ids=relic_ids,
            floor=floor_num,
            act=act,
        )
        purge_score = purge_gain - (purge_cost / 45.0)
        candidates.append((purge_score, "shop_purge", f"shop_purge_gain={purge_gain:.1f}_cost={purge_cost}"))

    scored_cards, buy_threshold = score_shop_card_options(
        shop_cards,
        gold=gold,
        deck_cards=deck_cards,
        relic_ids=relic_ids,
        floor=floor_num,
        act=act,
    )
    for score, idx, card, reason in scored_cards:
        candidates.append((score - buy_threshold, f"buy_card_{idx}", f"shop_card_{getattr(card,'card_id','?')}_{reason}"))

    for i, relic in enumerate(shop_relics):
        score, reason = _score_shop_relic(relic, gold)
        candidates.append((score, f"buy_relic_{i}", reason))

    return _pick_scored_action(
        game_state,
        candidates,
        default_action="shop_leave",
        default_reason="shop_leave",
    )


# =============================================================================
# Grid 选牌（升级 / 净化 / 变形）
# =============================================================================

def _decide_grid(game_state: Dict[str, Any]) -> str:
    """
    choice_available=False -> 等待
    for_upgrade=True -> 选最好的 N 张牌
    for_purge=True   -> 选最差的 N 张牌
    其他             -> 选最好的 N 张牌
    """
    if not game_state.get("choice_available", False):
        game_state["_decision_reason"] = "grid_not_ready"
        return "proceed"

    cards     = game_state.get("grid_cards", [])
    num_cards = game_state.get("grid_num_cards", 1)
    for_purge = game_state.get("for_purge", False)
    for_upgrade = game_state.get("for_upgrade", False)

    if not cards:
        game_state["_decision_reason"] = "grid_no_cards"
        return "proceed"

    indices, reason = pick_grid_cards(
        cards,
        deck_cards=game_state.get("deck_cards", cards),
        relic_ids=game_state.get("relic_ids", []),
        floor=game_state.get("floor"),
        act=game_state.get("act"),
        num_cards=num_cards,
        for_purge=for_purge,
        for_upgrade=for_upgrade,
    )

    if not indices:
        game_state["_decision_reason"] = "grid_no_indices"
        return "proceed"

    game_state["_decision_reason"] = f"grid_{reason}"
    return "grid_select_" + "_".join(str(i) for i in indices)


# =============================================================================
# Hand Select
# =============================================================================

def _decide_hand_select(game_state: Dict[str, Any]) -> str:
    """手牌选择改成组合候选打分。"""
    if not game_state.get("choice_available", False):
        game_state["_decision_reason"] = "hand_select_not_ready"
        return "proceed"

    cards     = game_state.get("hand_select_cards", [])
    num_cards = min(game_state.get("hand_select_num", 1), 3)

    if not cards:
        game_state["_decision_reason"] = "hand_select_no_cards"
        return "proceed"

    candidates: list[tuple[float, str, str]] = []
    for combo in combinations(range(len(cards)), num_cards):
        score, reason = _score_hand_select_combo(combo, cards)
        action = "hand_select_" + "_".join(str(i) for i in combo)
        candidates.append((score, action, reason))

    return _pick_scored_action(
        game_state,
        candidates,
        default_action="proceed",
        default_reason="hand_select_no_indices",
    )


def _decide_game_over(game_state: Dict[str, Any]) -> str:
    game_state["_decision_reason"] = (
        "victory" if game_state.get("game_over_victory") else "defeat"
    )
    return "proceed"


def _decide_complete(game_state: Dict[str, Any]) -> str:
    game_state["_decision_reason"] = "complete_proceed"
    return "proceed"


# =============================================================================
# 战斗出牌（DFS 序列规划）
# =============================================================================

def _decide_combat(game_state: Dict[str, Any]) -> str:
    """DFS 序列规划器（含快速路径）。"""
    global _planned_uuids

    raw = game_state.get("raw")
    if raw is None or not hasattr(raw, "hand"):
        game_state["_decision_reason"] = "no_raw"
        return "end_turn"

    player = getattr(raw, "player", None)
    hand   = list(getattr(raw, "hand", None) or [])
    energy = getattr(player, "energy", 0) or 0

    if energy <= 0:
        zero_cost = [c for c in hand
                     if getattr(c, "is_playable", False)
                     and getattr(c, "cost", 1) == 0
                     and getattr(c, "card_id", "") not in JUNK_IDS]
        if not zero_cost:
            _planned_uuids = []
            game_state["_decision_reason"] = "no_energy"
            return "end_turn"

    if _planned_uuids:
        next_uuid = _planned_uuids[0]
        matching  = [c for c in hand
                     if getattr(c, "uuid", None) == next_uuid
                     and getattr(c, "is_playable", False)]
        if matching:
            _planned_uuids = _planned_uuids[1:]
            idx = hand.index(matching[0])
            game_state["_decision_reason"] = "sequence"
            return f"play_card_{idx}"
        else:
            _planned_uuids = []

    sequence = plan_best_sequence(raw)
    plan_meta = get_last_plan_metadata()
    if not sequence:
        if plan_meta.get("timed_out") or plan_meta.get("node_budget_hit"):
            game_state["_decision_reason"] = "dfs_timeout_no_playable"
        else:
            game_state["_decision_reason"] = "no_playable"
        return "end_turn"

    _planned_uuids = [getattr(c, "uuid", "") for c in sequence[1:]]
    first_card = sequence[0]
    try:
        idx = hand.index(first_card)
    except ValueError:
        _planned_uuids = []
        game_state["_decision_reason"] = "index_error"
        return "end_turn"

    if plan_meta.get("timed_out") or plan_meta.get("node_budget_hit"):
        game_state["_decision_reason"] = "dfs_timeout_plan"
    else:
        game_state["_decision_reason"] = "dfs_plan"
    return f"play_card_{idx}"
