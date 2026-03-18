"""
ai/card_rewards.py -- Ironclad 牌奖励选择

基础分来自 spirecomm 的 IroncladPriority，
再叠加当前牌组协同、复制上限、前中后期节奏修正。
"""

from __future__ import annotations

from collections import Counter
from copy import copy
import math

from ai.ironclad_cards import (
    AOE_CARDS,
    BLOCK_CARDS,
    BLOCK_PAYOFFS,
    DRAW_CARDS,
    ENERGY_CARDS,
    EXHAUST_ENABLERS,
    EXHAUST_PAYOFFS,
    IRONCLAD_CARD_IDS,
    SELF_DAMAGE_CARDS,
    SELF_DAMAGE_PAYOFFS,
    SLOW_SETUP_CARDS,
    STATUS_GENERATORS,
    STATUS_PAYOFFS,
    STRENGTH_PAYOFFS,
    STRENGTH_SOURCES,
    VULNERABLE_SOURCES,
)
from spirecomm.ai.priorities import IroncladPriority

_priority = IroncladPriority()

_UPGRADE_BONUS = {
    "Armaments": 9.0,
    "Bash": 8.0,
    "Battle Trance": 6.0,
    "Body Slam": 10.0,
    "Blood for Blood": 7.0,
    "Carnage": 6.0,
    "Double Tap": 7.0,
    "Flame Barrier": 6.0,
    "Ghostly Armor": 6.0,
    "Immolate": 6.0,
    "Impervious": 7.0,
    "Limit Break": 12.0,
    "Pommel Strike": 5.0,
    "Searing Blow": 40.0,
    "Shockwave": 8.0,
    "Shrug It Off": 5.0,
    "Thunderclap": 7.0,
    "True Grit": 10.0,
    "Uppercut": 8.0,
    "Whirlwind": 6.0,
}


def pick_best_reward(
    cards: list,
    deck_cards: list | None = None,
    relic_ids: list[str] | None = None,
    floor: int | None = None,
    act: int | None = None,
    can_skip: bool = True,
) -> tuple[int | None, object | None, str]:
    """
    从卡牌奖励列表中选出最优卡。

    返回 (index, card, reason)，或 (None, None, "skip") 表示全部不值得拿。
    """
    if not cards:
        return None, None, "skip_empty"

    scored_cards, skip_threshold = score_reward_options(
        cards,
        deck_cards=deck_cards,
        relic_ids=relic_ids,
        floor=floor,
        act=act,
    )
    best_score, _, best_card, best_reason = max(scored_cards, key=lambda item: item[0])
    if can_skip and best_score < skip_threshold:
        return None, None, "skip_low_value"
    return cards.index(best_card), best_card, best_reason


def pick_best_shop_card(
    cards: list,
    gold: int,
    deck_cards: list | None = None,
    relic_ids: list[str] | None = None,
    floor: int | None = None,
    act: int | None = None,
) -> tuple[int | None, object | None, str]:
    if not cards:
        return None, None, "shop_no_cards"

    scored_cards, buy_threshold = score_shop_card_options(
        cards,
        gold=gold,
        deck_cards=deck_cards,
        relic_ids=relic_ids,
        floor=floor,
        act=act,
    )
    if not scored_cards:
        return None, None, "shop_skip_low_value"
    best_score, best_idx, best_card, best_reason = max(scored_cards, key=lambda item: item[0])
    if best_score < buy_threshold:
        return None, None, "shop_skip_low_value"
    return best_idx, best_card, best_reason


def score_reward_options(
    cards: list,
    deck_cards: list | None = None,
    relic_ids: list[str] | None = None,
    floor: int | None = None,
    act: int | None = None,
) -> tuple[list[tuple[float, int, object, str]], float]:
    deck_cards = list(deck_cards or [])
    relic_ids = list(relic_ids or [])
    profile = _build_deck_profile(deck_cards, relic_ids)
    scored_cards: list[tuple[float, int, object, str]] = []
    for idx, card in enumerate(cards):
        score, reason = _score_candidate(card, profile, floor=floor, act=act)
        scored_cards.append((score, idx, card, reason))
    return scored_cards, _reward_skip_threshold(deck_cards, floor=floor, act=act)


def score_shop_card_options(
    cards: list,
    gold: int,
    deck_cards: list | None = None,
    relic_ids: list[str] | None = None,
    floor: int | None = None,
    act: int | None = None,
) -> tuple[list[tuple[float, int, object, str]], float]:
    deck_cards = list(deck_cards or [])
    relic_ids = list(relic_ids or [])
    profile = _build_deck_profile(deck_cards, relic_ids)
    scored_cards: list[tuple[float, int, object, str]] = []

    for idx, card in enumerate(cards):
        price = int(getattr(card, "price", 9999) or 9999)
        if gold < price:
            continue
        raw_score, reason = _score_candidate(card, profile, floor=floor, act=act)
        value_score = raw_score - (price / 40.0)
        if gold - price < 75:
            value_score -= 1.5
        scored_cards.append((value_score, idx, card, f"shop_{reason}_price={price}"))

    return scored_cards, -1.5


def pick_grid_cards(
    cards: list,
    deck_cards: list | None = None,
    relic_ids: list[str] | None = None,
    floor: int | None = None,
    act: int | None = None,
    num_cards: int = 1,
    for_purge: bool = False,
    for_upgrade: bool = False,
) -> tuple[list[int], str]:
    if not cards or num_cards <= 0:
        return [], "grid_empty"

    deck_cards = list(deck_cards or cards or [])
    relic_ids = list(relic_ids or [])
    profile = _build_deck_profile(deck_cards, relic_ids)
    ranked: list[tuple[float, int, str]] = []

    for idx, card in enumerate(cards):
        if for_purge:
            score = _purge_value(card, profile, floor=floor, act=act)
            ranked.append((score, idx, "purge"))
        elif for_upgrade:
            score = _upgrade_gain(card, profile, floor=floor, act=act)
            ranked.append((score, idx, "upgrade"))
        else:
            score, _ = _score_candidate(card, profile, floor=floor, act=act)
            ranked.append((score, idx, "select"))

    reverse = not for_purge
    ranked.sort(key=lambda item: item[0], reverse=reverse)
    selected = [idx for _, idx, _ in ranked[:num_cards]]
    reason = ranked[0][2] if ranked else "grid_empty"
    return selected, reason


def estimate_best_upgrade_gain(
    cards: list,
    deck_cards: list | None = None,
    relic_ids: list[str] | None = None,
    floor: int | None = None,
    act: int | None = None,
) -> float:
    if not cards:
        return float("-inf")

    deck_cards = list(deck_cards or cards or [])
    relic_ids = list(relic_ids or [])
    profile = _build_deck_profile(deck_cards, relic_ids)
    gains = [_upgrade_gain(card, profile, floor=floor, act=act) for card in cards]
    return max(gains, default=float("-inf"))


def estimate_purge_gain(
    cards: list,
    deck_cards: list | None = None,
    relic_ids: list[str] | None = None,
    floor: int | None = None,
    act: int | None = None,
) -> float:
    if not cards:
        return float("-inf")

    deck_cards = list(deck_cards or cards or [])
    relic_ids = list(relic_ids or [])
    profile = _build_deck_profile(deck_cards, relic_ids)
    purge_values = [_purge_value(card, profile, floor=floor, act=act) for card in cards]
    return -min(purge_values, default=float("inf"))


def _build_deck_profile(deck_cards: list, relic_ids: list[str]) -> dict[str, object]:
    counts = Counter(
        getattr(card, "card_id", "")
        for card in deck_cards
        if getattr(card, "card_id", "")
    )
    deck_ids = list(counts.elements())

    return {
        "counts": counts,
        "deck_size": len(deck_ids),
        "strike_count": sum(1 for card_id in deck_ids if "Strike" in card_id),
        "aoe": sum(counts[card_id] for card_id in AOE_CARDS),
        "draw": sum(counts[card_id] for card_id in DRAW_CARDS),
        "energy": sum(counts[card_id] for card_id in ENERGY_CARDS),
        "strength_sources": sum(counts[card_id] for card_id in STRENGTH_SOURCES),
        "strength_payoffs": sum(counts[card_id] for card_id in STRENGTH_PAYOFFS),
        "block_cards": sum(counts[card_id] for card_id in BLOCK_CARDS),
        "block_payoffs": sum(counts[card_id] for card_id in BLOCK_PAYOFFS),
        "exhaust_enablers": sum(counts[card_id] for card_id in EXHAUST_ENABLERS),
        "exhaust_payoffs": sum(counts[card_id] for card_id in EXHAUST_PAYOFFS),
        "status_generators": sum(counts[card_id] for card_id in STATUS_GENERATORS),
        "status_payoffs": sum(counts[card_id] for card_id in STATUS_PAYOFFS),
        "self_damage": sum(counts[card_id] for card_id in SELF_DAMAGE_CARDS),
        "self_damage_payoffs": sum(counts[card_id] for card_id in SELF_DAMAGE_PAYOFFS),
        "vulnerable_sources": sum(counts[card_id] for card_id in VULNERABLE_SOURCES),
        "relic_ids": set(relic_ids),
    }


def _score_candidate(
    card,
    profile: dict[str, object],
    floor: int | None,
    act: int | None,
) -> tuple[float, str]:
    card_id = getattr(card, "card_id", "")
    base_score = _base_reward_score(card)
    score = base_score
    reasons = [f"base={base_score:.1f}"]

    counts: Counter = profile["counts"]
    copies = counts.get(card_id, 0)
    max_copies = _priority.MAX_COPIES.get(card_id)
    if max_copies is not None and copies >= max_copies:
        score -= 25
        reasons.append("over_copy_cap")
    elif max_copies is not None and copies == max_copies - 1:
        score -= 8
        reasons.append("near_copy_cap")

    act = act or 1
    floor = floor or 0
    early_game = act == 1 and floor <= 16
    late_game = act >= 3 or floor >= 35

    if card_id in AOE_CARDS and profile["aoe"] < 2:
        score += 15
        reasons.append("need_aoe")
    if card_id in DRAW_CARDS and profile["draw"] < 2:
        score += 12
        reasons.append("need_draw")
    if card_id in ENERGY_CARDS and profile["energy"] < 2:
        score += 8
        reasons.append("need_energy")
    if card_id in VULNERABLE_SOURCES and profile["vulnerable_sources"] < 2:
        score += 6
        reasons.append("need_vulnerable")

    strength_sources = int(profile["strength_sources"])
    strength_payoffs = int(profile["strength_payoffs"])
    block_cards = int(profile["block_cards"])
    block_payoffs = int(profile["block_payoffs"])
    exhaust_enablers = int(profile["exhaust_enablers"])
    exhaust_payoffs = int(profile["exhaust_payoffs"])
    status_generators = int(profile["status_generators"])
    status_payoffs = int(profile["status_payoffs"])
    self_damage = int(profile["self_damage"])
    self_damage_payoffs = int(profile["self_damage_payoffs"])
    strike_count = int(profile["strike_count"])
    deck_size = int(profile["deck_size"])
    relic_ids = profile["relic_ids"]

    if card_id in STRENGTH_SOURCES:
        if strength_payoffs > 0:
            score += 14
            reasons.append("strength_engine")
        elif card_id in {"Inflame", "Spot Weakness"}:
            score += 5
            reasons.append("generic_scaling")
    if card_id in STRENGTH_PAYOFFS:
        if strength_sources > 0:
            score += 16
            reasons.append("has_strength")
        elif card_id == "Limit Break":
            score -= 22
            reasons.append("no_strength_to_double")
        elif card_id == "Heavy Blade":
            score -= 8
            reasons.append("low_strength_support")

    if card_id in BLOCK_CARDS and block_payoffs > 0:
        score += 8
        reasons.append("supports_block_plan")
    if card_id in BLOCK_PAYOFFS:
        if block_cards >= 5:
            score += 16
            reasons.append("block_shell_ready")
        else:
            score -= 12
            reasons.append("thin_block_shell")
    if card_id == "Barricade":
        score += 10 if block_cards >= 6 else -16
        reasons.append("barricade_check")
    if card_id == "Entrench":
        score += 8 if block_cards >= 6 else -14
        reasons.append("entrench_check")
    if card_id == "Juggernaut":
        score += 8 if block_cards >= 6 else -10
        reasons.append("juggernaut_check")

    if card_id in EXHAUST_ENABLERS and exhaust_payoffs > 0:
        score += 10
        reasons.append("exhaust_enabled")
    if card_id in EXHAUST_PAYOFFS:
        if exhaust_enablers >= 2:
            score += 14
            reasons.append("exhaust_shell_ready")
        else:
            score -= 6
            reasons.append("light_exhaust_shell")
    if card_id == "Corruption":
        if deck_size >= 12:
            score += 12
            reasons.append("many_skills_likely")
        if exhaust_payoffs > 0:
            score += 14
            reasons.append("corruption_engine")

    if card_id in STATUS_GENERATORS and status_payoffs > 0:
        score += 10
        reasons.append("status_enabled")
    if card_id in STATUS_PAYOFFS:
        if status_generators > 0:
            score += 12
            reasons.append("status_shell_ready")
        else:
            score -= 8
            reasons.append("no_status_generators")

    if card_id in SELF_DAMAGE_CARDS and self_damage_payoffs > 0:
        score += 10
        reasons.append("self_damage_enabled")
    if card_id in SELF_DAMAGE_PAYOFFS:
        if self_damage >= 2:
            score += 14
            reasons.append("self_damage_shell_ready")
        else:
            score -= 10
            reasons.append("not_enough_self_damage")

    if card_id == "Perfected Strike":
        if strike_count >= 6:
            score += 16
            reasons.append("many_strikes")
        elif strike_count <= 4:
            score -= 14
            reasons.append("few_strikes")
    if card_id == "Searing Blow":
        if deck_size <= 18:
            score += 8
            reasons.append("thin_upgrade_plan")
        else:
            score -= 12
            reasons.append("thick_deck_for_searing")

    if early_game:
        if card_id in AOE_CARDS:
            score += 8
            reasons.append("act1_aoe")
        if card_id in {
            "Anger", "Armaments", "Cleave", "Clothesline", "Flame Barrier",
            "Headbutt", "Iron Wave", "Pommel Strike", "Shrug It Off",
            "Spot Weakness", "True Grit", "Twin Strike", "Uppercut",
            "Warcry", "Carnage", "Immolate",
        }:
            score += 8
            reasons.append("act1_tempo")
        if card_id in SLOW_SETUP_CARDS:
            score -= 10
            reasons.append("too_slow_for_act1")
        if card_id == "Armaments":
            score += 6
            reasons.append("act1_upgrade_density")
        if card_id == "Spot Weakness":
            score += 6
            reasons.append("act1_boss_scaling")
        if card_id == "True Grit":
            score += 5
            reasons.append("act1_block_plus_exhaust")
        if card_id == "Warcry" and int(profile["draw"]) < 2:
            score += 4
            reasons.append("act1_cycle_help")

    if late_game and card_id in SLOW_SETUP_CARDS:
        score += 6
        reasons.append("late_game_scaling")

    if "Snecko Eye" in relic_ids:
        cost = getattr(card, "cost", 0)
        if isinstance(cost, int) and cost >= 2:
            score += 12
            reasons.append("snecko_high_cost")
        elif cost == 0:
            score -= 5
            reasons.append("snecko_zero_cost")

    return score, ",".join(reasons)


def _purge_value(
    card,
    profile: dict[str, object],
    floor: int | None,
    act: int | None,
) -> float:
    card_id = getattr(card, "card_id", "")
    keep_score, _ = _score_candidate(card, profile, floor=floor, act=act)
    purge_score = keep_score

    if card_id == "Strike_R":
        purge_score -= 18
    elif card_id == "Defend_R":
        purge_score -= 12
    elif card_id == "Bash":
        purge_score += 6

    if getattr(card, "upgrades", 0) > 0 and card_id != "Searing Blow":
        purge_score += 8

    if card_id in BLOCK_PAYOFFS and int(profile["block_cards"]) >= 5:
        purge_score += 6
    if card_id in STRENGTH_PAYOFFS and int(profile["strength_sources"]) > 0:
        purge_score += 6

    if card_id not in IRONCLAD_CARD_IDS:
        purge_score -= 25

    return purge_score


def _upgrade_gain(
    card,
    profile: dict[str, object],
    floor: int | None,
    act: int | None,
) -> float:
    card_id = getattr(card, "card_id", "")
    current_upgrades = int(getattr(card, "upgrades", 0) or 0)
    if current_upgrades > 0 and card_id != "Searing Blow":
        return float("-inf")

    base_score, _ = _score_candidate(card, profile, floor=floor, act=act)
    upgraded_card = copy(card)
    upgraded_card.upgrades = current_upgrades + 1
    upgraded_score, _ = _score_candidate(upgraded_card, profile, floor=floor, act=act)

    gain = (upgraded_score - base_score) + _UPGRADE_BONUS.get(card_id, 3.0)

    if card_id in STRENGTH_PAYOFFS and int(profile["strength_sources"]) > 0:
        gain += 2
    if card_id in BLOCK_PAYOFFS and int(profile["block_cards"]) >= 5:
        gain += 2
    if card_id in EXHAUST_PAYOFFS and int(profile["exhaust_enablers"]) >= 2:
        gain += 2

    return gain


def _base_reward_score(card) -> float:
    priority = card_priority_score(card)
    if math.isinf(priority):
        card_id = getattr(card, "card_id", "")
        return -5.0 if card_id in IRONCLAD_CARD_IDS else -20.0
    skip_priority = _priority.CARD_PRIORITIES.get("Skip", priority + 1)
    return float(skip_priority - priority)


def card_priority_score(card) -> float:
    """返回卡牌优先级分数（越低越好）；不在列表中返回 inf。"""
    return _priority.CARD_PRIORITIES.get(
        getattr(card, "card_id", ""), math.inf
    )


def _reward_skip_threshold(
    deck_cards: list | None,
    floor: int | None,
    act: int | None,
) -> float:
    deck_size = len(deck_cards or [])
    act = act or 1
    floor = floor or 0
    if act == 1 and floor <= 16 and deck_size <= 18:
        return -18.0
    if act == 1:
        return -14.0
    if act == 2:
        return -12.0
    return -10.0
