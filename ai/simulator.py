"""
ai/simulator.py — 单回合 DFS 最优出牌序列规划器

算法（参考 bottled_ai / xaved88，MIT License）:
  1. 枚举手牌中所有合法出牌排列（满足能量约束）
  2. 对每条序列模拟最终战斗状态
  3. 以评分函数打分，返回评分最高序列的第一张牌

复杂度: 手牌 N 张，最差 O(N!) 但能量限制极大剪枝。
实测起始牌组（5 张，3 能量）约 20~40 个合法节点。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

from spirecomm.spire.character import Intent
from ai.card_stats import IRONCLAD_STATS, JUNK_IDS, get_card_stats


# ─────────────────────────────────────────────────────────────────────────────
# 辅助：从 game_state 中读取数值
# ─────────────────────────────────────────────────────────────────────────────

def _player_strength(raw) -> int:
    """玩家当前力量值（Power id contains 'strength'）。"""
    player = getattr(raw, "player", None)
    if player is None:
        return 0
    for p in (getattr(player, "powers", None) or []):
        pid = (getattr(p, "power_id", "") or "").lower()
        if "strength" in pid:
            try:
                return int(getattr(p, "amount", 0) or 0)
            except (TypeError, ValueError):
                pass
    return 0


def _enemy_vuln_stacks(raw) -> int:
    """第一个存活怪物的易伤层数。"""
    for m in (getattr(raw, "monsters", None) or []):
        if getattr(m, "is_gone", True):
            continue
        for p in (getattr(m, "powers", None) or []):
            pid = (getattr(p, "power_id", "") or "").lower()
            if "vulnerable" in pid:
                try:
                    return max(0, int(getattr(p, "amount", 0) or 0))
                except (TypeError, ValueError):
                    pass
        return 0  # 第一个活怪没有易伤
    return 0


def _enemy_weak_stacks(raw) -> int:
    """第一个存活怪物的虚弱层数。"""
    for m in (getattr(raw, "monsters", None) or []):
        if getattr(m, "is_gone", True):
            continue
        for p in (getattr(m, "powers", None) or []):
            pid = (getattr(p, "power_id", "") or "").lower()
            if "weak" in pid:
                try:
                    return max(0, int(getattr(p, "amount", 0) or 0))
                except (TypeError, ValueError):
                    pass
        return 0
    return 0


def _incoming_damage(raw) -> int:
    """本回合预计承受伤害（含弱化修正）。"""
    total = 0
    for m in (getattr(raw, "monsters", None) or []):
        if getattr(m, "is_gone", True) or getattr(m, "half_dead", False):
            continue
        intent = getattr(m, "intent", None)
        if intent and intent.is_attack():
            dmg  = getattr(m, "move_adjusted_damage", 0) or 0
            hits = getattr(m, "move_hits", 1) or 1
            try:
                total += max(0, int(dmg)) * max(1, int(hits))
            except (TypeError, ValueError):
                total += 5
    return total


def _alive_monster_count(raw) -> int:
    return sum(
        1 for m in (getattr(raw, "monsters", None) or [])
        if not getattr(m, "is_gone", True)
        and not getattr(m, "half_dead", False)
        and getattr(m, "current_hp", 0) > 0
    )


def _strike_count(raw) -> int:
    """牌组+手牌中所有含 'strike' 的牌数量（Perfected Strike 加成用）。"""
    deck = list(getattr(raw, "deck", None) or [])
    hand = list(getattr(raw, "hand", None) or [])
    count = 0
    for c in deck + hand:
        cid  = (getattr(c, "card_id", "") or "").lower()
        name = (getattr(c, "name", "") or "").lower()
        if "strike" in cid or "strike" in name:
            count += 1
    return count


# ─────────────────────────────────────────────────────────────────────────────
# 模拟状态
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SimState:
    energy:       int
    player_block: int   # 当前格挡（已有 + 本回合获得）
    enemy_vuln:   int   # 易伤层数
    enemy_weak:   int   # 虚弱层数
    damage_total: int   # 本回合对敌人造成的总伤害
    cards_played: List  = field(default_factory=list)

    def clone(self) -> "SimState":
        return SimState(
            energy       = self.energy,
            player_block = self.player_block,
            enemy_vuln   = self.enemy_vuln,
            enemy_weak   = self.enemy_weak,
            damage_total = self.damage_total,
            cards_played = self.cards_played[:],
        )


# ─────────────────────────────────────────────────────────────────────────────
# 核心：单张牌的模拟
# ─────────────────────────────────────────────────────────────────────────────

def _simulate_play(card, state: SimState,
                   player_strength: int, strike_count: int) -> Optional[SimState]:
    """
    模拟打出一张牌，返回更新后的 SimState；
    如果打不了（能量不足、不在数据表）返回 None。
    """
    cost = getattr(card, "cost", 1)
    if cost == -1:
        # X-cost (Whirlwind): 花费所有剩余能量
        cost = state.energy

    if cost > state.energy:
        return None

    s = state.clone()
    s.energy -= cost
    s.cards_played.append(card)

    cid = getattr(card, "card_id", "")

    # ── 特殊牌处理 ─────────────────────────────────────────
    # Entrench: 格挡翻倍
    if cid == "Entrench":
        s.player_block *= 2
        return s

    # Seeing Red: 获得 2 能量
    if cid in ("Seeing Red", "Seeing Red+"):
        s.energy += 2
        return s

    # Body Slam: 伤害 = 当前格挡
    if cid in ("Body Slam", "Body Slam+"):
        vuln_mult = 1.5 if s.enemy_vuln > 0 else 1.0
        s.damage_total += int(s.player_block * vuln_mult)
        return s

    # Whirlwind: 每能量点打一次
    if cid.startswith("Whirlwind"):
        hit_count = cost  # cost 已等于 energy（X-cost 逻辑）
        dmg_per_hit = (8 if getattr(card, "upgrades", 0) else 5)
        if player_strength > 0:
            dmg_per_hit += player_strength
        vuln_mult = 1.5 if s.enemy_vuln > 0 else 1.0
        s.damage_total += int(dmg_per_hit * vuln_mult) * hit_count
        s.energy = 0
        return s

    # ── 通用路径：查数据表 ─────────────────────────────────
    stats = get_card_stats(card,
                           player_strength=player_strength,
                           strike_count=strike_count,
                           current_vuln=s.enemy_vuln)
    if stats is None:
        # 不在数据表中 —— 保守估计：0伤0挡，但正常扣能量
        return s

    s.player_block  += stats["block"]
    s.damage_total  += stats["dmg_total"]
    s.enemy_vuln    += stats["apply_vuln"]
    s.enemy_weak    += stats["apply_weak"]

    return s


# ─────────────────────────────────────────────────────────────────────────────
# 评分函数
# ─────────────────────────────────────────────────────────────────────────────

def _score(state: SimState, incoming: int, multi_monster: bool) -> float:
    """
    评分越高越好。

    设计原则（参考 bottled_ai weighted factors）:
      - 伤害贡献最大（终局是杀死敌人）
      - 格挡有价值，但只在 <= incoming 时有效
      - 施加 Vulnerable 有乘数价值（影响后续多回合）
      - 能量浪费扣分
    """
    # 有效格挡（超过来袭伤害的格挡价值减半）
    effective_block = min(state.player_block, incoming)
    excess_block    = max(0, state.player_block - incoming) * 0.3

    # Vulnerable 价值：假设后续还有 3 次攻击，每次约 6 伤
    vuln_future_value = state.enemy_vuln * 6 * 0.5 * 3  # 0.5 = 50%增伤的价值

    score = (
        state.damage_total   * 1.0
        + effective_block    * 2.0
        + excess_block
        + vuln_future_value
    )
    return score


# ─────────────────────────────────────────────────────────────────────────────
# DFS 枚举
# ─────────────────────────────────────────────────────────────────────────────

def plan_best_sequence(raw) -> list:
    """
    对当前手牌枚举所有合法出牌序列，返回最优序列（Card 列表）。
    空列表 = 没有可打的牌（应结束回合）。
    """
    hand = list(getattr(raw, "hand", None) or [])
    player = getattr(raw, "player", None)
    if player is None:
        return []

    energy        = getattr(player, "energy", 0) or 0
    player_block  = getattr(player, "block",  0) or 0
    pstr          = _player_strength(raw)
    s_count       = _strike_count(raw)
    incoming      = _incoming_damage(raw)
    multi_monster = _alive_monster_count(raw) > 1

    # 只考虑可出的非垃圾牌
    candidates = [
        c for c in hand
        if getattr(c, "is_playable", False)
        and getattr(c, "card_id", "") not in JUNK_IDS
    ]

    if not candidates:
        return []

    initial = SimState(
        energy       = energy,
        player_block = player_block,
        enemy_vuln   = _enemy_vuln_stacks(raw),
        enemy_weak   = _enemy_weak_stacks(raw),
        damage_total = 0,
        cards_played = [],
    )

    best_score:    float = -1e9
    best_sequence: list  = []

    def dfs(remaining: list, state: SimState) -> None:
        nonlocal best_score, best_sequence

        # 给当前节点打分
        sc = _score(state, incoming, multi_monster)
        if sc > best_score:
            best_score    = sc
            best_sequence = state.cards_played[:]

        # 剪枝: 没有可打的牌
        any_playable = False
        for card in remaining:
            cost = getattr(card, "cost", 1)
            if cost == -1:
                cost = state.energy
            if cost <= state.energy:
                any_playable = True
                break
        if not any_playable:
            return

        for i, card in enumerate(remaining):
            new_state = _simulate_play(card, state, pstr, s_count)
            if new_state is None:
                continue
            new_remaining = remaining[:i] + remaining[i+1:]
            dfs(new_remaining, new_state)

    dfs(candidates, initial)
    return best_sequence
