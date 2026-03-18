# Cloud Sampling Plan

## Goal

Run the bot on a Windows cloud machine for long periods, keep the process alive after crashes, and write clean per-session training data for later filtering and model training.

## What Is Stable Enough Now

- The launcher can start Workshop-based ModTheSpire directly.
- The bot can auto-start new runs after death or run completion.
- Per-session and per-instance logs are separated.
- JSONL records now include decision reasons and candidate actions for many major screens.

The bot is still strategically weak. That is acceptable for data collection as long as the control flow remains stable.

## Recommended Cloud Layout

Use one repo checkout per machine:

```text
D:\sts_ai
```

Keep training output under:

```text
D:\sts_ai\training_data\
  watchdog.log
  <session_id>\
    instance-0.log
    instance-0.jsonl
    instance-1.log
    instance-1.jsonl
```

## Recommended Run Mode

For long-running collection, use:

- `run_cloud_watchdog.ps1` for unattended cloud runs
- `run_cloud.ps1` for one-shot validation or manual runs

`run_cloud_watchdog.ps1`:
- creates a fresh `session_id` on each restart
- runs a dry-run before launch
- restarts the launcher when it exits
- appends lifecycle events to `training_data\watchdog.log`

## First Validation On A Cloud Machine

Run:

```powershell
.\run_cloud.ps1 -StsDir "D:\Steam\steamapps\common\SlayTheSpire" -SteamRoot "D:\Steam" -DryRunOnly
```

Then run a single real instance:

```powershell
.\run_cloud.ps1 -StsDir "D:\Steam\steamapps\common\SlayTheSpire" -SteamRoot "D:\Steam" -Instances 1
```

Check:

- the Workshop `ModTheSpire.jar` is used
- `CommunicationMod` points to `main.py`
- `training_data\<session_id>\instance-0.log` is growing
- `training_data\<session_id>\instance-0.jsonl` is growing

## Long-Run Command

Single instance:

```powershell
.\run_cloud_watchdog.ps1 -StsDir "D:\Steam\steamapps\common\SlayTheSpire" -SteamRoot "D:\Steam" -Instances 1
```

Multi-instance:

```powershell
.\run_cloud_watchdog.ps1 -StsDir "D:\Steam\steamapps\common\SlayTheSpire" -SteamRoot "D:\Steam" -Instances 3
```

If you want a fixed seed:

```powershell
.\run_cloud_watchdog.ps1 -StsDir "D:\Steam\steamapps\common\SlayTheSpire" -SteamRoot "D:\Steam" -Instances 1 -Seed "ABC123"
```

## Sampling Policy

Recommended phases:

1. Stability pass
   - 1 instance
   - 2 to 4 hours
   - objective: confirm there are no control-flow stalls

2. Throughput pass
   - 2 to 3 instances per machine
   - objective: maximize decisions per hour without making the machine unstable

3. Fleet pass
   - same repo and same command on multiple cloud machines
   - aggregate all `training_data\<session_id>\*.jsonl`

## What To Monitor

Every few hours, check:

- `training_data\watchdog.log`
- latest `instance-0.log`
- latest `instance-0.jsonl`

Healthy signals:

- repeated `OUT_OF_GAME -> auto_start`
- `GAME_OVER` followed by a new run
- reward, rest, map, and event decisions continue appearing
- JSONL keeps growing

Bad signals:

- repeated identical screen transitions without progress
- no new log lines for several minutes
- watchdog restarting too often
- `communication_mod_errors.log` receiving fresh exceptions

## Data Hygiene

Keep the raw JSONL files unchanged.

Treat them as the source trace for:

- supervised imitation datasets
- offline value-model training
- future reward summarization

Do not overwrite sessions in place. New restarts should create new session folders.

## Recommended Next Step After Collection Starts

Once cloud sampling is stable, add one post-processing script that:

- reads all session JSONL files
- extracts `(state, candidate_actions, chosen_action, outcome tags)`
- writes a compact training table for model training

That should happen after the cloud run is stable, not before.
