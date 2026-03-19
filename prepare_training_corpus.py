import argparse
import json
from collections import Counter
from pathlib import Path

from export_clean_training_table import _clean_record, _drop_reason, _is_noncombat
from export_training_table import (
    build_training_record,
    iter_step_records,
    load_episode_summaries,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build merged behavior-cloning corpora from all collected STS sessions."
    )
    parser.add_argument(
        "--data-dir",
        default="training_data",
        help="Root training_data directory containing multiple session folders.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional output directory. Defaults to <data-dir>/_prepared",
    )
    parser.add_argument(
        "--limit-per-session",
        type=int,
        default=0,
        help="Optional maximum number of raw step records to inspect per session.",
    )
    return parser.parse_args()


def discover_sessions(data_dir: Path) -> list[Path]:
    sessions = []
    for path in sorted(data_dir.iterdir()):
        if not path.is_dir():
            continue
        if any(path.glob("instance-*.jsonl")):
            sessions.append(path)
    return sessions


def write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", errors="backslashreplace") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        raise SystemExit(f"Data directory does not exist: {data_dir}")

    output_dir = Path(args.output_dir).resolve() if args.output_dir else data_dir / "_prepared"
    output_dir.mkdir(parents=True, exist_ok=True)

    sessions = discover_sessions(data_dir)
    if not sessions:
        raise SystemExit(f"No session directories found under: {data_dir}")

    merged_all: list[dict] = []
    merged_noncombat: list[dict] = []
    drop_reasons: Counter = Counter()
    session_rows: list[dict] = []

    for session_dir in sessions:
        episode_summaries = load_episode_summaries(session_dir)
        if not episode_summaries:
            drop_reasons["session_without_episodes"] += 1
            session_rows.append(
                {
                    "session": session_dir.name,
                    "raw_records": 0,
                    "bc_all_rows": 0,
                    "bc_noncombat_rows": 0,
                    "episodes": 0,
                    "status": "skipped_no_episodes",
                }
            )
            continue
        raw_count = 0
        kept_all = 0
        kept_noncombat = 0

        for _, line in iter_step_records(session_dir):
            if args.limit_per_session and raw_count >= args.limit_per_session:
                break
            raw_count += 1
            try:
                step = json.loads(line)
            except json.JSONDecodeError:
                drop_reasons["json_parse_error"] += 1
                continue

            episode_id = str(step.get("episode_id", ""))
            merged = build_training_record(step, episode_summaries.get(episode_id))
            reason = _drop_reason(merged)
            if reason:
                drop_reasons[reason] += 1
                continue

            cleaned = _clean_record(merged)
            merged_all.append(cleaned)
            kept_all += 1
            if _is_noncombat(cleaned):
                merged_noncombat.append(cleaned)
                kept_noncombat += 1

        session_rows.append(
            {
                "session": session_dir.name,
                "raw_records": raw_count,
                "bc_all_rows": kept_all,
                "bc_noncombat_rows": kept_noncombat,
                "episodes": len(episode_summaries),
                "status": "included",
            }
        )

    all_path = output_dir / "training_corpus.bc_all.jsonl"
    noncombat_path = output_dir / "training_corpus.bc_noncombat.jsonl"
    report_path = output_dir / "training_corpus_report.md"
    sessions_index_path = output_dir / "sessions_index.json"

    write_jsonl(all_path, merged_all)
    write_jsonl(noncombat_path, merged_noncombat)
    sessions_index_path.write_text(json.dumps(session_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Training Corpus Report",
        "",
        f"- Sessions discovered: {len(sessions)}",
        f"- Sessions included: {sum(1 for row in session_rows if row.get('status') == 'included')}",
        f"- Total BC rows (all screens): {len(merged_all)}",
        f"- Total BC rows (non-combat): {len(merged_noncombat)}",
        f"- Dropped rows: {sum(drop_reasons.values())}",
        "",
        "## Drop Reasons",
    ]
    if drop_reasons:
        for reason, count in sorted(drop_reasons.items()):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Sessions",
        ]
    )
    for row in session_rows:
        lines.append(
            f"- {row['session']}: raw={row['raw_records']} "
            f"bc_all={row['bc_all_rows']} bc_noncombat={row['bc_noncombat_rows']} "
            f"episodes={row['episodes']}"
        )

    lines.extend(
        [
            "",
            "## Outputs",
            f"- `{all_path}`",
            f"- `{noncombat_path}`",
            f"- `{sessions_index_path}`",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[sessions] {len(sessions)}")
    print(f"[bc_all] {all_path} rows={len(merged_all)}")
    print(f"[bc_noncombat] {noncombat_path} rows={len(merged_noncombat)}")
    print(f"[report] {report_path}")
    print(f"[index] {sessions_index_path}")


if __name__ == "__main__":
    main()
