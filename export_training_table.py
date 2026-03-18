import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export raw STS JSONL traces into a training-ready JSONL table."
    )
    parser.add_argument(
        "--data-dir",
        default="training_data",
        help="Root training_data directory or a specific session directory.",
    )
    parser.add_argument(
        "--session",
        default="",
        help="Optional explicit session id directory under --data-dir.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output path. Defaults to <session_dir>/training_table.jsonl",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of step records to export.",
    )
    return parser.parse_args()


def resolve_session_dir(data_dir: Path, session: str) -> Path:
    if session:
        session_dir = data_dir / session
        if not session_dir.exists():
            raise SystemExit(f"Session directory not found: {session_dir}")
        return session_dir

    if data_dir.is_dir() and any(p.suffix == ".jsonl" for p in data_dir.glob("*.jsonl")):
        return data_dir

    sessions = [p for p in data_dir.iterdir() if p.is_dir()]
    if not sessions:
        raise SystemExit(f"No session directories found under: {data_dir}")
    return max(sessions, key=lambda p: p.stat().st_mtime)


def load_episode_summaries(session_dir: Path) -> dict[str, dict]:
    summaries: dict[str, dict] = {}
    for path in sorted(session_dir.glob("*.episodes.jsonl")):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                episode_id = str(record.get("episode_id", ""))
                if episode_id:
                    summaries[episode_id] = record
    return summaries


def iter_step_records(session_dir: Path):
    for path in sorted(session_dir.glob("*.jsonl")):
        if path.name.endswith(".episodes.jsonl"):
            continue
        if path.name == "training_table.jsonl":
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield path, line


def normalize_candidates(candidates) -> list[dict]:
    if not isinstance(candidates, list):
        return []
    normalized = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        normalized.append(
            {
                "action": candidate.get("action"),
                "score": candidate.get("score"),
                "reason": candidate.get("reason"),
            }
        )
    return normalized


def build_training_record(step: dict, episode_summary: dict | None) -> dict:
    state = step.get("state", {}) if isinstance(step.get("state"), dict) else {}
    summary = episode_summary or {}
    return {
        "timestamp": step.get("timestamp"),
        "session_id": step.get("session_id"),
        "instance_id": step.get("instance_id"),
        "episode_id": step.get("episode_id"),
        "step_index": step.get("step_index"),
        "terminal": step.get("terminal"),
        "screen_type": step.get("screen_type"),
        "raw_screen_type": step.get("raw_screen_type"),
        "room_type": step.get("room_type"),
        "room_phase": step.get("room_phase"),
        "character": step.get("character"),
        "seed": step.get("seed"),
        "floor": step.get("floor"),
        "act": step.get("act"),
        "action": step.get("action"),
        "explanation": step.get("explanation"),
        "decision_reason": state.get("_decision_reason"),
        "candidate_actions": normalize_candidates(state.get("_decision_candidates")),
        "state": state,
        "outcome": {
            "victory": summary.get("victory"),
            "score": summary.get("score"),
            "act_reached": summary.get("act_reached"),
            "floor_reached": summary.get("floor_reached"),
            "final_hp": summary.get("final_hp"),
            "max_hp": summary.get("max_hp"),
            "steps": summary.get("steps"),
            "act_boss": summary.get("act_boss"),
        },
    }


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        raise SystemExit(f"Data directory does not exist: {data_dir}")

    session_dir = resolve_session_dir(data_dir, args.session)
    episode_summaries = load_episode_summaries(session_dir)
    output_path = Path(args.output).resolve() if args.output else session_dir / "training_table.jsonl"

    exported = 0
    with open(output_path, "w", encoding="utf-8", errors="backslashreplace") as out:
        for _, line in iter_step_records(session_dir):
            if args.limit and exported >= args.limit:
                break
            try:
                step = json.loads(line)
            except json.JSONDecodeError:
                continue
            episode_id = str(step.get("episode_id", ""))
            summary = episode_summaries.get(episode_id)
            record = build_training_record(step, summary)
            out.write(json.dumps(record, ensure_ascii=True) + "\n")
            exported += 1

    print(f"[session] {session_dir.name}")
    print(f"[output] {output_path}")
    print(f"[episodes] {len(episode_summaries)}")
    print(f"[rows] {exported}")


if __name__ == "__main__":
    main()
