# Contributing

Use Python 3.11–3.14 and Node 24 (the CI frontend version). Create a virtual environment, then run `python -m pip install -e '.[dev]'`. In `viewer`, use `npm ci`.

Run `python -m pytest`, `npm test` in `viewer`, and `npm run build` before proposing a change. Run `python -m build` and check the resulting wheel when package assets change. See `docs/validation.md` for browser and benchmark commands.

Keep the Python recorder dependency-free at runtime. Changes to the event model require matching contract, JSON Schema, Python validation, browser validation, and conformance fixtures. Do not weaken a warning to make a test pass; explain evidence uncertainty explicitly.

Never submit real prompts, credentials, customer records, or recordings. Add synthetic fixtures that isolate a meaningful behavior. A bug report should describe expected and observed behavior, environment, steps, and a reviewed reduced recording if appropriate.

The project is standalone. Do not add dependencies on other personal projects or copy their code without explicit authorization. The recorder and viewer must not invoke recorded tools or models. Executable examples may call their own explicitly documented simulated provider and local tools. No execution replay or cloud collection belongs in this release.

See [dependency/support policy](docs/dependencies.md) and [the engineering review](docs/engineering-review.md). Before sending a patch, run `git diff --check` and review generated fixtures and screenshots for private data. Never edit a built viewer without updating its source and rebuilding it.
