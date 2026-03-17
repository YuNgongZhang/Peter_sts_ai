import os
import sys
from datetime import datetime

from spirecomm.communication.coordinator import Coordinator
from spirecomm.communication.action import (
    StateAction, PlayCardAction, EndTurnAction, ProceedAction, CancelAction,
    ChooseAction, ChooseMapNodeAction, ChooseMapBossAction,
    CardRewardAction, CombatRewardAction, BossRewardAction,
    OpenChestAction, EventOptionAction, RestAction,
    ChooseShopkeeperAction, BuyCardAction, BuyRelicAction, BuyPurgeAction,
    CardSelectAction,
)
from spirecomm.spire.character import Intent
from spirecomm.spire.card import CardType
from spirecomm.spire.screen import ScreenType, RestOption

import ai.decision as _decision
from ai.explanation import explain_action


LOG_PATH = os.path.join(os.path.dirname(__file__), "sts_state.log")

_last_state_fingerprint: tuple = ()

# 这些屏幕无论 play/end/choice_available 是否为 True，都必须到达 decide_action
_ACTIVE_SCREENS = frozenset({
    ScreenType.CARD_REWARD,
    ScreenType.COMBAT_REWARD,
    ScreenType.MAP,
    ScreenType.CHEST,
    ScreenType.EVENT,
    ScreenType.REST,
    ScreenType.SHOP_ROOM,
    ScreenType.SHOP_SCREEN,
    ScreenType.BOSS_REWARD,
    ScreenType.GRID,
    ScreenType.HAND_SELECT,
})

# proceed 快速通道不拦截这些屏幕（需要 AI 做选择）
_NO_INTERCEPT = frozenset({
    ScreenType.COMBAT_REWARD,
    ScreenType.CARD_REWARD,
    ScreenType.BOSS_REWARD,
    ScreenType.SHOP_SCREEN,
    ScreenType.REST,
    ScreenType.CHEST,
    ScreenType.GRID,
    ScreenType.HAND_SELECT,
    ScreenType.EVENT,
})


def log(line: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    msg = f"{timestamp} {line}"
    if sys.stdin.isatty():
        print(msg, file=sys.stderr, flush=True)
    else:
        with open(LOG_PATH, "a", encoding="utf-8", errors="ignore") as f:
            f.write(msg + "\n")


def _parse_hand(game_state) -> list[str]:
    hand_names = []
    hand = getattr(game_state, "hand", None)
    if hand is None:
        return hand_names
    try:
        for c in hand:
            card_id = getattr(c, "card_id", None)
            if not isinstance(card_id, str) or not card_id.strip():
                continue
            base = card_id.strip()
            for suf in ("_R", "_G", "_B", "_P"):
                if base.endswith(suf):
                    base = base[: -len(suf)]
                    break
            hand_names.append(base.replace("_", " "))
    except TypeError:
        pass
    return hand_names


def _parse_enemy_intent(game_state) -> str:
    monsters = getattr(game_state, "monsters", None)
    if not monsters:
        return "unknown"
    try:
        alive = [m for m in monsters if not getattr(m, "is_gone", False)]
        if not alive:
            return "unknown"
        first = alive[0]
        intent: Intent | None = getattr(first, "intent", None)
        if intent is None:
            return "unknown"
        intent_name = intent.name.lower()
        if intent in (Intent.DEBUG, Intent.UNKNOWN, Intent.NONE):
            return "unknown"
        if intent.is_attack():
            dmg  = getattr(first, "move_adjusted_damage", 0)
            hits = getattr(first, "move_hits", 0)
            try:
                dmg_i, hits_i = int(dmg), int(hits)
            except (TypeError, ValueError):
                return intent_name
            if dmg_i < 0:
                return f"{intent_name} ?"
            if hits_i > 1:
                return f"{intent_name} {dmg_i}x{hits_i}"
            return f"{intent_name} {dmg_i}"
        return intent_name
    except (TypeError, StopIteration, AttributeError):
        return "unknown"


def _select_target(game_state, card):
    alive = [
        m for m in (getattr(game_state, "monsters", None) or [])
        if not getattr(m, "is_gone", True)
        and not getattr(m, "half_dead", False)
        and getattr(m, "current_hp", 0) > 0
    ]
    if not alive:
        return None
    if getattr(card, "type", None) == CardType.ATTACK:
        return min(alive, key=lambda m: m.current_hp)
    return max(alive, key=lambda m: m.current_hp)


def _build_spirecomm_action(action_str: str, game_state):
    """将 decide_action() 返回的字符串转换为 spirecomm Action 对象。"""
    screen = getattr(game_state, "screen", None)

    # ── 战斗 ──────────────────────────────────────────────────────────────────
    if action_str == "end_turn":
        return EndTurnAction()

    if action_str.startswith("play_card_"):
        try:
            idx = int(action_str.split("_")[-1])
        except ValueError:
            return EndTurnAction()
        hand = list(getattr(game_state, "hand", None) or [])
        if idx >= len(hand):
            return EndTurnAction()
        card = hand[idx]
        if not getattr(card, "is_playable", False):
            log(f"[warn] {getattr(card,'card_id','?')} not playable, ending turn")
            return EndTurnAction()
        target = None
        if getattr(card, "has_target", False):
            target = _select_target(game_state, card)
            if target is None:
                log("[warn] no alive target, ending turn")
                return EndTurnAction()
        return PlayCardAction(card=card, target_monster=target)

    # ── 通用推进 ──────────────────────────────────────────────────────────────
    if action_str == "proceed":
        return ProceedAction()

    # ── 未知 choice（Neow 等）────────────────────────────────────────────────
    if action_str.startswith("choose_"):
        # choose_0, choose_1, ...
        tail = action_str[len("choose_"):]
        if tail.isdigit():
            return ChooseAction(choice_index=int(tail))

    # ── 战斗奖励 ──────────────────────────────────────────────────────────────
    if action_str in ("skip_card_reward", "proceed_combat_reward"):
        return ProceedAction()

    if action_str.startswith("choose_card_reward_"):
        try:
            idx = int(action_str.split("_")[-1])
        except ValueError:
            return ProceedAction()
        # CardRewardAction 用 card.name 发命令，中文客户端下名字乱码会报错。
        # 直接发 "choose <index>" 更可靠，CommunicationMod 支持数字索引。
        cards = getattr(screen, "cards", []) if screen else []
        if idx < len(cards):
            return ChooseAction(choice_index=idx)
        return ProceedAction()

    if action_str.startswith("take_combat_reward_"):
        try:
            idx = int(action_str.split("_")[-1])
        except ValueError:
            return ProceedAction()
        rewards = getattr(screen, "rewards", []) if screen else []
        if idx < len(rewards):
            return CombatRewardAction(rewards[idx])
        return ProceedAction()

    # ── Boss 遗物 ──────────────────────────────────────────────────────────────
    if action_str.startswith("take_boss_reward_"):
        try:
            idx = int(action_str.split("_")[-1])
        except ValueError:
            return ProceedAction()
        relics = getattr(screen, "relics", []) if screen else []
        if idx < len(relics):
            return BossRewardAction(relics[idx])
        return ProceedAction()

    # ── 地图 ──────────────────────────────────────────────────────────────────
    if action_str == "choose_map_boss":
        return ChooseMapBossAction()

    if action_str.startswith("choose_map_node_"):
        try:
            idx = int(action_str.split("_")[-1])
        except ValueError:
            return StateAction(requires_game_ready=False)
        next_nodes = getattr(screen, "next_nodes", []) if screen else []
        if idx < len(next_nodes):
            return ChooseMapNodeAction(next_nodes[idx])
        return StateAction(requires_game_ready=False)

    # ── 宝箱 ──────────────────────────────────────────────────────────────────
    if action_str == "open_chest":
        return OpenChestAction()

    # ── 事件 ──────────────────────────────────────────────────────────────────
    if action_str.startswith("choose_event_"):
        try:
            idx = int(action_str.split("_")[-1])
        except ValueError:
            return ProceedAction()
        options = getattr(screen, "options", []) if screen else []
        if idx < len(options):
            return EventOptionAction(options[idx])
        return ProceedAction()

    # ── 休息点 ────────────────────────────────────────────────────────────────
    if action_str.startswith("rest_"):
        option_name = action_str[5:]
        try:
            return RestAction(RestOption[option_name])
        except KeyError:
            return ProceedAction()

    # ── 商店 ──────────────────────────────────────────────────────────────────
    if action_str == "enter_shop":
        return ChooseShopkeeperAction()

    if action_str == "shop_leave":
        return CancelAction()

    if action_str == "shop_purge":
        # BuyPurgeAction() 不带牌 -> 触发 GRID 选牌界面，由 _decide_grid 选最差牌
        return BuyPurgeAction()

    if action_str.startswith("buy_card_"):
        try:
            idx = int(action_str.split("_")[-1])
        except ValueError:
            return CancelAction()
        # BuyCardAction 也用 card.name，中文客户端乱码。改用索引。
        # 商店 choice_list 顺序：cards 列表的下标即为 choose index。
        cards = getattr(screen, "cards", []) if screen else []
        if idx < len(cards):
            return ChooseAction(choice_index=idx)
        return CancelAction()

    if action_str.startswith("buy_relic_"):
        try:
            idx = int(action_str.split("_")[-1])
        except ValueError:
            return CancelAction()
        # 遗物在 choice_list 中排在卡牌之后。
        cards  = getattr(screen, "cards",  []) if screen else []
        relics = getattr(screen, "relics", []) if screen else []
        if idx < len(relics):
            return ChooseAction(choice_index=len(cards) + idx)
        return CancelAction()

    # ── Grid 选牌 ─────────────────────────────────────────────────────────────
    if action_str.startswith("grid_select_"):
        parts = action_str[len("grid_select_"):].split("_")
        try:
            indices = [int(p) for p in parts if p.isdigit()]
        except ValueError:
            return ProceedAction()
        cards = getattr(screen, "cards", []) if screen else []
        selected = [cards[i] for i in indices if i < len(cards)]
        if selected:
            return CardSelectAction(selected)
        return ProceedAction()

    # ── Hand Select ───────────────────────────────────────────────────────────
    if action_str.startswith("hand_select_"):
        parts = action_str[len("hand_select_"):].split("_")
        try:
            indices = [int(p) for p in parts if p.isdigit()]
        except ValueError:
            return ProceedAction()
        cards = getattr(screen, "cards", []) if screen else []
        selected = [cards[i] for i in indices if i < len(cards)]
        if selected:
            return CardSelectAction(selected)
        return ProceedAction()

    log(f"[warn] unknown action '{action_str}', sending state")
    return StateAction(requires_game_ready=False)


def on_state_change(game_state):
    global _last_state_fingerprint

    in_combat      = bool(getattr(game_state, "in_combat",         False))
    play_available = bool(getattr(game_state, "play_available",    False))
    end_available  = bool(getattr(game_state, "end_available",     False))
    proceed_avail  = bool(getattr(game_state, "proceed_available", False))
    choice_avail   = bool(getattr(game_state, "choice_available",  False))
    screen_type    = getattr(game_state, "screen_type", None)

    # 快速推进（不拦截需要 AI 决策的屏幕）
    if proceed_avail and screen_type not in _NO_INTERCEPT:
        return ProceedAction()

    # 既没有可操作的标志，也不是我们处理的屏幕 -> 等待
    can_act = (play_available or end_available or choice_avail
               or screen_type in _ACTIVE_SCREENS)
    if not can_act:
        return StateAction(requires_game_ready=False)

    # ── 读取玩家状态 ──────────────────────────────────────────────────────────
    current_hp = getattr(game_state, "current_hp", None)
    max_hp     = getattr(game_state, "max_hp",     80)
    gold       = getattr(game_state, "gold",       0)
    act        = getattr(game_state, "act",        1)
    floor_num  = getattr(game_state, "floor",      1)

    if in_combat and getattr(game_state, "player", None) is not None:
        player_hp = getattr(game_state.player, "current_hp", current_hp)
        energy    = getattr(game_state.player, "energy",     0)
    else:
        player_hp = current_hp
        energy    = 0

    hand_names   = _parse_hand(game_state)  if in_combat else []
    enemy_intent = _parse_enemy_intent(game_state) if in_combat else "unknown"

    screen      = getattr(game_state, "screen", None)
    screen_name = screen_type.name if screen_type else "NONE"

    # ── 各屏幕特定数据提取 ────────────────────────────────────────────────────

    # 地图
    map_nodes, boss_available = [], False
    if screen_type == ScreenType.MAP and screen is not None:
        raw_nodes      = getattr(screen, "next_nodes", []) or []
        map_nodes      = [{"symbol": n.symbol, "x": n.x, "y": n.y} for n in raw_nodes]
        boss_available = bool(getattr(screen, "boss_available", False))

    # 卡牌奖励 / 战斗奖励
    reward_cards, combat_rewards = [], []
    if screen_type == ScreenType.CARD_REWARD   and screen is not None:
        reward_cards   = list(getattr(screen, "cards",   []) or [])
    if screen_type == ScreenType.COMBAT_REWARD and screen is not None:
        combat_rewards = list(getattr(screen, "rewards", []) or [])

    # Boss 遗物
    boss_relics = []
    if screen_type == ScreenType.BOSS_REWARD and screen is not None:
        boss_relics = list(getattr(screen, "relics", []) or [])

    # 宝箱
    chest_open = False
    if screen_type == ScreenType.CHEST and screen is not None:
        chest_open = bool(getattr(screen, "chest_open", False))

    # 事件
    event_id, event_options = "", []
    if screen_type == ScreenType.EVENT and screen is not None:
        event_id = getattr(screen, "event_id", "")
        opts     = getattr(screen, "options", []) or []
        event_options = [
            {"text":     getattr(o, "text",    ""),
             "disabled": getattr(o, "disabled", False),
             "choice_index": getattr(o, "choice_index", i)}
            for i, o in enumerate(opts)
        ]

    # 休息点
    has_rested, rest_options = False, []
    if screen_type == ScreenType.REST and screen is not None:
        has_rested   = bool(getattr(screen, "has_rested",    False))
        rest_options = list(getattr(screen, "rest_options",  []) or [])

    # 商店
    shop_cards, shop_relics   = [], []
    purge_available, purge_cost = False, 9999
    if screen_type == ScreenType.SHOP_SCREEN and screen is not None:
        shop_cards      = list(getattr(screen, "cards",           []) or [])
        shop_relics     = list(getattr(screen, "relics",          []) or [])
        purge_available = bool(getattr(screen, "purge_available", False))
        purge_cost      = getattr(screen, "purge_cost", 9999)

    # Grid
    grid_cards, grid_num, for_upgrade, for_purge = [], 1, False, False
    if screen_type == ScreenType.GRID and screen is not None:
        grid_cards  = list(getattr(screen, "cards",      []) or [])
        grid_num    = getattr(screen, "num_cards",        1)
        for_upgrade = bool(getattr(screen, "for_upgrade", False))
        for_purge   = bool(getattr(screen, "for_purge",   False))

    # Hand Select
    hand_select_cards, hand_select_num = [], 1
    if screen_type == ScreenType.HAND_SELECT and screen is not None:
        hand_select_cards = list(getattr(screen, "cards",     []) or [])
        hand_select_num   = getattr(screen, "num_cards",      1)

    # ── 去重 ──────────────────────────────────────────────────────────────────
    fingerprint = (
        in_combat, play_available, screen_name,
        player_hp, energy, tuple(hand_names), enemy_intent,
        tuple(n["symbol"] for n in map_nodes), boss_available,
        tuple(getattr(c, "card_id", "") for c in reward_cards),
        len(combat_rewards),
        gold, has_rested, chest_open, event_id,
        tuple(getattr(c, "card_id", "") for c in shop_cards),
        tuple(getattr(r, "relic_id", "") for r in boss_relics),
        tuple(getattr(c, "card_id", "") for c in grid_cards),
        _decision._visited_shop,        # 商店状态也进指纹，防止重复进店
    )
    if fingerprint == _last_state_fingerprint:
        return StateAction(requires_game_ready=False)
    _last_state_fingerprint = fingerprint

    # ── 日志 ──────────────────────────────────────────────────────────────────
    def _ids(cards):
        return [getattr(c, "name", getattr(c, "card_id", "?")) for c in cards]

    if screen_type == ScreenType.MAP:
        log(f"[MAP] nodes={[n['symbol'] for n in map_nodes]}  boss={boss_available}")
    elif screen_type == ScreenType.CARD_REWARD:
        log(f"[CARD_REWARD] {_ids(reward_cards)}")
    elif screen_type == ScreenType.COMBAT_REWARD:
        log(f"[COMBAT_REWARD] {[getattr(getattr(r,'reward_type',None),'name','?') for r in combat_rewards]}")
    elif screen_type == ScreenType.BOSS_REWARD:
        log(f"[BOSS_REWARD] {[getattr(r,'relic_id','?') for r in boss_relics]}")
    elif screen_type == ScreenType.CHEST:
        log(f"[CHEST] open={chest_open}")
    elif screen_type == ScreenType.EVENT:
        log(f"[EVENT] id={event_id}  opts={len(event_options)}")
    elif screen_type == ScreenType.REST:
        log(f"[REST] opts={[o.name for o in rest_options]}  hp={player_hp}/{max_hp}")
    elif screen_type == ScreenType.SHOP_ROOM:
        log(f"[SHOP_ROOM] gold={gold}")
    elif screen_type == ScreenType.SHOP_SCREEN:
        log(f"[SHOP] gold={gold}  cards={_ids(shop_cards)}")
    elif screen_type == ScreenType.GRID:
        log(f"[GRID] n={grid_num}  upgrade={for_upgrade}  purge={for_purge}")
    elif screen_type == ScreenType.HAND_SELECT:
        log(f"[HAND_SELECT] n={hand_select_num}")
    elif in_combat:
        log(f"HP:{player_hp}  E:{energy}  Hand:{hand_names}  Enemy:{enemy_intent}")

    # ── AI 决策 ────────────────────────────────────────────────────────────────
    state_dict = {
        # 玩家基础
        "player_hp":         player_hp,
        "current_hp":        current_hp,
        "max_hp":            max_hp,
        "gold":              gold,
        "act":               act,
        "floor":             floor_num,
        "energy":            energy,
        "hand":              hand_names,
        "enemy_intent":      enemy_intent,
        "screen_type":       screen_name,
        "choice_available":  choice_avail,
        # 地图
        "map_nodes":         map_nodes,
        "boss_available":    boss_available,
        # 奖励
        "reward_cards":      reward_cards,
        "combat_rewards":    combat_rewards,
        "boss_relics":       boss_relics,
        # 宝箱
        "chest_open":        chest_open,
        # 事件
        "event_id":          event_id,
        "event_options":     event_options,
        # 休息
        "has_rested":        has_rested,
        "rest_options":      rest_options,
        # 商店
        "shop_cards":        shop_cards,
        "shop_relics":       shop_relics,
        "purge_available":   purge_available,
        "purge_cost":        purge_cost,
        # Grid
        "grid_cards":        grid_cards,
        "grid_num_cards":    grid_num,
        "for_upgrade":       for_upgrade,
        "for_purge":         for_purge,
        # Hand Select
        "hand_select_cards": hand_select_cards,
        "hand_select_num":   hand_select_num,
        # 原始对象
        "raw":               game_state,
    }

    action_str  = _decision.decide_action(state_dict)
    explanation = explain_action(state_dict, action_str)
    log(f"-> {action_str}  ({explanation})")
    log("-" * 40)

    return _build_spirecomm_action(action_str, game_state)


def on_out_of_game():
    return StateAction(requires_game_ready=False)


def on_error(error: str):
    log(f"[error] {error}")
    return StateAction(requires_game_ready=False)


def main():
    coordinator = Coordinator()
    coordinator.signal_ready()
    coordinator.register_state_change_callback(on_state_change)
    coordinator.register_out_of_game_callback(on_out_of_game)
    coordinator.register_command_error_callback(on_error)
    coordinator.run()


if __name__ == "__main__":
    main()
