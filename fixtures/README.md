# Reviewed synthetic recordings

Every committed recording contains synthetic data. Do not add actual customer traces here: this directory is an explicit exception to the repository's JSONL ignore rule.

| File | Provenance and purpose |
| --- | --- |
| `agent-example-success.jsonl` | Captured by executing `examples/record_agent.py` with filtered content enabled: invalid argument, corrected lookup, successful answer. |
| `agent-example-failure.jsonl` | Same executing code: invalid argument, corrected identifier, actual local `OrderNotFound`, failed root. |
| `demo-success.jsonl`, `demo-failure.jsonl`, `demo-interrupted.jsonl` | Hand-authored, deterministic illustrations from `demo.py`, also bundled in the viewer. They are not real execution captures. |
| `typescript-example.jsonl` | Independently produced by `viewer/scripts/produce-fixture.ts`, exercising a second-language producer. |
| `otlp-example.json` | Small synthetic OTLP export for the documented conversion subset. |

The two agent examples were generated on November 12, 2026 from the actual Python workflow. UUIDs, clocks, and durations are recorded at execution time; application outcomes are deterministic, file bytes are not. The simulated provider is identified in every model span. Token usage is absent because no language model runs.

The catalog, requests, and fake credential markers are all synthetic. Generated selected-content samples were checked for omitted credentials, email values, and internal notes before inclusion. Argument values intentionally remain visible for debugging. A fresh default run omits all input/output payloads instead:

```sh
python examples/record_agent.py
python examples/record_agent.py --output-dir recordings/new-selected-example --capture-content
```

The second command needs a new directory. Never regenerate over an existing capture or normalize its measured times to pretend execution was deterministic.
