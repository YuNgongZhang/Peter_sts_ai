"""
ai/card_rewards.py -- 卡牌奖励选择

使用 spirecomm 自带的 IroncladPriority 优先级列表进行评分：
  - 优先级列表中排名 < "Skip" 位置的牌 → 值得拿
  - 排名 >= "Skip" 或不在列表中的牌 → 跳过

优先级来源：spirecomm/ai/priorities.py IroncladPriority
（基于 bottled_ai，MIT License）
"""

from __future__ import annotations
import math
from spirecomm.ai.priorities import IroncladPriority

_priority = IroncladPriority()


def pick_best_reward(cards: list) -> tuple[int | None, object | None]:
    """
    从卡牌奖励列表中选出最优卡。

    返回 (index, card)，或 (None, None) 表示全部不值得拿（跳过）。
    """
    if not cards:
        return None, None

    # 过滤掉低于 Skip 阈值的牌
    worth_taking = [c for c in cards if not _priority.should_skip(c)]
    if not worth_taking:
        return None, None

    best = _priority.get_best_card(worth_taking)
    return cards.index(best), best


def card_priority_score(card) -> float:
    """返回卡牌优先级分数（越低越好）；不在列表中返回 inf。"""
    return _priority.CARD_PRIORITIES.get(
        getattr(card, "card_id", ""), math.inf
    )
