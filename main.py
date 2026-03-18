import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

from spirecomm.communication.coordinator import Coordinator
from spirecomm.communication.action import (
    Action,
    StartGameAction,
    StateAction, PlayCardAction, EndTurnAction, ProceedAction, CancelAction,
    ChooseAction, ChooseMapNodeAction, ChooseMapBossAction,
    CardRewardAction, CombatRewardAction, BossRewardAction,
    OpenChestAction, EventOptionAction, RestAction,
    ChooseShopkeeperAction, BuyCardAction, BuyRelicAction, BuyPurgeAction,
    CardSelectAction,
)
from spirecomm.spire.character import Intent, PlayerClass
from spirecomm.spire.card import CardType
from spirecomm.spire.screen import ScreenType, RestOption

import ai.decision as _decision
from ai.explanation import explain_action


BASE_DIR = os.path.dirname(__file__)
DEFAULT_DATA_DIR = os.path.join(BASE_DIR, "training_data")
SESSION_REGISTRY_PATH = os.environ.get(
    "STS_AI_SESSION_REGISTRY",
    os.path.join(DEFAULT_DATA_DIR, "active_session.json"),
)


def _acquire_file_lock(lock_path: str, timeout_seconds: float = 10.0):
    deadline = time.time() + timeout_seconds
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            return fd
        except FileExistsError:
            if time.time() >= deadline:
                raise TimeoutError(f"Timed out waiting for lock: {lock_path}")
            time.sleep(0.05)


def _release_file_lock(fd: int, lock_path: str) -> None:
    os.close(fd)
    try:
        os.unlink(lock_path)
    except FileNotFoundError:
        pass


def _load_active_session_from_registry() -> tuple[str, str, str] | None:
    if not os.path.exists(SESSION_REGISTRY_PATH):
        return None

    os.makedirs(os.path.dirname(SESSION_REGISTRY_PATH), exist_ok=True)
    lock_path = SESSION_REGISTRY_PATH + ".lock"
    fd = _acquire_file_lock(lock_path)
    try:
        with open(SESSION_REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = json.load(f)
        data_dir = registry.get("data_dir") or DEFAULT_DATA_DIR
        session_id = registry.get("session_id") or uuid.uuid4().hex[:12]
        next_instance = int(registry.get("next_instance", 0))
        instance_id = f"instance-{next_instance}"
        registry["next_instance"] = next_instance + 1
        with open(SESSION_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
        return data_dir, session_id, instance_id
    finally:
        _release_file_lock(fd, lock_path)


def _resolve_runtime_paths() -> tuple[str, str, str, str, str]:
    data_dir = os.environ.get("STS_AI_DATA_DIR")
    session_id = os.environ.get("STS_AI_SESSION_ID")
    instance_id = os.environ.get("STS_AI_INSTANCE_ID")

    if not (data_dir and session_id and instance_id):
        registry_values = _load_active_session_from_registry()
        if registry_values is not None:
            data_dir = data_dir or registry_values[0]
            session_id = session_id or registry_values[1]
            instance_id = instance_id or registry_values[2]

    data_dir = data_dir or DEFAULT_DATA_DIR
    session_id = session_id or uuid.uuid4().hex[:12]
    instance_id = instance_id or "instance-0"

    session_dir = os.path.join(data_dir, session_id)
    os.makedirs(session_dir, exist_ok=True)

    jsonl_path = os.environ.get(
        "STS_AI_DATASET_PATH",
        os.path.join(session_dir, f"{instance_id}.jsonl"),
    )
    log_path = os.environ.get(
        "STS_AI_LOG_PATH",
        os.path.join(session_dir, f"{instance_id}.log"),
    )
    return data_dir, session_id, instance_id, jsonl_path, log_path


DATA_DIR, SESSION_ID, INSTANCE_ID, JSONL_PATH, LOG_PATH = _resolve_runtime_paths()


def _read_session_registry() -> dict:
    try:
        with open(SESSION_REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SESSION_REGISTRY = _read_session_registry()
AUTO_START_NEW_RUNS = _env_flag(
    "STS_AI_AUTO_START",
    bool(SESSION_REGISTRY.get("auto_start_new_runs", True)),
)
PLAYER_CLASS_NAME = os.environ.get(
    "STS_AI_PLAYER_CLASS",
    str(SESSION_REGISTRY.get("player_class", "IRONCLAD")),
).upper()
ASCENSION_LEVEL = int(
    os.environ.get(
        "STS_AI_ASCENSION_LEVEL",
        SESSION_REGISTRY.get("ascension_level", 0),
    )
)
RUN_SEED = os.environ.get("STS_AI_SEED") or SESSION_REGISTRY.get("seed")

_last_state_fingerprint: tuple = ()
_start_requested = False

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
    ScreenType.GAME_OVER,
    ScreenType.COMPLETE,
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
    ScreenType.GAME_OVER,
    ScreenType.COMPLETE,
})


def log(line: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    msg = _sanitize_text(f"{timestamp} {line}")
    if sys.stdin.isatty():
        print(msg, file=sys.stderr, flush=True)
    else:
        with open(LOG_PATH, "a", encoding="utf-8", errors="ignore") as f:
            f.write(msg + "\n")


def _sanitize_text(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.encode("utf-8", "replace").decode("utf-8")


def _sanitize_json_compatible(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_json_compatible(v) for v in value]
    if isinstance(value, dict):
        return {
            _sanitize_text(k): _sanitize_json_compatible(v)
            for k, v in value.items()
        }
    return _sanitize_text(repr(value))


def _safe_value(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in value.items()}
    if hasattr(value, "name") and isinstance(getattr(value, "name"), str):
        payload = {"name": getattr(value, "name")}
        for attr in ("card_id", "relic_id", "text", "choice_index", "disabled", "x", "y", "symbol"):
            if hasattr(value, attr):
                payload[attr] = _safe_value(getattr(value, attr))
        return payload
    if hasattr(value, "__dict__"):
        payload = {}
        for key, item in vars(value).items():
            if key.startswith("_") or key == "parent":
                continue
            payload[key] = _safe_value(item)
        if payload:
            return payload
    return repr(value)


def _record_training_example(state_dict, action_str: str, explanation: str) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "session_id": SESSION_ID,
        "instance_id": INSTANCE_ID,
        "floor": state_dict.get("floor"),
        "act": state_dict.get("act"),
        "screen_type": state_dict.get("screen_type"),
        "raw_screen_type": state_dict.get("raw_screen_type"),
        "in_combat": bool(state_dict.get("in_combat")),
        "room_phase": state_dict.get("room_phase"),
        "room_type": state_dict.get("room_type"),
        "turn": state_dict.get("turn"),
        "character": state_dict.get("character"),
        "seed": state_dict.get("seed"),
        "action": _sanitize_text(action_str),
        "explanation": _sanitize_text(explanation),
        "state": {k: _safe_value(v) for k, v in state_dict.items() if k != "raw"},
    }
    safe_record = _sanitize_json_compatible(record)
    with open(JSONL_PATH, "a", encoding="utf-8", errors="backslashreplace") as f:
        f.write(json.dumps(safe_record, ensure_ascii=True) + "\n")


def _get_player_class() -> PlayerClass:
    try:
        return PlayerClass[PLAYER_CLASS_NAME]
    except KeyError:
        log(f"[warn] unknown player class '{PLAYER_CLASS_NAME}', defaulting to IRONCLAD")
        return PlayerClass.IRONCLAD


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


def _parse_deck(game_state) -> list:
    deck = getattr(game_state, "deck", None)
    if deck is None:
        return []
    try:
        return list(deck)
    except TypeError:
        return []


def _parse_relic_ids(game_state) -> list[str]:
    relics = getattr(game_state, "relics", None)
    if relics is None:
        return []
    ids: list[str] = []
    try:
        for relic in relics:
            relic_id = getattr(relic, "relic_id", None)
            if isinstance(relic_id, str) and relic_id.strip():
                ids.append(relic_id)
    except TypeError:
        pass
    return ids


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
    if action_str == "wait":
        return StateAction(requires_game_ready=False)

    if action_str == "proceed":
        return ProceedAction()

    # ── 未知 choice（Neow 等）────────────────────────────────────────────────
    if action_str.startswith("choose_"):
        # choose_0, choose_1, ...
        tail = action_str[len("choose_"):]
        if tail.isdigit():
            return ChooseAction(choice_index=int(tail))

    # ── 战斗奖励 ──────────────────────────────────────────────────────────────
    if action_str == "skip_card_reward":
        # Card reward skip is exposed by CommunicationMod as a left-side skip/return button,
        # not the right-side proceed button.
        return Action(command="skip")

    if action_str == "skip_combat_reward":
        # Once claimable rewards are exhausted, leaving the combat reward screen uses proceed.
        return ProceedAction()

    if action_str == "proceed_combat_reward":
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
            # BossRewardAction 用 relic.name，中文客户端下本地化名称可能导致命令失配。
            # 直接发 choose <index> 更稳定。
            return ChooseAction(choice_index=idx)
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
        cards = getattr(screen, "cards", []) if screen else []
        relics = getattr(screen, "relics", []) if screen else []
        potions = getattr(screen, "potions", []) if screen else []
        purge_index = len(cards) + len(relics) + len(potions)
        return ChooseAction(choice_index=purge_index)

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
    global _last_state_fingerprint, _start_requested
    _start_requested = False

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
    raw_screen_name = screen_type.name if screen_type else "NONE"
    screen_name = "COMBAT" if in_combat and raw_screen_name == "NONE" else raw_screen_name
    room_phase_name = getattr(getattr(game_state, "room_phase", None), "name", "UNKNOWN")
    room_type_name = getattr(game_state, "room_type", "UNKNOWN")
    character_name = getattr(getattr(game_state, "character", None), "name", "UNKNOWN")
    seed_value = getattr(game_state, "seed", None)
    turn_num = getattr(game_state, "turn", 0) if in_combat else 0
    deck_cards = _parse_deck(game_state)
    deck_card_ids = [getattr(card, "card_id", "") for card in deck_cards if getattr(card, "card_id", "")]
    relic_ids = _parse_relic_ids(game_state)

    # ── 各屏幕特定数据提取 ────────────────────────────────────────────────────

    # 地图
    map_nodes, boss_available = [], False
    if screen_type == ScreenType.MAP and screen is not None:
        raw_nodes      = getattr(screen, "next_nodes", []) or []
        map_nodes      = [{"symbol": n.symbol, "x": n.x, "y": n.y} for n in raw_nodes]
        boss_available = bool(getattr(screen, "boss_available", False))

    # 卡牌奖励 / 战斗奖励
    reward_cards, combat_rewards = [], []
    card_reward_can_skip, card_reward_can_bowl = True, False
    if screen_type == ScreenType.CARD_REWARD   and screen is not None:
        reward_cards   = list(getattr(screen, "cards",   []) or [])
        card_reward_can_skip = bool(getattr(screen, "can_skip", True))
        card_reward_can_bowl = bool(getattr(screen, "can_bowl", False))
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
    event_id, event_body_text, event_options = "", "", []
    if screen_type == ScreenType.EVENT and screen is not None:
        event_id = getattr(screen, "event_id", "")
        event_body_text = getattr(screen, "body_text", "")
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
    shop_cards, shop_relics, shop_potions = [], [], []
    purge_available, purge_cost = False, 9999
    if screen_type == ScreenType.SHOP_SCREEN and screen is not None:
        shop_cards      = list(getattr(screen, "cards",           []) or [])
        shop_relics     = list(getattr(screen, "relics",          []) or [])
        shop_potions    = list(getattr(screen, "potions",         []) or [])
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

    # Game Over
    game_over_score, game_over_victory = None, None
    if screen_type == ScreenType.GAME_OVER and screen is not None:
        game_over_score = getattr(screen, "score", None)
        game_over_victory = getattr(screen, "victory", None)

    # ── 去重 ──────────────────────────────────────────────────────────────────
    fingerprint = (
        in_combat, play_available, screen_name,
        player_hp, energy, tuple(hand_names), enemy_intent,
        tuple(n["symbol"] for n in map_nodes), boss_available,
        tuple(getattr(c, "card_id", "") for c in reward_cards),
        card_reward_can_skip, card_reward_can_bowl,
        len(combat_rewards),
        gold, has_rested, chest_open, event_id, _sanitize_text(event_body_text),
        tuple(
            (_sanitize_text(opt.get("text", "")), bool(opt.get("disabled", False)), opt.get("choice_index"))
            for opt in event_options
        ),
        tuple(deck_card_ids),
        tuple(relic_ids),
        tuple(getattr(c, "card_id", "") for c in shop_cards),
        tuple(getattr(p, "potion_id", "") for p in shop_potions),
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
        log(f"[CARD_REWARD] {_ids(reward_cards)}  deck={len(deck_card_ids)} skip={card_reward_can_skip}")
    elif screen_type == ScreenType.COMBAT_REWARD:
        log(f"[COMBAT_REWARD] {[getattr(getattr(r,'reward_type',None),'name','?') for r in combat_rewards]}")
    elif screen_type == ScreenType.BOSS_REWARD:
        log(f"[BOSS_REWARD] {[getattr(r,'relic_id','?') for r in boss_relics]}")
    elif screen_type == ScreenType.CHEST:
        log(f"[CHEST] open={chest_open}")
    elif screen_type == ScreenType.EVENT:
        log(f"[EVENT] id={event_id}  opts={len(event_options)}  body={_sanitize_text(event_body_text)[:80]}")
    elif screen_type == ScreenType.REST:
        log(f"[REST] opts={[o.name for o in rest_options]}  hp={player_hp}/{max_hp}")
    elif screen_type == ScreenType.SHOP_ROOM:
        log(f"[SHOP_ROOM] gold={gold}")
    elif screen_type == ScreenType.SHOP_SCREEN:
        log(
            f"[SHOP] gold={gold}  cards={_ids(shop_cards)}  "
            f"relics={[getattr(r, 'relic_id', '?') for r in shop_relics]}  "
            f"potions={[getattr(p, 'potion_id', '?') for p in shop_potions]}"
        )
    elif screen_type == ScreenType.GRID:
        log(f"[GRID] n={grid_num}  upgrade={for_upgrade}  purge={for_purge}")
    elif screen_type == ScreenType.HAND_SELECT:
        log(f"[HAND_SELECT] n={hand_select_num}")
    elif screen_type == ScreenType.GAME_OVER:
        log(f"[GAME_OVER] victory={game_over_victory} score={game_over_score}")
    elif screen_type == ScreenType.COMPLETE:
        log("[COMPLETE] run finished")
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
        "in_combat":         in_combat,
        "room_phase":        room_phase_name,
        "room_type":         room_type_name,
        "turn":              turn_num,
        "character":         character_name,
        "seed":              seed_value,
        "hand":              hand_names,
        "enemy_intent":      enemy_intent,
        "screen_type":       screen_name,
        "raw_screen_type":   raw_screen_name,
        "choice_available":  choice_avail,
        # 地图
        "map_nodes":         map_nodes,
        "boss_available":    boss_available,
        # 奖励
        "reward_cards":      reward_cards,
        "card_reward_can_skip": card_reward_can_skip,
        "card_reward_can_bowl": card_reward_can_bowl,
        "combat_rewards":    combat_rewards,
        "potions_full":      bool(game_state.are_potions_full()),
        "boss_relics":       boss_relics,
        "deck_cards":        deck_cards,
        "deck_card_ids":     deck_card_ids,
        "relic_ids":         relic_ids,
        # 宝箱
        "chest_open":        chest_open,
        # 事件
        "event_id":          event_id,
        "event_body_text":   event_body_text,
        "event_options":     event_options,
        # 休息
        "has_rested":        has_rested,
        "rest_options":      rest_options,
        # 商店
        "shop_cards":        shop_cards,
        "shop_relics":       shop_relics,
        "shop_potions":      shop_potions,
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
        # Game Over
        "game_over_score":   game_over_score,
        "game_over_victory": game_over_victory,
        # 原始对象
        "raw":               game_state,
    }

    action_str  = _decision.decide_action(state_dict)
    explanation = explain_action(state_dict, action_str)
    _record_training_example(state_dict, action_str, explanation)
    log(f"-> {action_str}  ({explanation})")
    log("-" * 40)

    return _build_spirecomm_action(action_str, game_state)


def on_out_of_game():
    global _start_requested
    if AUTO_START_NEW_RUNS and not _start_requested:
        _start_requested = True
        log(
            f"[OUT_OF_GAME] auto_start class={_get_player_class().name} "
            f"asc={ASCENSION_LEVEL} seed={RUN_SEED or 'random'}"
        )
        return StartGameAction(_get_player_class(), ASCENSION_LEVEL, RUN_SEED)
    return StateAction(requires_game_ready=False)


def on_error(error: str):
    global _start_requested
    _start_requested = False
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
