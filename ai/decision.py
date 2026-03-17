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
from typing import Any, Dict

from ai.card_stats import JUNK_IDS
from ai.card_rewards import pick_best_reward
from ai.simulator import plan_best_sequence
from spirecomm.spire.screen import RestOption
from spirecomm.ai.priorities import IroncladPriority

_priority = IroncladPriority()

# ── 全局状态 ──────────────────────────────────────────────────────────────────
_planned_uuids: list[str] = []
_visited_shop: bool = False       # 防止重复进店循环

# ── 地图节点优先级 ─────────────────────────────────────────────────────────────
# E=精英  R=休息  ?=事件  T=宝箱  $=商店  M=普通怪
_MAP_PRIORITY: dict[str, int] = {
    "E": 0, "R": 1, "?": 2, "T": 3, "$": 4, "M": 5,
}

# 危险事件 -> 选最后一个选项（通常为"离开/跳过"）
# 来源：spirecomm SimpleAgent + bottled_ai CommonEventHandler
_DANGEROUS_EVENTS = frozenset({
    "Vampires", "Masked Bandits", "Knowing Skull", "Ghosts",
    "Liars Game", "Golden Idol", "Drug Dealer", "The Library",
    "Cursed Tome", "Nloth", "Secret Portal", "Ancient Writing",
    "Dead Adventurer", "Duplicator",
})


# =============================================================================
# 公开接口
# =============================================================================

def decide_action(game_state: Dict[str, Any]) -> str:
    """
    顶层分发：根据 screen_type 调用对应子决策器。
    返回 spirecomm action 字符串，并将原因写入 game_state["_decision_reason"]。
    """
    screen_type = game_state.get("screen_type", "")

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

    # 未知屏幕有选项 -> 选第一个（Neow 开局奖励等）
    if game_state.get("choice_available", False):
        game_state["_decision_reason"] = "unknown_choice_0"
        return "choose_0"

    return _decide_combat(game_state)


# =============================================================================
# 战斗奖励 / 卡牌奖励
# =============================================================================

def _decide_combat_reward(game_state: Dict[str, Any]) -> str:
    """逐一领取战斗奖励；找到 CARD 类型时打开选牌界面。"""
    rewards = game_state.get("combat_rewards", [])
    for i, r in enumerate(rewards):
        rtype = getattr(getattr(r, "reward_type", None), "name", "")
        if rtype == "CARD":
            game_state["_decision_reason"] = "open_card_reward"
            return f"take_combat_reward_{i}"
    game_state["_decision_reason"] = "proceed_rewards"
    return "proceed_combat_reward"


def _decide_card_reward(game_state: Dict[str, Any]) -> str:
    """用 IroncladPriority 选最优奖励卡，或跳过。"""
    cards = game_state.get("reward_cards", [])
    idx, card = pick_best_reward(cards)
    if idx is None:
        game_state["_decision_reason"] = "reward_skip"
        return "skip_card_reward"
    game_state["_decision_reason"] = f"reward_{getattr(card, 'card_id', '?')}"
    return f"choose_card_reward_{idx}"


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
    """按节点类型优先级选择最优路径。"""
    map_nodes      = game_state.get("map_nodes", [])
    boss_available = game_state.get("boss_available", False)

    if boss_available and not map_nodes:
        game_state["_decision_reason"] = "map_boss"
        return "choose_map_boss"
    if not map_nodes:
        game_state["_decision_reason"] = "map_no_nodes"
        return "choose_map_boss"

    best_idx = min(
        range(len(map_nodes)),
        key=lambda i: _MAP_PRIORITY.get(map_nodes[i]["symbol"], 99),
    )
    game_state["_decision_reason"] = f"map_{map_nodes[best_idx]['symbol']}"
    return f"choose_map_node_{best_idx}"


# =============================================================================
# 宝箱
# =============================================================================

def _decide_chest(game_state: Dict[str, Any]) -> str:
    """宝箱未开就开，已开就推进。"""
    if game_state.get("chest_open", False):
        game_state["_decision_reason"] = "chest_proceed"
        return "proceed"
    game_state["_decision_reason"] = "open_chest"
    return "open_chest"


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

    if event_id in _DANGEROUS_EVENTS:
        idx = len(options) - 1
        game_state["_decision_reason"] = f"event_avoid_{event_id}"
        return f"choose_event_{idx}"

    for i, opt in enumerate(options):
        if not opt.get("disabled", False):
            game_state["_decision_reason"] = f"event_pick_{i}"
            return f"choose_event_{i}"

    game_state["_decision_reason"] = "event_fallback"
    return "choose_event_0"


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

    if has_rested or not rest_options:
        game_state["_decision_reason"] = "rest_proceed"
        return "proceed"

    hp_ratio = current_hp / max_hp

    if RestOption.REST in rest_options and hp_ratio < 0.50:
        game_state["_decision_reason"] = "rest_heal_low"
        return "rest_REST"

    if (RestOption.REST in rest_options
            and act > 1
            and floor_num % 17 == 15
            and hp_ratio < 0.90):
        game_state["_decision_reason"] = "rest_heal_preboss"
        return "rest_REST"

    if RestOption.SMITH in rest_options:
        game_state["_decision_reason"] = "rest_smith"
        return "rest_SMITH"

    for option in (RestOption.LIFT, RestOption.DIG, RestOption.TOKE, RestOption.RECALL):
        if option in rest_options:
            game_state["_decision_reason"] = f"rest_{option.name}"
            return f"rest_{option.name}"

    if RestOption.REST in rest_options and hp_ratio < 1.0:
        game_state["_decision_reason"] = "rest_heal_notfull"
        return "rest_REST"

    game_state["_decision_reason"] = "rest_proceed"
    return "proceed"


# =============================================================================
# 商店
# =============================================================================

def _decide_shop_room(game_state: Dict[str, Any]) -> str:
    """第一次进入商店，第二次（离开后）推进。"""
    global _visited_shop
    if _visited_shop:
        _visited_shop = False
        game_state["_decision_reason"] = "shop_leave_room"
        return "proceed"
    _visited_shop = True
    game_state["_decision_reason"] = "enter_shop"
    return "enter_shop"


def _decide_shop_screen(game_state: Dict[str, Any]) -> str:
    """
    购物优先级（来自 spirecomm SimpleAgent）：
      1. 净化（去除最差牌）
      2. 买值得买的卡牌
      3. 买遗物
      4. 离开
    """
    gold         = game_state.get("gold", 0)
    shop_cards   = game_state.get("shop_cards", [])
    shop_relics  = game_state.get("shop_relics", [])
    purge_avail  = game_state.get("purge_available", False)
    purge_cost   = game_state.get("purge_cost", 9999)

    if purge_avail and gold >= purge_cost:
        game_state["_decision_reason"] = "shop_purge"
        return "shop_purge"

    for i, card in enumerate(shop_cards):
        price = getattr(card, "price", 9999)
        if gold >= price and not _priority.should_skip(card):
            game_state["_decision_reason"] = f"shop_card_{getattr(card,'card_id','?')}"
            return f"buy_card_{i}"

    for i, relic in enumerate(shop_relics):
        price = getattr(relic, "price", 9999)
        if gold >= price:
            game_state["_decision_reason"] = f"shop_relic_{getattr(relic,'relic_id','?')}"
            return f"buy_relic_{i}"

    game_state["_decision_reason"] = "shop_leave"
    return "shop_leave"


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

    if not cards:
        game_state["_decision_reason"] = "grid_no_cards"
        return "proceed"

    sorted_cards = _priority.get_sorted_cards(cards, reverse=for_purge)
    selected     = sorted_cards[:num_cards]
    indices      = []
    for c in selected:
        try:
            indices.append(cards.index(c))
        except ValueError:
            pass

    if not indices:
        game_state["_decision_reason"] = "grid_no_indices"
        return "proceed"

    game_state["_decision_reason"] = "grid_select"
    return "grid_select_" + "_".join(str(i) for i in indices)


# =============================================================================
# Hand Select
# =============================================================================

def _decide_hand_select(game_state: Dict[str, Any]) -> str:
    """从手牌中选择最差的 N 张（通常用于净化/变形）。"""
    if not game_state.get("choice_available", False):
        game_state["_decision_reason"] = "hand_select_not_ready"
        return "proceed"

    cards     = game_state.get("hand_select_cards", [])
    num_cards = min(game_state.get("hand_select_num", 1), 3)

    if not cards:
        game_state["_decision_reason"] = "hand_select_no_cards"
        return "proceed"

    sorted_cards = _priority.get_sorted_cards(cards, reverse=True)
    selected     = sorted_cards[:num_cards]
    indices      = []
    for c in selected:
        try:
            indices.append(cards.index(c))
        except ValueError:
            pass

    if not indices:
        game_state["_decision_reason"] = "hand_select_no_indices"
        return "proceed"

    game_state["_decision_reason"] = "hand_select"
    return "hand_select_" + "_".join(str(i) for i in indices)


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
    if not sequence:
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

    game_state["_decision_reason"] = "dfs_plan"
    return f"play_card_{idx}"
