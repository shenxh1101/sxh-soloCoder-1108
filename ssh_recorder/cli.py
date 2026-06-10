import argparse
import os
import sys
import time
import signal
from datetime import datetime
from typing import Optional


def cmd_record(args) -> int:
    from .config import ServerConfig, ConfigLoader
    from .recorder import SSHRecorder

    if args.config and args.name:
        server = ConfigLoader.get_server(args.config, args.name)
        if server is None:
            print(f"Error: Server '{args.name}' not found in config file", file=sys.stderr)
            return 1
    elif args.host and args.user:
        server = ServerConfig(
            name=args.name or f"{args.user}@{args.host}",
            host=args.host,
            user=args.user,
            port=args.port,
            password=args.password,
            key_file=args.key_file,
        )
    else:
        print("Error: Must provide either --config/--name or --host/--user", file=sys.stderr)
        return 1

    recorder = SSHRecorder(server, log_dir=args.log_dir)

    def signal_handler(signum, frame):
        print("\n\nStopping recording...", file=sys.stderr)
        try:
            recorder.add_bookmark("session_interrupted", "Session ended by signal")
        except Exception:
            pass

    signal.signal(signal.SIGINT, signal_handler)

    try:
        return recorder.run()
    except KeyboardInterrupt:
        return 0


def _format_bookmark_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _print_bookmarks(bookmarks) -> None:
    print("Bookmarks:")
    prev_offset = 0.0
    for i, bm in enumerate(bookmarks, 1):
        time_str = _format_bookmark_time(bm["time_offset"])
        rel = bm["time_offset"] - prev_offset
        rel_str = _format_bookmark_time(rel)
        after_tag = " [末尾后]" if bm.get("is_after_end") else ""
        desc_part = f" — {bm['description']}" if bm.get("description") else ""
        print(f"  {i}. {bm['name']} @ {time_str} (+{rel_str}){after_tag}{desc_part}")
        prev_offset = bm["time_offset"]


def cmd_play(args) -> int:
    from .player import PlaybackController, InteractivePlayer

    if not os.path.exists(args.log_file):
        print(f"Error: Log file not found: {args.log_file}", file=sys.stderr)
        return 1

    controller = PlaybackController(
        log_file=args.log_file,
        speed=args.speed,
        show_input=args.show_input,
    )

    if args.list_bookmarks:
        bookmarks = controller.list_bookmarks()
        if not bookmarks:
            print("No bookmarks found in this session.")
        else:
            _print_bookmarks(bookmarks)
        return 0

    if args.snapshot:
        if not controller.snapshot(args.snapshot):
            print(f"Error: Bookmark '{args.snapshot}' not found", file=sys.stderr)
            return 1
        return 0

    if args.jump_bookmark:
        if not controller.jump_to_bookmark(args.jump_bookmark):
            print(f"Error: Bookmark '{args.jump_bookmark}' not found", file=sys.stderr)
            return 1

    player = InteractivePlayer(controller)
    player.run()
    return 0


def cmd_clean(args) -> int:
    from .cleaner import LogCleaner

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    output = args.output
    if not output:
        base, ext = os.path.splitext(args.input)
        output = f"{base}-clean.txt"

    LogCleaner.clean_log_file(
        input_file=args.input,
        output_file=output,
        include_input=args.include_input,
        remove_ansi=not args.keep_ansi,
        apply_backspace=not args.keep_backspace,
        remove_control=not args.keep_control,
    )
    print(f"Cleaned log saved to: {output}")
    return 0


def cmd_export(args) -> int:
    from .exporter import HTMLExporter

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    output = args.output
    if not output:
        base, _ = os.path.splitext(args.input)
        output = f"{base}.html"

    HTMLExporter.export(
        log_file=args.input,
        output_file=output,
        title=args.title,
    )
    print(f"HTML export saved to: {output}")
    return 0


def cmd_search(args) -> int:
    from .searcher import LogSearcher

    if not os.path.exists(args.path):
        print(f"Error: Path not found: {args.path}", file=sys.stderr)
        return 1

    results = LogSearcher.search(
        path=args.path,
        query=args.query,
        case_sensitive=args.case_sensitive,
        regex=args.regex,
        context_lines=args.context,
        recursive=not args.no_recursive,
        max_results=args.max_results,
    )

    if not results:
        print("No matches found.")
        return 0

    output = LogSearcher.format_results(
        results,
        with_context=not args.no_context,
        colored=not args.no_color,
    )
    print(output)
    return 0


def cmd_list(args) -> int:
    from .storage import SessionReader

    log_dir = args.log_dir
    if not os.path.exists(log_dir):
        print(f"Error: Log directory not found: {log_dir}", file=sys.stderr)
        return 1

    logs = SessionReader.find_logs(log_dir)
    if not logs:
        print("No recorded sessions found.")
        return 0

    print(f"Found {len(logs)} session(s):")
    print()
    for i, log_file in enumerate(logs, 1):
        reader = SessionReader(log_file)
        host = reader.metadata.host if reader.metadata else "unknown"
        user = reader.metadata.user if reader.metadata else "unknown"
        started = ""
        if reader.metadata and reader.metadata.started_at:
            started = datetime.fromtimestamp(reader.metadata.started_at).strftime("%Y-%m-%d %H:%M:%S")
        size = os.path.getsize(log_file)
        size_str = f"{size // 1024}KB" if size < 1024 * 1024 else f"{size // 1024 // 1024}MB"
        print(f"  {i:3d}. [{started}] {user}@{host}")
        print(f"       File: {log_file} ({size_str})")
        if reader.metadata and reader.metadata.bookmarks:
            print(f"       Bookmarks: {len(reader.metadata.bookmarks)}")
        print()
    return 0


def cmd_list_bookmarks(args) -> int:
    from .player import PlaybackController

    if not os.path.exists(args.log_file):
        print(f"Error: Log file not found: {args.log_file}", file=sys.stderr)
        return 1

    controller = PlaybackController(log_file=args.log_file)
    bookmarks = controller.list_bookmarks()
    if not bookmarks:
        print("No bookmarks found in this session.")
        return 0

    _print_bookmarks(bookmarks)
    return 0


def cmd_multi_record(args) -> int:
    from .config import ConfigLoader
    from .concurrent import ConcurrentSessionManager

    if not args.config:
        print("Error: --config is required for multi-session recording", file=sys.stderr)
        return 1

    servers = ConfigLoader.load_servers(args.config)
    if not servers:
        print("Error: No servers found in config file", file=sys.stderr)
        return 1

    server_names = args.servers or list(servers.keys())
    selected_servers = []
    for name in server_names:
        if name not in servers:
            print(f"Warning: Server '{name}' not found in config, skipping", file=sys.stderr)
            continue
        selected_servers.append(servers[name])

    if not selected_servers:
        print("Error: No valid servers selected", file=sys.stderr)
        return 1

    manager = ConcurrentSessionManager(log_dir=args.log_dir)

    print(f"Starting {len(selected_servers)} concurrent session(s)...")
    for server in selected_servers:
        try:
            sid = manager.start_session(server)
            print(f"  Started: {sid} -> {server.user}@{server.host}")
        except Exception as e:
            print(f"  Failed to start {server.user}@{server.host}: {e}", file=sys.stderr)

    status_file = os.path.join(args.log_dir, "concurrent_status.json")
    print(f"\nStatus file: {status_file}")
    print("Press Ctrl+C to stop all sessions...\n")

    def shutdown_handler(signum, frame):
        print("\n\nShutting down all sessions...")
        manager.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)

    try:
        while True:
            manager.cleanup_finished()
            manager.save_status(status_file)
            sessions = manager.list_sessions()
            alive = sum(1 for s in sessions if s["is_alive"])
            if alive == 0:
                print("All sessions have ended.")
                break
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Active sessions: {alive}/{len(sessions)}", end="\r")
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop_all()
        manager.save_status(status_file)
        print("\nAll sessions stopped.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ssh-recorder",
        description="SSH Session Recorder & Player - Record, replay, and share SSH sessions",
    )
    parser.add_argument("--version", action="version", version="ssh-recorder 1.0.0")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    # Record
    rec_parser = subparsers.add_parser("record", help="Record an SSH session")
    rec_group = rec_parser.add_mutually_exclusive_group(required=False)
    rec_group.add_argument("--config", help="Path to YAML config file with server definitions")
    rec_parser.add_argument("--name", help="Server name in config file, or session name")
    rec_parser.add_argument("--host", help="SSH server hostname")
    rec_parser.add_argument("--user", help="SSH username")
    rec_parser.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
    rec_parser.add_argument("--password", help="SSH password (not recommended, use key files)")
    rec_parser.add_argument("--key-file", help="Path to private key file")
    rec_parser.add_argument("--log-dir", default="logs", help="Directory for log files (default: logs)")
    rec_parser.set_defaults(func=cmd_record)

    # Multi record
    multi_parser = subparsers.add_parser("multi-record", help="Record multiple SSH sessions concurrently")
    multi_parser.add_argument("--config", required=True, help="Path to YAML config file")
    multi_parser.add_argument("--servers", nargs="*", help="Specific server names to record (default: all)")
    multi_parser.add_argument("--log-dir", default="logs", help="Directory for log files (default: logs)")
    multi_parser.set_defaults(func=cmd_multi_record)

    # Play
    play_parser = subparsers.add_parser("play", help="Play back a recorded session")
    play_parser.add_argument("log_file", help="Path to session log file")
    play_parser.add_argument("--speed", type=float, default=1.0, help="Playback speed (default: 1.0)")
    play_parser.add_argument("--show-input", action="store_true", help="Show user input during playback")
    play_parser.add_argument("--list-bookmarks", action="store_true", help="List all bookmarks and exit")
    play_parser.add_argument("--jump-bookmark", help="Jump to a specific bookmark by name")
    play_parser.add_argument("--snapshot", metavar="BOOKMARK", help="Non-interactive: output terminal state at bookmark and exit")
    play_parser.set_defaults(func=cmd_play)

    # Clean
    clean_parser = subparsers.add_parser("clean", help="Generate a cleaned, readable version of the log")
    clean_parser.add_argument("input", help="Input session log file")
    clean_parser.add_argument("-o", "--output", help="Output file path (default: <input>-clean.txt)")
    clean_parser.add_argument("--include-input", action="store_true", help="Include user input in cleaned output")
    clean_parser.add_argument("--keep-ansi", action="store_true", help="Keep ANSI color codes")
    clean_parser.add_argument("--keep-backspace", action="store_true", help="Do not process backspace characters")
    clean_parser.add_argument("--keep-control", action="store_true", help="Keep other control characters")
    clean_parser.set_defaults(func=cmd_clean)

    # Export
    exp_parser = subparsers.add_parser("export", help="Export session to interactive HTML page")
    exp_parser.add_argument("input", help="Input session log file")
    exp_parser.add_argument("-o", "--output", help="Output HTML file (default: <input>.html)")
    exp_parser.add_argument("--title", help="Custom title for the HTML page")
    exp_parser.set_defaults(func=cmd_export)

    # Search
    search_parser = subparsers.add_parser("search", help="Search through recorded sessions")
    search_parser.add_argument("path", help="Log file or directory to search")
    search_parser.add_argument("--query", "-q", required=True, help="Search query")
    search_parser.add_argument("--case-sensitive", action="store_true", help="Case-sensitive search")
    search_parser.add_argument("--regex", action="store_true", help="Treat query as regular expression")
    search_parser.add_argument("--context", type=int, default=2, help="Lines of context around matches (default: 2)")
    search_parser.add_argument("--no-recursive", action="store_true", help="Do not search subdirectories")
    search_parser.add_argument("--no-context", action="store_true", help="Show only matching lines")
    search_parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    search_parser.add_argument("--max-results", type=int, default=100, help="Max results per file (default: 100)")
    search_parser.set_defaults(func=cmd_search)

    # List
    list_parser = subparsers.add_parser("list", help="List all recorded sessions")
    list_parser.add_argument("--log-dir", default="logs", help="Log directory to scan (default: logs)")
    list_parser.set_defaults(func=cmd_list)

    # List-bookmarks
    lbm_parser = subparsers.add_parser("list-bookmarks", help="List bookmarks in a session log")
    lbm_parser.add_argument("log_file", help="Path to session log file")
    lbm_parser.set_defaults(func=cmd_list_bookmarks)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
