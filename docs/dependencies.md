# Dependencies and supported environments

## Runtime

- Python 3.11–3.14 is the intended supported range for this alpha. Package metadata permits Python >=3.11; that is not a claim that future versions have been tested.
- The recorder, reader, converter, command line, and static server use only the Python standard library. There are **zero third-party Python runtime dependencies**.
- The installed package includes its browser bundle. Node, npm, a database, OpenTelemetry SDKs, provider SDKs, and API keys are not needed to record or view files.
- React, React DOM, their transitive Scheduler code, and Vite's module-preload helper are bundled in the viewer with MIT notices. The project itself uses MIT. Build/test packages are not shipped as installed dependencies. There are no CDN assets, analytics, remote fonts, or background services.

## Development and builds

`pyproject.toml` declares setuptools >=77 and wheel as build tools. The `dev` extra contains pytest >=8,<10, build >=1,<2, and jsonschema >=4,<5. Those are development tools, not dependencies installed with the application. They are bounded ranges rather than a reproducible Python environment lock.

Use Node 24 for frontend development, matching GitHub Actions. Phase 2 used Node 26.10.0; the alpha qualification uses Node 24.22.3 in a clean checkout, matching the CI major version. `viewer/package-lock.json` pins the resolved npm dependency tree; use `npm ci`, not an unreviewed lockfile update. `viewer/package.json` lists React, TypeScript, Vite, Vitest, Testing Library, jsdom, and Playwright. Playwright downloads a browser for acceptance tests; it is not shipped in the wheel.

GitHub Actions tests Python 3.11 and 3.14 on macOS and Linux and the viewer on Linux/Node 24. Action revisions are pinned to full commit IDs, jobs have time limits, and workflow permissions are read-only. Remote CI has not run because the repository has not been published. See [validation](validation.md) for the environments actually exercised locally. Windows and non-Chromium browsers are not verified support claims.

## Dependency risk checks

On November 12, 2026, the full npm audit (including development packages) reported no known vulnerabilities. A Python environment audit initially identified the installer pip 26.1.2 as affected by [GHSA-qwm4-qh6w-59xr](https://github.com/advisories/GHSA-qwm4-qh6w-59xr). The advisory concerns package installation from a malicious index, not recorder execution. The project environment was upgraded to pip 26.3 and audited again with no known vulnerabilities reported among auditable packages. The unpublished local project itself has no advisory-database entry and is reviewed through source and tests.

Quickstart and CI upgrade pip to >=26.2 before installation. No machine-wide Python installation was changed. A clean wheel install can use `--no-index --no-deps` because the application has no Python dependencies. Build tools still require an initial download unless already cached.

Recheck before publishing or updating dependencies:

```sh
python -m pip check
cd viewer
npm audit
cd ..
# Optional audit tool, run in an isolated environment; not an application dependency.
uvx pip-audit --path .venv/lib/python3.14/site-packages
```

Adjust the last path to the environment's actual Python version. Advisory scans cannot prove the absence of vulnerabilities. Review dependency changes, source provenance, build output, and relevant regression tests as well.

## Release versions and reproducibility

GitHub tag `v0.1.0-alpha.1` and npm/display version `0.1.0-alpha.1` map to Python prerelease `0.1.0a1`. A small shared Python version module and a frontend package-version import prevent newly generated capture/export provenance from drifting. The event/transform schema stays at `0.1`, and historical fixture version labels are not rewritten.

The npm tree and GitHub Action revisions are pinned. Python development/build requirements use declared ranges; the project does not claim bit-identical rebuilds across arbitrary toolchain versions. Release preparation records actual tool versions, checks the built package contents, and supplies SHA-256 hashes for the specific reviewed bytes. No OpenClaw package or agent framework is required.
