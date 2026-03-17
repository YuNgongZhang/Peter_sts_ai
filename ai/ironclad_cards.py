"""
Ironclad card-pool metadata and synergy tags.

Card pool cross-checked against the Slay the Spire Wiki Ironclad card list:
https://slay-the-spire.fandom.com/wiki/Ironclad_Cards
"""

from __future__ import annotations


IRONCLAD_CARD_POOL: dict[str, dict[str, object]] = {
    "Strike_R": {"cost": 1, "summary": "Basic attack.", "roles": ["starter", "attack", "strike", "frontload"]},
    "Defend_R": {"cost": 1, "summary": "Basic block card.", "roles": ["starter", "skill", "block"]},
    "Bash": {"cost": 2, "summary": "Single-target damage plus Vulnerable.", "roles": ["attack", "frontload", "vulnerable_source"]},
    "Anger": {"cost": 0, "summary": "Cheap attack that shuffles copies into the discard pile.", "roles": ["attack", "frontload", "strength_payoff"]},
    "Armaments": {"cost": 1, "summary": "Gain Block and upgrade cards in hand.", "roles": ["skill", "block", "support"]},
    "Body Slam": {"cost": 1, "summary": "Deals damage equal to current Block.", "roles": ["attack", "block_payoff"]},
    "Clash": {"cost": 0, "summary": "High damage, but only playable if all cards in hand are attacks.", "roles": ["attack", "frontload"]},
    "Cleave": {"cost": 1, "summary": "Solid early AoE attack.", "roles": ["attack", "aoe", "frontload"]},
    "Clothesline": {"cost": 2, "summary": "Single-target hit that applies Weak.", "roles": ["attack", "frontload", "weak_source"]},
    "Flex": {"cost": 0, "summary": "Temporary Strength for burst turns.", "roles": ["skill", "strength_source", "burst"]},
    "Havoc": {"cost": 1, "summary": "Plays the top card of the draw pile for free.", "roles": ["skill", "cheat_mana", "support"]},
    "Headbutt": {"cost": 1, "summary": "Attack that returns a discard card to the top of the draw pile.", "roles": ["attack", "frontload", "deck_control"]},
    "Heavy Blade": {"cost": 2, "summary": "Single-target attack with strong Strength scaling.", "roles": ["attack", "strength_payoff", "scaling"]},
    "Iron Wave": {"cost": 1, "summary": "Hybrid damage and Block.", "roles": ["attack", "block", "frontload"]},
    "Metallicize": {"cost": 1, "summary": "Power that grants passive Block every turn.", "roles": ["power", "block", "scaling"]},
    "Perfected Strike": {"cost": 2, "summary": "Attack that scales with cards containing Strike in their name.", "roles": ["attack", "strike_payoff", "scaling"]},
    "Pommel Strike": {"cost": 1, "summary": "Damage plus card draw.", "roles": ["attack", "draw", "strike"]},
    "Rage": {"cost": 0, "summary": "Gain Block whenever attacks are played this turn.", "roles": ["skill", "block", "attack_payoff"]},
    "Shrug It Off": {"cost": 1, "summary": "Reliable Block plus draw.", "roles": ["skill", "block", "draw"]},
    "Sword Boomerang": {"cost": 1, "summary": "Multi-hit attack with strong Strength scaling.", "roles": ["attack", "strength_payoff", "multi_hit"]},
    "Thunderclap": {"cost": 1, "summary": "AoE hit that applies Vulnerable.", "roles": ["attack", "aoe", "vulnerable_source"]},
    "True Grit": {"cost": 1, "summary": "Gain Block and exhaust a card.", "roles": ["skill", "block", "exhaust_enabler"]},
    "Twin Strike": {"cost": 1, "summary": "Two-hit attack.", "roles": ["attack", "multi_hit", "strength_payoff", "strike"]},
    "Warcry": {"cost": 0, "summary": "Draw, then put a card from hand back on top of the draw pile.", "roles": ["skill", "draw", "deck_control"]},
    "Wild Strike": {"cost": 1, "summary": "High damage attack that shuffles a Wound.", "roles": ["attack", "frontload", "strike", "status_generator"]},
    "Battle Trance": {"cost": 0, "summary": "Large draw burst with a draw restriction for the rest of the turn.", "roles": ["skill", "draw", "burst"]},
    "Bloodletting": {"cost": 0, "summary": "Lose HP to gain energy.", "roles": ["skill", "energy", "self_damage"]},
    "Burning Pact": {"cost": 1, "summary": "Exhaust a card to draw cards.", "roles": ["skill", "draw", "exhaust_enabler"]},
    "Carnage": {"cost": 2, "summary": "Large frontloaded attack with ethereal downside.", "roles": ["attack", "frontload"]},
    "Combust": {"cost": 1, "summary": "Passive AoE each end of turn at the cost of self-damage.", "roles": ["power", "aoe", "self_damage", "scaling"]},
    "Disarm": {"cost": 1, "summary": "Permanently lowers enemy Strength.", "roles": ["skill", "debuff"]},
    "Dropkick": {"cost": 1, "summary": "Rewards attacking Vulnerable targets with draw and energy.", "roles": ["attack", "vulnerable_payoff", "draw", "energy"]},
    "Dual Wield": {"cost": 1, "summary": "Copies an attack or power in hand.", "roles": ["skill", "copy", "support"]},
    "Entrench": {"cost": 2, "summary": "Doubles current Block.", "roles": ["skill", "block_payoff", "scaling"]},
    "Evolve": {"cost": 1, "summary": "Draw when status cards are drawn.", "roles": ["power", "status_payoff", "draw"]},
    "Feel No Pain": {"cost": 1, "summary": "Gain Block whenever a card is exhausted.", "roles": ["power", "exhaust_payoff", "block"]},
    "Fire Breathing": {"cost": 1, "summary": "Deals AoE damage whenever a status or curse is drawn.", "roles": ["power", "status_payoff", "aoe"]},
    "Flame Barrier": {"cost": 2, "summary": "Big Block plus retaliation damage when attacked.", "roles": ["skill", "block", "frontload"]},
    "Ghostly Armor": {"cost": 1, "summary": "Efficient Block with ethereal downside.", "roles": ["skill", "block"]},
    "Hemokinesis": {"cost": 1, "summary": "High damage attack that costs HP.", "roles": ["attack", "frontload", "self_damage"]},
    "Infernal Blade": {"cost": 1, "summary": "Creates a random attack in hand and exhausts.", "roles": ["skill", "card_generation", "exhaust_enabler"]},
    "Inflame": {"cost": 1, "summary": "Simple permanent Strength source.", "roles": ["power", "strength_source", "scaling"]},
    "Intimidate": {"cost": 0, "summary": "Apply Weak to all enemies and exhaust.", "roles": ["skill", "aoe", "weak_source"]},
    "Power Through": {"cost": 1, "summary": "Huge Block that adds Wounds.", "roles": ["skill", "block", "status_generator"]},
    "Pummel": {"cost": 1, "summary": "Multi-hit attack that exhausts.", "roles": ["attack", "multi_hit", "strength_payoff", "exhaust_enabler"]},
    "Rampage": {"cost": 1, "summary": "Attack that gains permanent damage each time it is played.", "roles": ["attack", "scaling", "deck_control"]},
    "Reckless Charge": {"cost": 0, "summary": "Free attack that shuffles a Dazed.", "roles": ["attack", "frontload", "status_generator"]},
    "Searing Blow": {"cost": 2, "summary": "Single card scaling plan through repeated upgrades.", "roles": ["attack", "scaling"]},
    "Second Wind": {"cost": 1, "summary": "Exhaust non-attacks from hand for Block.", "roles": ["skill", "block", "exhaust_enabler"]},
    "Seeing Red": {"cost": 1, "summary": "Gain energy and exhaust.", "roles": ["skill", "energy", "exhaust_enabler"]},
    "Sentinel": {"cost": 1, "summary": "Basic Block card that refunds energy when exhausted.", "roles": ["skill", "block", "exhaust_payoff", "energy"]},
    "Sever Soul": {"cost": 2, "summary": "Attack that exhausts non-attacks from hand.", "roles": ["attack", "frontload", "exhaust_enabler"]},
    "Shockwave": {"cost": 2, "summary": "AoE Weak plus Vulnerable with exhaust.", "roles": ["skill", "aoe", "vulnerable_source", "weak_source", "exhaust_enabler"]},
    "Spot Weakness": {"cost": 1, "summary": "Conditional permanent Strength gain.", "roles": ["skill", "strength_source", "scaling"]},
    "Uppercut": {"cost": 2, "summary": "Strong attack that applies both Weak and Vulnerable.", "roles": ["attack", "frontload", "vulnerable_source", "weak_source"]},
    "Whirlwind": {"cost": "X", "summary": "Scales AoE damage with available energy.", "roles": ["attack", "aoe", "strength_payoff", "energy_payoff"]},
    "Barricade": {"cost": 3, "summary": "Retain Block between turns.", "roles": ["power", "block_payoff", "scaling"]},
    "Berserk": {"cost": 0, "summary": "Gain Vulnerable to generate extra energy each turn.", "roles": ["power", "energy", "self_setup"]},
    "Bludgeon": {"cost": 3, "summary": "Very large single-target hit.", "roles": ["attack", "frontload"]},
    "Blood for Blood": {"cost": 4, "summary": "Starts expensive, gets cheaper as HP is lost.", "roles": ["attack", "self_damage_payoff", "frontload"]},
    "Brutality": {"cost": 0, "summary": "Lose HP each turn to draw more cards.", "roles": ["power", "draw", "self_damage", "scaling"]},
    "Corruption": {"cost": 3, "summary": "Skills cost 0 and exhaust when played.", "roles": ["power", "exhaust_engine", "scaling"]},
    "Dark Embrace": {"cost": 2, "summary": "Draw whenever cards are exhausted.", "roles": ["power", "exhaust_payoff", "draw"]},
    "Demon Form": {"cost": 3, "summary": "Slow but dominant permanent Strength scaling.", "roles": ["power", "strength_source", "scaling"]},
    "Double Tap": {"cost": 1, "summary": "Next attack is played twice.", "roles": ["skill", "attack_payoff", "burst"]},
    "Exhume": {"cost": 1, "summary": "Returns a random exhausted card to hand and exhausts.", "roles": ["skill", "exhaust_payoff", "recursion"]},
    "Feed": {"cost": 1, "summary": "Attack that permanently raises max HP on kill.", "roles": ["attack", "scaling", "frontload"]},
    "Fiend Fire": {"cost": 2, "summary": "Exhaust the hand for a large finishing burst.", "roles": ["attack", "exhaust_enabler", "frontload"]},
    "Immolate": {"cost": 2, "summary": "Premium AoE attack that adds Burns.", "roles": ["attack", "aoe", "frontload", "status_generator"]},
    "Impervious": {"cost": 2, "summary": "Massive Block with exhaust.", "roles": ["skill", "block", "frontload", "exhaust_enabler"]},
    "Juggernaut": {"cost": 2, "summary": "Turns repeated Block gain into damage.", "roles": ["power", "block_payoff", "scaling"]},
    "Limit Break": {"cost": 1, "summary": "Doubles current Strength.", "roles": ["skill", "strength_payoff", "scaling"]},
    "Offering": {"cost": 0, "summary": "Lose HP to draw cards and gain energy.", "roles": ["skill", "draw", "energy", "self_damage", "burst"]},
    "Reaper": {"cost": 2, "summary": "AoE damage that heals for damage dealt.", "roles": ["attack", "aoe", "strength_payoff", "sustain"]},
    "Rupture": {"cost": 1, "summary": "Gain Strength whenever HP is lost from cards.", "roles": ["power", "self_damage_payoff", "strength_source", "scaling"]},
}

IRONCLAD_CARD_IDS = frozenset(IRONCLAD_CARD_POOL)

AOE_CARDS = frozenset({"Cleave", "Thunderclap", "Whirlwind", "Shockwave", "Intimidate", "Combust", "Immolate", "Reaper", "Fire Breathing"})
DRAW_CARDS = frozenset({"Pommel Strike", "Shrug It Off", "Warcry", "Battle Trance", "Burning Pact", "Dropkick", "Evolve", "Brutality", "Dark Embrace", "Offering", "Exhume"})
ENERGY_CARDS = frozenset({"Bloodletting", "Dropkick", "Seeing Red", "Offering", "Berserk", "Sentinel"})
STRENGTH_SOURCES = frozenset({"Flex", "Inflame", "Spot Weakness", "Demon Form", "Rupture"})
STRENGTH_PAYOFFS = frozenset({"Anger", "Heavy Blade", "Sword Boomerang", "Twin Strike", "Pummel", "Whirlwind", "Reaper", "Limit Break"})
BLOCK_CARDS = frozenset({"Defend_R", "Armaments", "Iron Wave", "Shrug It Off", "True Grit", "Rage", "Metallicize", "Entrench", "Feel No Pain", "Flame Barrier", "Ghostly Armor", "Power Through", "Second Wind", "Sentinel", "Impervious", "Barricade"})
BLOCK_PAYOFFS = frozenset({"Body Slam", "Entrench", "Barricade", "Juggernaut"})
EXHAUST_ENABLERS = frozenset({"True Grit", "Burning Pact", "Infernal Blade", "Pummel", "Second Wind", "Seeing Red", "Sever Soul", "Shockwave", "Exhume", "Fiend Fire", "Impervious", "Corruption"})
EXHAUST_PAYOFFS = frozenset({"Feel No Pain", "Dark Embrace", "Sentinel", "Exhume"})
STATUS_GENERATORS = frozenset({"Wild Strike", "Power Through", "Reckless Charge", "Immolate"})
STATUS_PAYOFFS = frozenset({"Evolve", "Fire Breathing"})
SELF_DAMAGE_CARDS = frozenset({"Bloodletting", "Combust", "Hemokinesis", "Brutality", "Offering", "Berserk"})
SELF_DAMAGE_PAYOFFS = frozenset({"Rupture", "Blood for Blood"})
VULNERABLE_SOURCES = frozenset({"Bash", "Thunderclap", "Shockwave", "Uppercut"})
SLOW_SETUP_CARDS = frozenset({"Barricade", "Berserk", "Brutality", "Corruption", "Dark Embrace", "Demon Form", "Evolve", "Fire Breathing", "Juggernaut", "Rupture"})
