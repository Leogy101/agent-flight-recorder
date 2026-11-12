"""Execute a local agent workflow with a deterministic model stand-in.

No LLM, credentials, network request, or prerecorded trace is involved. The
stand-in makes one argument error, responds to validation feedback, and uses a
real read-only tool. Every recording comes from executing that code.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

from agent_flight_recorder import Recorder
from agent_flight_recorder.recording import load_recording


ORDER_DATA = Path(__file__).resolve().parent / "data" / "synthetic_orders.json"
SYNTHETIC_CREDENTIAL = "EXAMPLE-ONLY-FAKE-CREDENTIAL"
SYNTHETIC_EMAIL = "synthetic.customer@example.invalid"
_ORDER_ID = re.compile(r"SYN-[0-9]{4}\Z")
_MAX_ATTEMPTS = 2


class WorkflowError(Exception):
    """An expected application error, separate from recorder health."""


class InvalidToolArguments(WorkflowError):
    pass


class OrderNotFound(WorkflowError):
    pass


class SimulatedProvider:
    """A rule-based stand-in, deliberately not an actual language model.

    Initial argument generation drops the SYN prefix and returns an integer.
    Validation feedback causes it to reuse the requested string identifier.
    No token counts are invented for these ordinary Python function calls.
    """

    def choose_action(self, request: dict, feedback: dict | None) -> dict:
        order_id = request["order_id"] if feedback else int(request["order_id"].removeprefix("SYN-"))
        return {"tool": "lookup_order", "arguments": {"order_id": order_id}}

    def compose_answer(self, order: dict) -> str:
        return f"Synthetic order {order['order_id']} is {order['status']}."


def lookup_order(arguments: dict, *, data_path: Path = ORDER_DATA) -> dict:
    """Validate arguments and read the local synthetic order catalog once."""
    if type(arguments) is not dict or set(arguments) != {"order_id"}:
        raise InvalidToolArguments("lookup_order requires exactly one order_id argument")
    order_id = arguments["order_id"]
    if type(order_id) is not str or not _ORDER_ID.fullmatch(order_id):
        raise InvalidToolArguments("order_id must be a string in the SYN-0000 format")
    with Path(data_path).open(encoding="utf-8") as source:
        catalog = json.load(source)
    for order in catalog["orders"]:
        if order["order_id"] == order_id:
            return dict(order)
    # The caller gets the original exception; recording and CLI omit its text.
    raise OrderNotFound(f"No local synthetic order matches {order_id}")


def _execute_workflow(request: dict, recorder: Recorder, data_path: Path) -> dict:
    provider = SimulatedProvider()
    feedback = None
    previous_attempt_id = None
    with recorder.run("Synthetic order support agent", input=request) as run:
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            with recorder.span(
                "model", "Simulated provider: choose action",
                input={"request": request, "validation_feedback": feedback},
                attributes={"provider": "local-simulation", "model": "deterministic-stand-in-v1"},
            ) as model_call:
                action = provider.choose_action(request, feedback)
                model_call.set_output(action)

            attributes = {"tool_name": "lookup_order", "attempt": attempt}
            links = []
            if previous_attempt_id:
                attributes["retry_of"] = previous_attempt_id
                links.append({"span_id": previous_attempt_id, "relation": "retry_of"})
            tool_call = recorder.span(
                "tool", "lookup_order", input=action["arguments"],
                attributes=attributes, links=links,
            )
            try:
                with tool_call:
                    if action["tool"] != "lookup_order":
                        raise InvalidToolArguments("The requested tool is unavailable")
                    order = lookup_order(action["arguments"], data_path=data_path)
                    tool_call.set_output(order)
            except InvalidToolArguments:
                # Catch outside the span so its actual failure is observed. Feed
                # a coarse code back to the stand-in, never the exception text.
                if attempt == _MAX_ATTEMPTS:
                    raise
                feedback = {"code": "invalid_tool_arguments", "expected_format": "SYN-0000"}
                previous_attempt_id = tool_call.span_id
                recorder.event("Retry after argument validation", payload={"next_attempt": attempt + 1, "reason": feedback["code"]})
                continue

            with recorder.span(
                "model", "Simulated provider: compose answer", input=order,
                attributes={"provider": "local-simulation", "model": "deterministic-stand-in-v1"},
            ) as model_call:
                answer = provider.compose_answer(order)
                model_call.set_output(answer)
            result = {"order_id": order["order_id"], "status": order["status"], "answer": answer, "tool_attempts": attempt}
            run.set_output(result)
            return result
    raise WorkflowError("The synthetic workflow produced no result")


def run_scenario(scenario: str, output: str | Path, *, capture_content: bool = False, data_path: Path = ORDER_DATA) -> dict:
    """Execute success or failure and record its actual runtime boundaries.

    Success returns an answer based on the local catalog. Failure raises the
    original OrderNotFound after one argument-correction retry. Both leave a
    recording when capture is healthy. Existing output is never overwritten.
    """
    if scenario not in {"success", "failure"}:
        raise ValueError("scenario must be success or failure")
    request = {
        "order_id": "SYN-1001" if scenario == "success" else "SYN-4040",
        "customer_email": SYNTHETIC_EMAIL,
        "api_key": SYNTHETIC_CREDENTIAL,
    }
    with Recorder(
        output, capture_content=capture_content,
        redact_keys=("customer_email", "internal_note"),
        redact_patterns=(SYNTHETIC_CREDENTIAL, SYNTHETIC_EMAIL),
    ) as recorder:
        return _execute_workflow(request, recorder, Path(data_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute a synthetic support agent locally and record its real calls. No LLM or network access.")
    parser.add_argument("--scenario", choices=("success", "failure", "both"), help="Default: both; legacy --output defaults to success")
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--output-dir", type=Path, help="New directory to create; omitted means a private temporary directory")
    destination.add_argument("--output", type=Path, help="Legacy single-recording path; writes success unless --scenario is specified")
    parser.add_argument("--capture-content", action="store_true", help="Opt in to filtered synthetic inputs/outputs; default is metadata only")
    args = parser.parse_args(argv)
    scenario_choice = args.scenario or ("success" if args.output is not None else "both")
    if args.output is not None and scenario_choice == "both":
        print("--output writes one scenario; select success or failure, or use --output-dir for both.")
        return 2
    try:
        if args.output is not None:
            if args.output.exists() or args.output.is_symlink():
                print("Recording destination exists. Choose a new output file.")
                return 2
            directory = args.output.parent
        elif args.output_dir is None:
            directory = Path(tempfile.mkdtemp(prefix="afr-agent-example-"))
        else:
            directory = args.output_dir
            directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    except OSError:
        print("Unable to create a new recording directory. Choose a new writable location.")
        return 2

    scenarios = ("success", "failure") if scenario_choice == "both" else (scenario_choice,)
    print("Executing local synthetic scenarios with a deterministic provider stand-in; no LLM or network calls.")
    print("Content mode: filtered opt-in" if args.capture_content else "Content mode: metadata only")
    for scenario in scenarios:
        target = args.output if args.output is not None else directory / f"{scenario}.jsonl"
        try:
            result = run_scenario(scenario, target, capture_content=args.capture_content)
        except OrderNotFound:
            if scenario != "failure":
                print("Unexpected workflow failure; inspect the recording. Exception text is omitted.")
                return 1
            print("failure: expected OrderNotFound after argument correction; the agent failed, not the example command.")
        except Exception:
            print("Unable to complete the example; inspect any recording and check the local setup. Exception text is omitted.")
            return 1
        else:
            if scenario == "failure":
                print("The expected failure did not occur; check the synthetic data.")
                return 1
            print(f"success: {result['answer']} Tool attempts: {result['tool_attempts']}.")
        try:
            captured = load_recording(target)
            if captured["warnings"]:
                print("The agent ran, but recording evidence is incomplete. Inspect capture health before using this example.")
                return 1
        except (OSError, ValueError):
            print("The agent ran, but its recording is unavailable or invalid. Check the recording destination.")
            return 1
        print(f"Recording: {target}")
    print("Inspect with afr view, then select a recording. Playback reads saved events; it does not rerun the workflow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
