# STS AI Coach

A Python bot that plays **Slay the Spire** (Ironclad) automatically — card combat, map routing, rewards, events, shops, campfires, and more — all handled by a rule-based decision tree built on top of [spirecomm](https://github.com/ForgottenArbiter/spirecomm) and [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod).

## Architecture

```
STS (Java) ──CommunicationMod──► spirecomm ──► main.py ──► ai/decision.py ──► Action
```

| File | Role |
|------|------|
| `main.py` | Coordinator setup, state parsing, action builder |
| `ai/decision.py` | Full-game decision tree (11 screen handlers) |
| `ai/simulator.py` | Single-turn DFS card sequence planner |
| `ai/card_stats.py` | Ironclad card data table (damage, block, effects) |
| `ai/card_rewards.py` | Card reward selection via IroncladPriority |
| `ai/explanation.py` | Human-readable log annotations |
| `spirecomm/` | Vendored spirecomm library (ForgottenArbiter, MIT) |

## Decision Tree — Screen Coverage

| Screen | Logic |
|--------|-------|
| **Combat** | DFS over all legal play orderings; scores by damage + block + Vulnerable value |
| `COMBAT_REWARD` | Takes CARD reward to open card selection; proceeds otherwise |
| `CARD_REWARD` | IroncladPriority tier list — picks best card or skips |
| `BOSS_REWARD` | `get_best_boss_relic` from IroncladPriority |
| `MAP` | Priority: Elite > Rest > Event > Chest > Shop > Monster |
| `CHEST` | Opens it |
| `EVENT` | Avoids ~15 dangerous events; picks first option otherwise |
| `REST` | HP < 50% → heal; else smith (upgrade); else other options |
| `SHOP_ROOM` | Enters shop |
| `SHOP_SCREEN` | Purge → buy cards → buy relics → leave |
| `GRID` / `HAND_SELECT` | Best cards for upgrade, worst for purge |

## Setup

### Prerequisites
- Python 3.11+
- [Slay the Spire](https://store.steampowered.com/app/646570) (Steam)
- [ModTheSpire](https://github.com/kiooeht/ModTheSpire)
- [BaseMod](https://github.com/daviscook477/BaseMod)
- [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod)

Use `install_sts_mods.py` to download the required mods automatically:
```bash
# Edit STS_DIR in the script first, then:
python install_sts_mods.py
```

### Configure CommunicationMod
In `CommunicationMod/config.properties`:
```
command=python D:/sts_ai/main.py
```

### Run
Launch Slay the Spire with ModTheSpire. The bot starts automatically when a run begins.

Logs are written to `sts_state.log` in the project root.

## Credits

- [spirecomm](https://github.com/ForgottenArbiter/spirecomm) — ForgottenArbiter (MIT)
- [bottled_ai](https://github.com/xaved88/bottled_ai) — xaved88 (MIT) — card stats and priority data
- [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod) — ForgottenArbiter (MIT)
