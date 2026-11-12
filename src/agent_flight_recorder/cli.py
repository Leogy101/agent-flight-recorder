"""Small local commands: demo, view, validate, and file-only OTLP conversion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import webbrowser

from .recording import load_recording, write_recording
from ._json_preflight import preflight_json
from .otlp import convert_otlp
from .server import make_server


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("Non-finite JSON value")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="afr", description="Inspect agent recordings offline. Playback never executes tools.")
    parser.add_argument("--version", action="version", version="Agent Flight Recorder 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)
    view = sub.add_parser("view", help="Serve the bundled viewer on loopback")
    view.add_argument("--port", type=int, default=0, help="Port; 0 chooses an available port")
    view.add_argument("--no-open", action="store_true", help="Print URL without opening a browser")
    demo = sub.add_parser("demo", help="Write three clearly labeled synthetic recordings")
    demo.add_argument("--output", type=Path, default=Path("recordings"))
    validate = sub.add_parser("validate", help="Validate a local JSONL recording")
    validate.add_argument("recording", type=Path)
    validate.add_argument("--allow-partial", action="store_true")
    convert = sub.add_parser("import-otlp", help="Convert a documented OTLP JSON file; no collector")
    convert.add_argument("source", type=Path)
    convert.add_argument("--output", type=Path, required=True)
    convert.add_argument("--trace-id", default=None)
    convert.add_argument("--capture-content", action="store_true", help="Opt in to filtered source content; review before sharing")
    args = parser.parse_args(argv)
    try:
        if args.command == "view":
            if not 0 <= args.port <= 65535:
                raise ValueError("Port must be between 0 and 65535")
            server = make_server(args.port)
            url = f"http://127.0.0.1:{server.server_address[1]}/"
            print(f"Agent Flight Recorder: {url}\nOpen a recording in the browser. Files stay in browser memory.\nPress Ctrl+C to stop.", flush=True)
            if not args.no_open:
                webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        if args.command == "demo":
            from .demo import demo_events
            args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
            targets = [(args.output / f"demo-{name}.jsonl", demo_events(name)) for name in ("failure", "interrupted", "success")]
            if any(path.exists() for path, _ in targets):
                raise ValueError("Demo output exists; choose a new output directory")
            for path, events in targets:
                write_recording(events, path)
                print(f"Wrote synthetic recording: {path}")
            return 0
        if args.command == "validate":
            result = load_recording(args.recording, allow_partial=args.allow_partial)
            print(f"{len(result['events'])} events; {len(result['warnings'])} evidence warnings")
            for warning in result["warnings"]:
                line = f" (line {warning['line']})" if warning.get("line") else ""
                print(f"- {warning['code']}{line}: {warning['message']}")
            return 1 if result["warnings"] else 0
        if args.command == "import-otlp":
            with args.source.open("rb") as handle:
                raw = handle.read(25 * 1024 * 1024 + 1)
            if len(raw) > 25 * 1024 * 1024:
                raise ValueError("OTLP input exceeds 25 MiB")
            text = preflight_json(raw)
            source = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_constant)
            events = convert_otlp(source, trace_id=args.trace_id, capture_content=args.capture_content)
            write_recording(events, args.output)
            print(f"Converted {len(events)} events. Coverage: imported completed spans. Output: {args.output}")
            return 0
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        # Parser and filesystem messages may include supplied content or sensitive paths.
        if isinstance(error, json.JSONDecodeError):
            print("Error: invalid JSON input", file=sys.stderr)
        elif isinstance(error, OSError):
            print("Error: unable to access file or bind local viewer; check path, permissions, and port", file=sys.stderr)
        elif isinstance(error, RecursionError):
            print("Error: input nesting exceeds supported limits", file=sys.stderr)
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
