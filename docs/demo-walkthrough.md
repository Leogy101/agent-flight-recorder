# A 90 second incident walkthrough

Run `afr view` and open the synthetic failure example. All data is invented, and no payment, model call, or external action takes place.

1. **Read the summary.** The agent outcome is an error. Capture closure is a separate fact. Content was explicitly captured for this synthetic demonstration.
2. **Find the first failing tool call.** Select “Issue refund · attempt 1.” Its input uses the string `"42.00"` for `amount_cents`. The earlier policy retrieval says the field expects integer cents.
3. **Follow the retry.** “Prepare retry” is a model step. Its recorded output repeats the same argument. “Issue refund · attempt 2” has explicit retry linkage and again ends with an error.
4. **State the evidence carefully.** Two observed attempts used a string where the synthetic policy expected an integer. This explains the demonstration's validation failures; the viewer does not claim to read hidden reasoning or prove every possible cause.
5. **Use playback.** Step backward and forward to reveal recorded events. No model or tool is invoked. Moving the cursor does not reverse the historical action.
6. **Preview a reduced export.** Observe which content and labels will be removed. Downloading creates a new file; it leaves the original unchanged.

Now open the interrupted example. Two tools overlap. One has a result; the other has no recorded end. The agent and capture are also unfinished. The correct conclusion is that evidence is incomplete, not that the missing tool necessarily failed.

Finally, open the success example to compare its flow manually. Cross-run diffing and automated diagnosis are not part of this release.

For a real SDK example without real services, run `python examples/record_agent.py --output recordings/example.jsonl`, then open that file. The synthetic credential field is filtered before writing.
