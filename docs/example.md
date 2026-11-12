# Execute and inspect a local agent workflow

This example runs a Python control loop, calls a read-only local tool, handles a
validation error, and records those runtime boundaries through `Recorder`. It
does not assemble trace events by hand. Its provider is a clearly labeled
deterministic stand-in, not an LLM. No paid account, network, credentials, provider
SDK, or agent framework is required.

From the repository root, after installing the package:

```sh
python examples/record_agent.py
```

The command creates a private temporary directory and prints paths to
`success.jsonl` and `failure.jsonl`. Runtime IDs, timestamps, and durations vary;
the application outcomes are reproducible. Both outcomes are intentional, so a
successfully demonstrated failure scenario does not make the command fail.
Temporary recordings remain available for inspection; they are not automatically
deleted. The command checks recording health separately from the agent outcome.

To choose a destination and inspect filtered payloads:

```sh
python examples/record_agent.py --output-dir recordings/executed-example --capture-content
afr view
```

The destination directory must not exist. Select either recording using the
viewer file picker. Run only one case with `--scenario success` or
`--scenario failure`. Repeating the default command creates another temporary
directory; repeating an explicit destination refuses to overwrite it.

The previous `--output recordings/example.jsonl` invocation remains supported:
it executes the success case when no scenario is specified and writes exactly one
new recording. It can be combined with `--scenario failure`, but not `both` or
`--output-dir`. Content capture is now explicitly opt-in for this example.

## What actually executes

1. The support agent receives a synthetic order request. A model span wraps a
   call to `SimulatedProvider.choose_action`.
2. The stand-in deliberately returns the order identifier as an integer. The
   actual `lookup_order` function rejects it with `InvalidToolArguments` before
   reading the catalog.
3. The agent catches that specific exception outside the tool span and supplies
   a coarse validation code to the provider. It permits one correction retry.
4. The provider responds to that feedback with the original string identifier.
   A second tool call validates it, opens
   `examples/data/synthetic_orders.json`, and searches the records.
5. In the success case, `SYN-1001` exists. The stand-in composes an answer from the
   returned status, and the agent returns after two tool attempts. In the failure
   case, `SYN-4040` is absent. The actual `OrderNotFound` propagates through the
   root span. It is not converted into a successful answer.

The retry records both an attempt number and an explicit link to the failed tool
span. The observed validation exception triggers the correction. The agent does
not retry a missing order. Changing the catalog status changes the successful
answer; the result is not a prerecorded response. The tool does not modify the
catalog.

All model labels say “Simulated provider”; metadata identifies
`local-simulation` / `deterministic-stand-in-v1`. These are ordinary Python calls,
so the example records no invented model usage. Very short durations and absent
token counts are expected. There are no sleeps to manufacture latency.

## Inspect the evidence

- Open `success.jsonl`, search `lookup_order`, and inspect attempts 1 and 2. The
  first ends with `InvalidToolArguments`; the second succeeds. Follow its
  `retry_of` link. The root agent succeeds despite a handled tool error.
- Open `failure.jsonl`. The first attempt fails validation; the corrected second
  attempt ends with `OrderNotFound`, and the root ends in error. Capture still
  finishes normally: agent outcome and recording health differ.
- With `--capture-content`, compare the integer argument on attempt 1 with the
  corrected string on attempt 2. Inspect the model decision and actual tool
  result. Default metadata capture explicitly marks those values as omitted.
- Step backward and forward through recorded playback. This traverses saved
  observations. It does not call the provider, read the catalog again, repair the
  failure, or reconstruct hidden state. Run the command again for a fresh
  execution and a new recording.

The root is named `Synthetic order support agent`. Model spans are
`Simulated provider: choose action` and, on success,
`Simulated provider: compose answer`. The viewer can show the observed argument
correction and missing-order failure; that evidence does not establish the
quality of a real language model or behavior of a remote provider.

## Privacy and application behavior

Both requests and catalog records are entirely synthetic. Metadata-only capture
is the default. Filtered content capture is explicit; credentials, customer email
fields, and internal notes are redacted before writing. Literal fake credential
and email patterns provide an additional example of redaction rules. Static
operation labels are developer-chosen. Redaction remains no general guarantee
that arbitrary future data is safe to publish.

Exception messages are neither sent back to the provider nor printed by this
example's command. Recordings retain error categories through the SDK. The Python
entry point preserves the original application exception for the caller:

```python
from pathlib import Path
from examples.record_agent import OrderNotFound, run_scenario

result = run_scenario("success", Path("recordings/new-success.jsonl"))
assert result["status"] == "shipped"

try:
    run_scenario("failure", Path("recordings/new-failure.jsonl"))
except OrderNotFound:
    pass  # The failed application run was recorded; it was not made successful.
```

Use new paths for each call. The example lives in the repository and is not
installed as a provider integration by the package. Its tests execute the tool,
check its calls and returned data, preserve exception identity, validate the
recordings, verify retry ordering, and check both privacy modes.
