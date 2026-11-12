# Contributing

Install Python 3.11+ and a current Node version compatible with the pinned Vite release. Create a virtual environment, then run `python -m pip install -e '.[dev]'`. In `viewer`, use `npm ci`.

Run `python -m pytest`, `npm test` in `viewer`, and `npm run build` before proposing a change. Run `python -m build` and check the resulting wheel when package assets change. See `docs/validation.md` for browser and benchmark commands.

Keep the Python recorder dependency-free at runtime. Changes to the event model require matching contract, JSON Schema, Python validation, browser validation, and conformance fixtures. Do not weaken a warning to make a test pass; explain evidence uncertainty explicitly.

Never submit real prompts, credentials, customer records, or recordings. Add synthetic fixtures that isolate a meaningful behavior. A bug report should describe expected and observed behavior, environment, steps, and a reviewed reduced recording if appropriate.

The project is standalone. Do not add dependencies on other personal projects or copy their code without explicit authorization. No execution replay, cloud collection, or automatic model/tool invocation belongs in the current MVP.
