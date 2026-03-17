import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path


APP_ID = "646570"
DEFAULT_STEAM_URI = f"steam://launch/{APP_ID}/option1"
WORKSHOP_INFO_PATH = Path(os.environ.get("LOCALAPPDATA", "")) / "ModTheSpire" / "WorkshopInfo.json"
MODTHESPIRE_WORKSHOP_ID = "1605060445"
REQUIRED_WORKSHOP_TITLES = {
    "BaseMod": "BaseMod",
    "Communication Mod": "CommunicationMod",
}


def detect_default_sts_dir() -> str:
    candidates = [
        os.environ.get("STS_DIR"),
        r"D:\Steam\steamapps\common\SlayTheSpire",
        r"C:\Program Files (x86)\Steam\steamapps\common\SlayTheSpire",
        r"C:\Steam\steamapps\common\SlayTheSpire",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return r"C:\Program Files (x86)\Steam\steamapps\common\SlayTheSpire"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch Slay the Spire for bot data collection / training."
    )
    parser.add_argument(
        "--sts-dir",
        default=detect_default_sts_dir(),
        help="Slay the Spire installation directory.",
    )
    parser.add_argument(
        "--steam-root",
        default=os.environ.get("STEAM_ROOT"),
        help="Optional Steam root directory. If omitted, it is inferred from --sts-dir.",
    )
    parser.add_argument(
        "--instances",
        type=int,
        default=1,
        help="How many game instances to launch.",
    )
    parser.add_argument(
        "--launch-mode",
        choices=("modthespire", "steam", "command"),
        default="modthespire",
        help="Use direct ModTheSpire launch for unattended runs, Steam for manual launch, or a custom command template.",
    )
    parser.add_argument(
        "--java",
        default=os.environ.get("JAVA_EXE", "java"),
        help="Java executable used for ModTheSpire mode.",
    )
    parser.add_argument(
        "--player-class",
        default=os.environ.get("STS_AI_PLAYER_CLASS", "IRONCLAD"),
        help="Player class to auto-start from the main menu.",
    )
    parser.add_argument(
        "--ascension-level",
        type=int,
        default=int(os.environ.get("STS_AI_ASCENSION_LEVEL", "0")),
        help="Ascension level used when auto-starting runs.",
    )
    parser.add_argument(
        "--seed",
        default=os.environ.get("STS_AI_SEED"),
        help="Optional fixed seed for repeated training runs.",
    )
    parser.add_argument(
        "--comm-command",
        default=os.environ.get("STS_COMM_COMMAND"),
        help="Exact CommunicationMod command. If omitted, uses the current Python executable and main.py.",
    )
    parser.add_argument(
        "--skip-launcher",
        action="store_true",
        default=True,
        help="Launch ModTheSpire with --skip-launcher.",
    )
    parser.add_argument(
        "--skip-intro",
        action="store_true",
        default=True,
        help="Launch ModTheSpire with --skip-intro.",
    )
    parser.add_argument(
        "--no-auto-start",
        action="store_true",
        help="Disable automatic start of a new run from the main menu.",
    )
    parser.add_argument(
        "--command",
        default=os.environ.get("STS_LAUNCH_COMMAND"),
        help=(
            "Custom launch command template. Available placeholders: "
            "{sts_dir}, {instance}, {session_id}."
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("STS_AI_DATA_DIR", "training_data"),
        help="Root directory for per-instance logs and dataset files.",
    )
    parser.add_argument(
        "--session-id",
        default=os.environ.get("STS_AI_SESSION_ID", uuid.uuid4().hex[:12]),
        help="Shared session id across all launched instances.",
    )
    parser.add_argument(
        "--steam-uri",
        default=os.environ.get("STS_STEAM_URI", DEFAULT_STEAM_URI),
        help="Steam URI used in steam launch mode.",
    )
    parser.add_argument(
        "--startup-delay",
        type=float,
        default=4.0,
        help="Delay in seconds between launching instances.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without launching processes.",
    )
    return parser.parse_args()


def prepare_session_registry(args: argparse.Namespace) -> Path:
    data_dir = Path(args.data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    registry_path = data_dir / "active_session.json"
    payload = {
        "session_id": args.session_id,
        "data_dir": str(data_dir),
        "next_instance": 0,
        "launch_mode": args.launch_mode,
        "auto_start_new_runs": not args.no_auto_start,
        "player_class": args.player_class.upper(),
        "ascension_level": args.ascension_level,
        "seed": args.seed,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return registry_path


def build_comm_command(args: argparse.Namespace) -> str:
    if args.comm_command:
        return args.comm_command
    python_exe = Path(sys.executable).resolve()
    bot_script = (Path(__file__).resolve().parent / "main.py").resolve()
    return f"{python_exe.as_posix()} {bot_script.as_posix()}"


def load_workshop_info() -> list[dict]:
    if not WORKSHOP_INFO_PATH.exists():
        raise SystemExit(
            f"Workshop info not found: {WORKSHOP_INFO_PATH}. "
            "Open ModTheSpire once after subscribing to the workshop mods."
        )
    with open(WORKSHOP_INFO_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise SystemExit(f"Unexpected workshop info format: {WORKSHOP_INFO_PATH}")
    return data


def validate_required_workshop_mods() -> dict[str, dict]:
    workshop_items = load_workshop_info()
    by_title = {
        str(item.get("title", "")).strip(): item
        for item in workshop_items
        if isinstance(item, dict)
    }
    resolved = {}
    missing = []
    for title, short_name in REQUIRED_WORKSHOP_TITLES.items():
        item = by_title.get(title)
        if item is None:
            missing.append(title)
            continue
        install_path = Path(str(item.get("installPath", "")))
        if not install_path.exists():
            raise SystemExit(
                f"Workshop mod '{title}' is registered but installPath does not exist: {install_path}"
            )
        resolved[short_name] = item
    if missing:
        raise SystemExit(
            "Missing required Steam Workshop subscriptions: " + ", ".join(missing)
        )
    return resolved


def resolve_workshop_root(args: argparse.Namespace, sts_dir: Path) -> Path:
    if args.steam_root:
        steam_root = Path(args.steam_root).expanduser().resolve()
        return steam_root / "steamapps" / "workshop" / "content" / APP_ID
    steamapps_dir = sts_dir.parent.parent
    return steamapps_dir / "workshop" / "content" / APP_ID


def resolve_workshop_modthespire_jar(workshop_root: Path) -> Path:
    jar_path = workshop_root / MODTHESPIRE_WORKSHOP_ID / "ModTheSpire.jar"
    if not jar_path.exists():
        raise SystemExit(
            f"Workshop ModTheSpire jar not found: {jar_path}. "
            "Subscribe to the ModTheSpire Steam Workshop item first."
        )
    return jar_path


def write_modthespire_local_config(args: argparse.Namespace) -> Path:
    local_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "ModTheSpire"
    local_dir.mkdir(parents=True, exist_ok=True)

    mod_list_path = local_dir / "mod_lists.json"
    mod_payload = {
        "defaultList": "<Default>",
        "lists": {
            "<Default>": [
                "BaseMod.jar",
                "CommunicationMod.jar",
            ]
        },
    }
    with open(mod_list_path, "w", encoding="utf-8") as f:
        json.dump(mod_payload, f, ensure_ascii=False, indent=2)

    comm_dir = local_dir / "CommunicationMod"
    comm_dir.mkdir(parents=True, exist_ok=True)
    config_path = comm_dir / "config.properties"
    config_text = "\n".join([
        f"# Updated by launch_training.py at {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "verbose=true",
        f"command={build_comm_command(args)}",
        "runAtGameStart=true",
        "",
    ])
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_text)

    return mod_list_path


def build_command(
    args: argparse.Namespace,
    sts_dir: Path,
    instance_name: str,
    workshop_root: Path,
) -> list[str] | str:
    if args.launch_mode == "steam":
        return args.steam_uri
    if args.launch_mode == "command":
        if not args.command:
            raise SystemExit("--launch-mode command requires --command.")
        formatted = args.command.format(
            sts_dir=str(sts_dir),
            instance=instance_name,
            session_id=args.session_id,
        )
        return formatted

    jar_path = resolve_workshop_modthespire_jar(workshop_root)
    if not jar_path.exists():
        raise SystemExit(f"ModTheSpire.jar not found: {jar_path}")
    command = [args.java, "-jar", str(jar_path)]
    if args.skip_launcher:
        command.append("--skip-launcher")
    if args.skip_intro:
        command.append("--skip-intro")
    return command


def launch_instance(
    args: argparse.Namespace,
    sts_dir: Path,
    workshop_root: Path,
    instance_index: int,
) -> subprocess.Popen | None:
    instance_name = f"instance-{instance_index}"
    session_dir = Path(args.data_dir) / args.session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["STS_AI_SESSION_REGISTRY"] = str((Path(args.data_dir).resolve() / "active_session.json"))
    env["STS_AI_SESSION_ID"] = args.session_id
    env["STS_AI_INSTANCE_ID"] = instance_name
    env["STS_AI_DATA_DIR"] = str(Path(args.data_dir).resolve())
    env["STS_AI_DATASET_PATH"] = str((session_dir / f"{instance_name}.jsonl").resolve())
    env["STS_AI_LOG_PATH"] = str((session_dir / f"{instance_name}.log").resolve())
    env["STS_AI_PLAYER_CLASS"] = args.player_class.upper()
    env["STS_AI_ASCENSION_LEVEL"] = str(args.ascension_level)
    if args.seed:
        env["STS_AI_SEED"] = args.seed
    env["STS_AI_AUTO_START"] = "false" if args.no_auto_start else "true"

    command = build_command(args, sts_dir, instance_name, workshop_root)
    if isinstance(command, str):
        printable = command
    else:
        printable = subprocess.list2cmdline(command)
    print(f"[launch] {instance_name}: {printable}")
    print(f"[output] dataset={env['STS_AI_DATASET_PATH']}")
    print(f"[output] log={env['STS_AI_LOG_PATH']}")

    if args.dry_run:
        return None

    if args.launch_mode == "steam":
        os.startfile(args.steam_uri)
        return None

    if isinstance(command, str):
        return subprocess.Popen(command, cwd=sts_dir, env=env, shell=True)
    return subprocess.Popen(command, cwd=sts_dir, env=env)


def main() -> None:
    args = parse_args()
    sts_dir = Path(args.sts_dir).expanduser().resolve()
    if not sts_dir.exists():
        raise SystemExit(f"STS directory does not exist: {sts_dir}")
    if args.instances < 1:
        raise SystemExit("--instances must be at least 1.")
    workshop_root = resolve_workshop_root(args, sts_dir)
    registry_path = prepare_session_registry(args)
    workshop_mods = validate_required_workshop_mods()
    mod_list_path = write_modthespire_local_config(args)
    workshop_mts_jar = resolve_workshop_modthespire_jar(workshop_root)

    print(f"[session] {args.session_id}")
    print(f"[sts_dir] {sts_dir}")
    print(f"[data_dir] {Path(args.data_dir).resolve()}")
    print(f"[registry] {registry_path}")
    print(f"[mods] {mod_list_path}")
    print(f"[workshop_root] {workshop_root}")
    print(f"[modthespire] {workshop_mts_jar}")
    print(f"[comm] {build_comm_command(args)}")
    for short_name, item in workshop_mods.items():
        print(f"[workshop] {short_name} -> {item['installPath']}")
    if args.launch_mode == "steam":
        print("[note] Steam mode may still show the ModTheSpire launcher UI. Use modthespire mode for unattended training.")

    launched = []
    for index in range(args.instances):
        proc = launch_instance(args, sts_dir, workshop_root, index)
        if proc is not None:
            launched.append(proc)
        if index != args.instances - 1 and args.startup_delay > 0:
            time.sleep(args.startup_delay)

    if not launched:
        if args.launch_mode == "steam" and not args.dry_run:
            print("[note] Steam mode delegates process management to Steam. Ctrl+C here will not stop the game.")
        return

    print(f"[done] launched {len(launched)} instance(s).")
    print("[note] Keep this terminal open if you want an easy place to stop them with Ctrl+C.")
    try:
        while True:
            time.sleep(1)
            active = [p for p in launched if p.poll() is None]
            if not active:
                break
    except KeyboardInterrupt:
        print("[stop] terminating launched processes...")
        for proc in launched:
            if proc.poll() is None:
                proc.terminate()


if __name__ == "__main__":
    main()
