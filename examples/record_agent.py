"""A synthetic agent recorded through the real SDK. No external services needed."""

import argparse
from pathlib import Path

from agent_flight_recorder import Recorder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("recordings/example.jsonl"))
    args = parser.parse_args()
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with Recorder(args.output, capture_content=True) as recorder:
        with recorder.run("Synthetic support workflow"):
            with recorder.span("model", "Choose an action", attributes={"provider": "synthetic", "model": "scripted"}) as call:
                # A stand-in for your own provider call. The recorder does not call it.
                decision = {"tool": "lookup_order", "order_id": "DEMO-42"}
                call.set_output(decision)
                call.set_usage(input_tokens=80, output_tokens=12)
            with recorder.span("tool", "Look up order", input=decision) as tool:
                result = {"status": "shipped", "api_key": "FAKE-DEMO-SECRET"}
                tool.set_output(result)
    print(f"Synthetic capture saved to {args.output}. Open it with afr view.")


if __name__ == "__main__":
    main()
