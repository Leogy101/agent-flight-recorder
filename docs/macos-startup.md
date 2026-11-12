# macOS viewer startup investigation

The release qualification exposed a real startup dependency: constructing the
loopback HTTP server performed a synchronous hostname lookup before the CLI could
announce its URL. That lookup stalled on GitHub's macOS runners. The confirmed
application-level cause is the unnecessary resolver call; the underlying reason
the runner's resolver stalled remains unknown.

The corrective change removes that lookup from this server's construction.
The diagnostic results below establish the failure, not a passing release.
Final qualification requires successful macOS/Linux CI and fresh public-source
installation of the release commit. Those outcomes belong in the
[release record](https://github.com/Leogy101/agent-flight-recorder/releases/tag/v0.1.0-alpha.1),
separately from this historical investigation.

## Evidence

The first installed-wheel failure only reported that no startup announcement
arrived within the configured ten-second wait. Its log had a roughly 45.7-second
gap after recording validation, without enough stage information to locate the
earlier delay. That alone did not distinguish server construction, child-process
startup, output buffering, or pipe readiness. Wheel metadata, bundled assets,
and local installed-package behavior had already been checked; those checks did
not prove that remote CLI startup would work.

[Diagnostic CI run 43280737772](https://github.com/Leogy101/agent-flight-recorder/actions/runs/43280737772),
at commit `30df4d2273642ede304610058d3332cef5358a56`, added bounded diagnostics and
test coverage while leaving production behavior unchanged. Both macOS jobs
failed the first real CLI startup attempt:

| Observation | Python 3.11.9 | Python 3.14.10 |
| --- | --- | --- |
| Measured startup stage | 10.003 s, deadline | 10.002 s, deadline |
| Child status before cleanup | Still running | Still running |
| Captured stdout | 0 bytes | 0 bytes |
| Selector | `KqueueSelector` | `KqueueSelector` |
| First server-test fixture setup | 35.01 s | 35.01 s |
| Python test result | 1 failed, 166 passed | 1 failed, 166 passed |

Only `test_real_cli_http_sigint_and_same_port_restart` failed in each job. After
the startup deadline, the harness requested a Python stack snapshot with
`SIGUSR1` before terminating the child. Both versions showed the same call path,
listed here from the CLI toward the blocked operation:

```text
cli.main
  -> make_server
  -> socketserver.TCPServer.__init__
  -> http.server.HTTPServer.server_bind
  -> socket.getfqdn
```

The child had not reached the announcement, whose `print` already uses
`flush=True`. The captured stack therefore explains the observed missing output
without attributing it to stdout buffering. The failure occurs on both tested
Python versions; it is not established as a Python 3.14-only regression or a
kqueue defect.

## Why an IP-bound server did a hostname lookup

`HTTPServer.server_bind` first performs the TCP bind, then calls
`socket.getfqdn(host)` to populate `server_name`. `getfqdn` synchronously invokes
`gethostbyaddr`. The TCP server constructor completes binding before activating
the listening socket. Supplying the numeric loopback address therefore did not
remove this later reverse-name lookup. The CLI announces its URL after the
constructor returns. [CPython HTTP server implementation](https://github.com/python/cpython/blob/v3.14.10/Lib/http/server.py),
[socket implementation](https://github.com/python/cpython/blob/v3.14.10/Lib/socket.py),
[constructor ordering](https://github.com/python/cpython/blob/v3.14.10/Lib/socketserver.py)

This confirms a blocking operation that the application does not need. It does
not identify a defective DNS service, a macOS networking bug, or a particular
GitHub runner configuration. No change to host resolver configuration is needed
for the application correction.

## Correction and regression coverage

The asset server specializes `ThreadingHTTPServer.server_bind`: it calls
`TCPServer.server_bind` directly, assigns the fixed internal name `localhost`,
and records the actual bound port. It continues to bind `127.0.0.1`, serve the
existing asset allowlist, and apply the same Host validation and response
security headers. It needs neither a resolved hostname nor a new dependency.

The regression test replaces `socket.getfqdn` and `socket.gethostbyaddr` with
functions that fail if called, then constructs the real server, checks its
loopback address, actual port, and name, and requires an HTTP 200 response with
the expected asset. Independent review confirmed that the previous production
implementation fails this guard. The smoke test retains its ten-second startup deadline,
HTTP request check, real `SIGINT` shutdown, and restart on the same port. A
longer timeout would leave the unnecessary resolver dependency in place.

Local correction checks passed 168 Python tests in 5.64 seconds and 44 viewer
tests in 1.01 seconds. These results establish local coverage; remote CI,
installed-wheel checks, full browser acceptance, and fresh public-source
installation remain distinct release gates for the corrected commit.

The diagnostic harness drains both pipes without blocking and retains at most
8 KiB from each. Failure summaries include the stage, monotonic elapsed time,
process status before/after cleanup, byte counts, and sanitized output. Stack
frames retain only a filename, line number, and function; machine paths,
unrecognized lines, and exception messages are excluded. Environment reporting
is limited to the OS identifier, Python version, and selector class. No agent
payload, environment-variable dump, or stack locals are collected.

A separate local regression-test synchronization issue initially waited for a
filename fragment from `faulthandler`; the remaining frame could arrive in a
later pipe chunk. That test now waits for the complete sanitized frame. This was
a diagnostic-test race, distinct from the live CLI's confirmed resolver stall.

## Reproduce the relevant checks

In a development environment with the test dependencies installed, run the real
subprocess boundary directly:

```sh
python -m pytest tests/test_installed_smoke.py::test_real_cli_http_sigint_and_same_port_restart -q -s
```

The workflow also builds a wheel, installs it without runtime dependencies into
`work/installed`, and runs the same lifecycle checks through that interpreter:

```sh
work/installed/bin/python tests/installed_smoke.py
```

These commands exercise startup, actual HTTP, shutdown, and port reuse. The
original delay depends on resolver behavior and need not occur on every machine;
the focused server regression deterministically prevents reintroducing the
lookup. A passing diagnostic control or local test is not a substitute for the
full macOS/Linux CI matrix and fresh public-source installation of the final
commit.
