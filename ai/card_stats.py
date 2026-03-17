"""
ai/card_stats.py — Ironclad 卡牌战斗数据表

数据来源: bottled_ai (xaved88, MIT License) + STS Wiki
card_id 格式与 spirecomm GameState.hand[n].card_id 完全一致

字段说明:
  dmg            : 基础伤害（单次，已含升级前）
  dmg_plus       : 升级后基础伤害
  block          : 基础格挡
  block_plus     : 升级后格挡
  hits           : 命中次数（-1 = X花费，每能量1次）
  apply_vuln     : 施加易伤层数
  apply_weak     : 施加虚弱层数
  str_multiplier : 力量加成倍数（默认1，Heavy Blade=3/5）
  bonus_per_strike: Perfected Strike 每张"strike"牌加伤
  aoe            : 是否打全体
  exhausts       : 是否消耗
"""

# key = spirecomm card.card_id  (大小写与游戏一致)
IRONCLAD_STATS: dict = {

    # ── 起始牌 ────────────────────────────────────────────
    "Strike_R": {
        "dmg": 6,  "dmg_plus": 9,
        "block": 0, "hits": 1,
    },
    "Defend_R": {
        "dmg": 0,
        "block": 5, "block_plus": 8, "hits": 0,
    },
    "Bash": {
        "dmg": 8,  "dmg_plus": 10,
        "block": 0, "hits": 1,
        "apply_vuln": 2, "apply_vuln_plus": 3,
    },

    # ── 普通攻击 ──────────────────────────────────────────
    "Anger": {
        "dmg": 6,  "dmg_plus": 8,
        "block": 0, "hits": 1,
    },
    "Cleave": {
        "dmg": 8,  "dmg_plus": 11,
        "block": 0, "hits": 1, "aoe": True,
    },
    "Clothesline": {
        "dmg": 12, "dmg_plus": 14,
        "block": 0, "hits": 1,
        "apply_weak": 2, "apply_weak_plus": 3,
    },
    "Heavy Blade": {
        "dmg": 14,
        "block": 0, "hits": 1,
        "str_multiplier": 3, "str_multiplier_plus": 5,
    },
    "Iron Wave": {
        "dmg": 5,  "dmg_plus": 7,
        "block": 5, "block_plus": 7, "hits": 1,
    },
    "Perfected Strike": {
        "dmg": 6,
        "block": 0, "hits": 1,
        "bonus_per_strike": 2, "bonus_per_strike_plus": 3,
    },
    "Pommel Strike": {
        "dmg": 9,  "dmg_plus": 10,
        "block": 0, "hits": 1,
    },
    "Twin Strike": {
        "dmg": 5,  "dmg_plus": 7,
        "block": 0, "hits": 2,
    },
    "Wild Strike": {
        "dmg": 12, "dmg_plus": 17,
        "block": 0, "hits": 1,
    },
    "Headbutt": {
        "dmg": 9,  "dmg_plus": 12,
        "block": 0, "hits": 1,
    },
    "Uppercut": {
        "dmg": 13, "dmg_plus": 13,
        "block": 0, "hits": 1,
        "apply_vuln": 1, "apply_vuln_plus": 2,
        "apply_weak": 1, "apply_weak_plus": 2,
    },
    "Thunderclap": {
        "dmg": 4,  "dmg_plus": 6,
        "block": 0, "hits": 1, "aoe": True,
        "apply_vuln": 1,
    },
    "Carnage": {
        "dmg": 20, "dmg_plus": 28,
        "block": 0, "hits": 1, "exhausts": True,
    },
    "Bludgeon": {
        "dmg": 32, "dmg_plus": 42,
        "block": 0, "hits": 1,
    },
    "Immolate": {
        "dmg": 21, "dmg_plus": 28,
        "block": 0, "hits": 1, "aoe": True,
    },
    "Sword Boomerang": {
        "dmg": 3,  "dmg_plus": 3,
        "block": 0, "hits": 3, "hits_plus": 4,
    },
    "Pummel": {
        "dmg": 2,
        "block": 0, "hits": 4, "hits_plus": 5, "exhausts": True,
    },
    "Feed": {
        "dmg": 10, "dmg_plus": 12,
        "block": 0, "hits": 1,
    },
    "Fiend Fire": {
        "dmg": 7,  "dmg_plus": 10,
        "block": 0, "hits": -2,  # special: hits = hand size, handled separately
        "exhausts": True,
    },
    "Hemokinesis": {
        "dmg": 15, "dmg_plus": 20,
        "block": 0, "hits": 1,
    },
    "Reckless Charge": {
        "dmg": 7,  "dmg_plus": 10,
        "block": 0, "hits": 1,
    },
    "Dropkick": {
        "dmg": 5,  "dmg_plus": 8,
        "block": 0, "hits": 1,
    },
    "Whirlwind": {
        "dmg": 5,  "dmg_plus": 8,
        "block": 0, "hits": -1,  # X-cost: hits = energy spent
        "aoe": True,
    },
    "Reaper": {
        "dmg": 4,  "dmg_plus": 5,
        "block": 0, "hits": 1, "aoe": True, "exhausts": True,
    },
    "Rampage": {
        "dmg": 8,   # grows each play; misc field tracks current value
        "block": 0, "hits": 1,
    },
    "Sever Soul": {
        "dmg": 16, "dmg_plus": 22,
        "block": 0, "hits": 1,
    },
    "Clash": {
        "dmg": 14, "dmg_plus": 18,
        "block": 0, "hits": 1,
        # only playable if all hand cards are attacks — enforced by is_playable
    },
    "Blood for Blood": {
        "dmg": 18, "dmg_plus": 22,
        "block": 0, "hits": 1,
    },
    "Body Slam": {
        "dmg": 0,   # dmg = player.block, handled in simulator
        "block": 0, "hits": 1,
        "dmg_equals_block": True,
    },
    "Spot Weakness": {
        "dmg": 0, "block": 0, "hits": 0,
        # gain Strength if target attacks — too situational to model
    },

    # ── 普通技能 ──────────────────────────────────────────
    "Armaments": {
        "dmg": 0,
        "block": 5, "block_plus": 15, "hits": 0,
    },
    "Shrug It Off": {
        "dmg": 0,
        "block": 8, "block_plus": 11, "hits": 0,
    },
    "True Grit": {
        "dmg": 0,
        "block": 7, "block_plus": 9, "hits": 0, "exhausts": True,
    },
    "Ghostly Armor": {
        "dmg": 0,
        "block": 10, "block_plus": 13, "hits": 0, "exhausts": True,
    },
    "Impervious": {
        "dmg": 0,
        "block": 30, "block_plus": 40, "hits": 0, "exhausts": True,
    },
    "Power Through": {
        "dmg": 0,
        "block": 15, "block_plus": 20, "hits": 0,
    },
    "Second Wind": {
        "dmg": 0,
        "block": 5, "block_plus": 7, "hits": 0,
        # block per non-attack exhausted — too complex, use base estimate
    },
    "Sentinel": {
        "dmg": 0,
        "block": 5, "block_plus": 8, "hits": 0,
    },
    "Flame Barrier": {
        "dmg": 0,
        "block": 12, "block_plus": 16, "hits": 0,
    },
    "Shockwave": {
        "dmg": 0, "block": 0, "hits": 0,
        "apply_vuln": 3, "apply_vuln_plus": 5,
        "apply_weak": 3, "apply_weak_plus": 5,
        "aoe": True, "exhausts": True,
    },
    "Disarm": {
        "dmg": 0, "block": 0, "hits": 0, "exhausts": True,
        # removes enemy strength — modeled as soft utility
    },
    "Intimidate": {
        "dmg": 0, "block": 0, "hits": 0,
        "apply_weak": 1, "apply_weak_plus": 2,
        "aoe": True, "exhausts": True,
    },
    "Flex": {
        "dmg": 0, "block": 0, "hits": 0,
        # temporary +2 Strength this turn — handled separately
    },
    "Seeing Red": {
        "dmg": 0, "block": 0, "hits": 0, "exhausts": True,
        # gain 2 energy
    },
    "Battle Trance": {
        "dmg": 0, "block": 0, "hits": 0,
        # draw 3 — too complex to model mid-turn
    },
    "Entrench": {
        "dmg": 0, "block": 0, "hits": 0,
        # doubles current block — handled separately
    },
    "Warcry": {
        "dmg": 0, "block": 0, "hits": 0, "exhausts": True,
        # draw 1, put card on deck — utility only
    },
    "Burning Pact": {
        "dmg": 0, "block": 0, "hits": 0,
        # exhaust 1, draw 2
    },
    "Dark Shackles": {
        "dmg": 0, "block": 0, "hits": 0, "exhausts": True,
        "apply_weak": 9, "apply_weak_plus": 15,  # enemy loses Strength temporarily
    },
    "Havoc": {
        "dmg": 0, "block": 0, "hits": 0,
        # plays top card of draw pile — too random to model
    },
}

# Upgraded card_ids (spirecomm appends no special suffix for upgrades;
# upgrades are tracked via card.upgrades > 0)
# We handle upgrades inside get_card_stats() by checking card.upgrades.

# Set of card_ids that should NEVER be played (junk)
JUNK_IDS: set = {
    "Slimed", "Wound", "Burn", "Dazed", "Void", "Clumsy", "Parasite",
    "AscendersBane", "Necronomicurse", "Shame", "Injury", "Writhe",
    "Doubt", "Decay", "Regret", "Pain", "Normality", "Pride",
}


def get_card_stats(card, player_strength: int = 0,
                   strike_count: int = 0,
                   current_vuln: int = 0) -> dict | None:
    """
    返回用于模拟器的卡牌效果字典，已应用升级/力量/Vulnerable。

    返回:
      {
        "dmg"        : int,    # 单次命中伤害（含 Vulnerable 加成）
        "block"      : int,    # 格挡量
        "hits"       : int,    # 命中次数（X-cost 卡此处不处理）
        "apply_vuln" : int,    # 施加易伤
        "apply_weak" : int,    # 施加虚弱
        "aoe"        : bool,
        "exhausts"   : bool,
        "dmg_total"  : int,    # 总伤害 = dmg * hits
      }
    返回 None 表示此牌不在数据表中（无法模拟）。
    """
    base = IRONCLAD_STATS.get(card.card_id)
    if base is None:
        return None

    upgraded = getattr(card, "upgrades", 0) > 0

    # ── 基础值（升级版/未升级） ───────────────────────────
    dmg   = base.get("dmg_plus",   base.get("dmg",   0)) if upgraded else base.get("dmg",   0)
    block = base.get("block_plus", base.get("block", 0)) if upgraded else base.get("block", 0)
    hits  = base.get("hits_plus",  base.get("hits",  1)) if upgraded else base.get("hits",  1)

    apply_vuln = (base.get("apply_vuln_plus", base.get("apply_vuln", 0))
                  if upgraded else base.get("apply_vuln", 0))
    apply_weak = (base.get("apply_weak_plus", base.get("apply_weak", 0))
                  if upgraded else base.get("apply_weak", 0))

    str_mult = (base.get("str_multiplier_plus", base.get("str_multiplier", 1))
                if upgraded else base.get("str_multiplier", 1))

    # ── 特殊卡规则 ────────────────────────────────────────
    # Perfected Strike: +2 per strike card in deck+hand
    if "bonus_per_strike" in base:
        bonus = (base.get("bonus_per_strike_plus", base["bonus_per_strike"])
                 if upgraded else base["bonus_per_strike"])
        dmg += bonus * strike_count

    # Heavy Blade: dmg += STR * multiplier
    if str_mult > 1 and player_strength > 0:
        dmg += player_strength * str_mult
    elif dmg > 0 and player_strength > 0:
        dmg += player_strength  # default: +1 per Strength

    # Body Slam: dmg = player block (caller passes via player_strength hack if needed)
    if base.get("dmg_equals_block"):
        dmg = player_strength  # caller passes block as player_strength for Body Slam

    # X-cost (Whirlwind): hits handled by caller
    if hits < 0:
        hits = 0  # caller will compute from energy

    # ── Vulnerable 加成（对攻击牌生效）─────────────────────
    vuln_mult = 1.5 if current_vuln > 0 and dmg > 0 else 1.0
    dmg_with_vuln = int(dmg * vuln_mult)

    return {
        "dmg":        dmg_with_vuln,
        "block":      block,
        "hits":       max(0, hits),
        "apply_vuln": apply_vuln,
        "apply_weak": apply_weak,
        "aoe":        base.get("aoe", False),
        "exhausts":   base.get("exhausts", False),
        "dmg_total":  dmg_with_vuln * max(0, hits),
    }
