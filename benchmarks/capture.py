"""Measure recording-only overhead; no live model or tool calls."""

import argparse
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path

from agent_flight_recorder import Recorder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--operations", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 100 <= args.operations <= 4500:
        parser.error("operations must be between 100 and 4500")
    samples = []
    with tempfile.TemporaryDirectory(prefix="afr-benchmark-") as directory:
        path = Path(directory) / "benchmark.jsonl"
        with Recorder(path) as recorder:
            with recorder.run("Synthetic capture benchmark"):
                for _ in range(args.operations):
                    before = time.perf_counter_ns()
                    with recorder.span("tool", "Synthetic operation", attributes={"provider": "synthetic", "model": "m" * 200, "tool_name": "t" * 200}):
                        pass
                    samples.append((time.perf_counter_ns() - before) / 1000)
        size = path.stat().st_size
        lines = len(path.read_bytes().splitlines())
        if recorder.health["failed_events"] or recorder.health["skipped_events"]:
            raise RuntimeError("Benchmark capture degraded")
    samples.sort()
    result = {
        "workload": "empty tool span; two synchronous flushed records per operation; metadata only",
        "python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
        "operations": args.operations, "events": lines,
        "microseconds_per_operation_p50": round(statistics.median(samples), 3),
        "microseconds_per_operation_p95": round(samples[int(len(samples) * .95) - 1], 3),
        "recording_bytes": size, "mean_bytes_per_event": round(size / lines, 1),
        "note": "Includes IDs, privacy filtering, context and two writes; excludes application work. Not a production latency guarantee.",
    }
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
