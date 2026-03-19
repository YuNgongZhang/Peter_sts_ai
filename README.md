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
| `ai/card_rewards.py` | Deck-aware scoring for rewards, shop, purge, and upgrades |
| `ai/ironclad_cards.py` | Ironclad card-pool metadata and synergy tags |
| `ai/explanation.py` | Human-readable log annotations |
| `launch_training.py` | Windows launcher for single/multi-instance data collection |
| `run_cloud.ps1` | PowerShell wrapper for cloud dry-run + launch |
| `run_cloud_watchdog.ps1` | PowerShell watchdog for long-running cloud sampling |
| `validate_dataset.py` | JSONL validator for pre-training dataset checks |
| `spirecomm/` | Vendored spirecomm library (ForgottenArbiter, MIT) |

## Decision Tree — Screen Coverage

| Screen | Logic |
|--------|-------|
| **Combat** | DFS over all legal play orderings; scores by damage + block + Vulnerable value |
| `COMBAT_REWARD` | Takes CARD reward to open card selection; proceeds otherwise |
| `CARD_REWARD` | Deck-aware card pick using current deck, relics, floor, and skip threshold |
| `BOSS_REWARD` | `get_best_boss_relic` from IroncladPriority |
| `MAP` | Priority: Elite > Rest > Event > Chest > Shop > Monster |
| `CHEST` | Opens it |
| `EVENT` | Avoids ~15 dangerous events; picks first option otherwise |
| `REST` | HP-based heal logic plus smith only when upgrade value is worth it |
| `SHOP_ROOM` | Enters shop |
| `SHOP_SCREEN` | Purge → deck-aware shop card buy → relic fallback → leave |
| `GRID` / `HAND_SELECT` | Deck-aware upgrade / purge selection |

## Setup

### Prerequisites
- Python 3.11+
- [Slay the Spire](https://store.steampowered.com/app/646570) (Steam)
- [ModTheSpire](https://github.com/kiooeht/ModTheSpire)
- [BaseMod](https://github.com/daviscook477/BaseMod)
- [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod)

### Preferred Setup: Steam Workshop
This project now assumes Steam Workshop is the source of truth for mods.

Required subscriptions:
- subscribe to `BaseMod`
- subscribe to `CommunicationMod`

In this workflow, the training launcher:
- validates the subscribed workshop installs from `C:\Users\<you>\AppData\Local\ModTheSpire\WorkshopInfo.json`
- launches the Steam Workshop copy of `ModTheSpire.jar`
- `ModTheSpire` local selection state (`mod_lists.json`)
- `CommunicationMod` local config (`config.properties`)
- STS / ModTheSpire startup arguments

It does **not** use the game's root `mods/` directory as the primary source of truth.

### Configure CommunicationMod
In `CommunicationMod/config.properties`:
```
command=py -3 D:/sts_ai/main.py
```

If your machine does not expose `py`, replace it with an absolute Python path, for example:
```text
command=C:/Python311/python.exe D:/sts_ai/main.py
```

### Run
For unattended training, launch ModTheSpire directly:
```bash
py -3 launch_training.py --launch-mode modthespire
```

This uses the Workshop-installed `ModTheSpire.jar`, not the copy under the game root.
If Steam is installed in a non-standard place, pass `--steam-root` explicitly.

Use Steam mode only for manual verification:
```bash
py -3 launch_training.py --launch-mode steam
```

### Training / Data Collection
The bot now writes one JSONL file per launched instance. Each line contains:
- current game state snapshot
- chosen action
- action explanation
- episode id / step index / terminal flag
- current full dungeon map snapshot
- session / instance metadata

Default output layout:
```text
training_data/<session_id>/
  instance-0.jsonl
  instance-0.log
  instance-0.episodes.jsonl
  instance-1.jsonl
  instance-1.log
  instance-1.episodes.jsonl
```

Single instance:
```bash
py -3 launch_training.py --launch-mode modthespire --sts-dir "D:\Steam\steamapps\common\SlayTheSpire"
```

Multi-instance:
```bash
py -3 launch_training.py --launch-mode modthespire --sts-dir "D:\Steam\steamapps\common\SlayTheSpire" --instances 3
```

If the Steam root cannot be inferred from `--sts-dir`, add:
```bash
py -3 launch_training.py --steam-root "D:\Steam"
```

If you need a custom launcher command on a cloud machine, use `--launch-mode command`:
```bash
py -3 launch_training.py ^
  --launch-mode command ^
  --command "\"C:\Program Files\Java\bin\java.exe\" -jar \"{sts_dir}\ModTheSpire.jar\"" ^
  --instances 2
```

Important notes:
- `launch_training.py` injects per-instance env vars so each bot process writes to its own dataset/log file.
- `launch_training.py` validates the required Steam Workshop mods before launch.
- `launch_training.py` configures ModTheSpire's local selected-mod list; it does not need to copy mods into the game folder.
- CommunicationMod still launches `main.py`; the launcher only starts game processes.
- For unattended runs, prefer `modthespire` mode instead of `steam`, because Steam mode may still show the ModTheSpire launcher UI.
- Multi-instance support depends on your local Steam / Windows setup. If one machine cannot run multiple copies reliably, use the same script on several cloud machines with different `--session-id` values.
- The current dataset is ideal for imitation learning / offline analysis. If you later want RL, keep this JSONL as the decision trace and add a post-run reward summarizer.

Logs are no longer limited to `sts_state.log`; when launched via `launch_training.py`, each instance writes its own `*.log` file inside `training_data/<session_id>/`.

## GitHub / Cloud Checklist

Before pushing:
- keep `training_data/` out of Git
- keep local IDE folders and runtime logs out of Git
- verify `CommunicationMod/config.properties` on the target machine points to that machine's Python + `main.py`
- verify `--sts-dir` and optionally `--steam-root` match the cloud machine
- do one dry run with `launch_training.py --dry-run` to confirm resolved paths and launch command

On a Windows cloud machine, the shortest path is:
```powershell
.\run_cloud.ps1 -StsDir "D:\Steam\steamapps\common\SlayTheSpire" -SteamRoot "D:\Steam" -Instances 1
```

For unattended long-running sampling with automatic restart:
```powershell
.\run_cloud_watchdog.ps1 -StsDir "D:\Steam\steamapps\common\SlayTheSpire" -SteamRoot "D:\Steam" -Instances 1
```

Dry-run only:
```powershell
.\run_cloud.ps1 -StsDir "D:\Steam\steamapps\common\SlayTheSpire" -SteamRoot "D:\Steam" -DryRunOnly
```

Long-run deployment notes are documented in [CLOUD_SAMPLING_PLAN.md](D:\sts_ai\CLOUD_SAMPLING_PLAN.md).

Validate the latest collected session before training:
```powershell
py -3 validate_dataset.py --data-dir training_data
```

Export the latest validated session into a training-ready table:
```powershell
py -3 export_training_table.py --data-dir training_data
```

Export a specific session:
```powershell
py -3 export_training_table.py --data-dir training_data --session <session_id>
```

The export writes `training_table.jsonl` inside the session directory and joins:
- per-step decision traces from `instance-*.jsonl`
- per-episode outcomes from `instance-*.episodes.jsonl`

Create behavior-cloning-ready cleaned tables from a collected session:
```powershell
py -3 export_clean_training_table.py --data-dir training_data --session <session_id>
```

This writes:
- `training_table.bc_all.jsonl`
- `training_table.bc_noncombat.jsonl`
- `dataset_report.md`

Default cleaning rules:
- drop purely mechanical `GAME_OVER` / `COMPLETE` rows
- drop obvious `possible_state_leak` rows
- keep structured fields and ids; do not rely on noisy text fields for training

Recommended order on a cloud machine with accumulated data:
```powershell
py -3 validate_dataset.py --data-dir training_data --session <session_id>
py -3 export_training_table.py --data-dir training_data --session <session_id>
py -3 export_clean_training_table.py --data-dir training_data --session <session_id>
```

Use `training_table.bc_noncombat.jsonl` first if you want the most stable first-pass BC dataset.

If your cloud machine has many collected sessions under `training_data/`, build one merged corpus:
```powershell
py -3 prepare_training_corpus.py --data-dir training_data
```

This writes a merged corpus under `training_data\_prepared\`:
- `training_corpus.bc_all.jsonl`
- `training_corpus.bc_noncombat.jsonl`
- `training_corpus_report.md`
- `sessions_index.json`

The corpus builder skips sessions that have no episode summaries (`0 episode` sessions).

Optional combat search tuning:
- `STS_AI_DFS_TIMEOUT_MS` controls the per-turn DFS timeout in milliseconds
- `STS_AI_DFS_MAX_NODES` controls the per-turn DFS node budget

## Credits

- [spirecomm](https://github.com/ForgottenArbiter/spirecomm) — ForgottenArbiter (MIT)
- [bottled_ai](https://github.com/xaved88/bottled_ai) — xaved88 (MIT) — card stats and priority data
- [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod) — ForgottenArbiter (MIT)
