# AGENT.md — Local Print Agent

## Project Summary

Build a standalone local print agent (Python) that polls the `receipt_printer`
Odoo module's HTTP routes for pending print jobs and prints them to a physical
receipt printer using ESC/POS commands. Must support two connection types:

- **USB** — printer connected directly to the machine running the agent.
- **Network** — printer reachable over TCP/IP on the local network (most
  ESC/POS network printers listen on raw port 9100).

This agent is the counterpart to the Odoo module built separately. It exposes the following API routes:

1. `GET /receipt_printer/pending_jobs` — query param or header identifies the
  printer (by id + api_key). Returns pending jobs for that printer only, as
  JSON: `{"jobs": [{"id": ..., "payload": ...}, ...]}`. Must not return jobs
  belonging to other printers.
2. `POST /receipt_printer/ack` — body: `{"job_id": ..., "status": "printed"|"failed",
  "error_message": "..."}` (error_message optional, required if status is
  failed). Calls the model methods above. Returns 200 with a small
  confirmation JSON, or an appropriate 4xx if job_id doesn't exist or doesn't
  belong to the authenticated printer.
- These routes are `type="http"`, `auth="none"` (auth handled manually via
  api_key, not Odoo session), CSRF disabled (agent isn't a browser session).

Do not build or modify the Odoo module here — only consume its HTTP API as a client.

## Development Method: Test-Driven Development

Hard requirement. For every piece of functionality:

1. Write a failing test first that describes the desired behavior.
2. Run it and confirm it fails for the expected reason (not a typo/import
   error).
3. Write the minimum code to make it pass.
4. Run the full test suite and confirm nothing else broke.
5. Refactor if needed, keeping tests green.
6. Only then move to the next piece of functionality.

Never write implementation code before its test exists. If implementation gets
written first, stop, delete it, and write the test first instead. Commit after
each red-green-refactor cycle so the history shows the TDD process, and
summarize what was built/tested after each phase below.

**Testing constraint specific to this project:** you cannot rely on real hardware being present in the test environment. All tests must run without a physical USB or network printer attached:

- Abstract the actual byte-sending behind a small interface (e.g. a
  `PrinterConnection` class with `open()`, `write(bytes)`, `close()`) so tests can substitute a fake/mock connection and assert on the bytes it received, rather than needing a real printer.
- Use `pytest` with `unittest.mock` (or `pyfakeusb`/similar if helpful) to simulate USB device discovery and network socket behavior.
- Use a local mock HTTP server (e.g. `pytest-httpserver`, or `responses`/  `requests-mock`) to simulate the Odoo endpoints — do not require a real Odoo instance to run the test suite.
- A small number of manual/integration tests that do require real hardware are fine, but must be clearly separated (e.g. a `tests/manual/` folder or a  pytest marker like `@pytest.mark.hardware`) and excluded from the default test run.

## Scope

### 1. Configuration
- A config file (YAML or JSON, agent's choice, but pick one and be
  consistent) defining:
  - Odoo base URL.
  - One or more printers, each with: local identifier/name, connection type (`usb` or `network`), connection-specific details (USB: vendor_id/ product_id, or a device path; network: host + port, default port 9100), and the printer's `api_key` (matches the `direct.print.printer` record in Odoo — this is how the agent identifies which printer's jobs to fetch).
- Config loading must validate required fields per connection type and fail with a clear error message if something's missing, rather than failing deep inside a printer call.
- Test coverage: valid config loads correctly into typed objects; missing required fields per connection type raise clear errors; unknown connection type is rejected.

### 2. Printer connection abstraction
- A common interface (`PrinterConnection` or similar) with at least
  `connect()`, `send(data: bytes)`, `disconnect()`, and something like
  `is_available()` for a lightweight reachability check.
- Two implementations:
  - `UsbPrinterConnection` — wraps raw USB or `python-escpos`'s `Usb` class.
  - `NetworkPrinterConnection` — opens a TCP socket to host:port and writes raw bytes (standard approach for port 9100 "raw" printing).
- Both must raise a common, agent-defined exception type on failure (e.g. `PrinterConnectionError`) so upstream code doesn't need to know which transport is in use.
- Test coverage: each implementation sends the exact bytes given, without mutating them; connection failures (device not found / socket refused) are caught and re-raised as `PrinterConnectionError`; `is_available()` reflects simulated up/down state.

### 3. Receipt rendering
- A function/class that takes a job payload (JSON is as described in routes of the Odoo module) and produces ESC/POS byte output using
  `python-escpos`'s in-memory/dummy profile (it supports a "dummy" printer mode that captures output as bytes without needing a device — use this for testing render logic in isolation from the connection layer).

### 4. Odoo client
- A thin client wrapping the two routes from the Odoo module:
  - `GET /receipt_printer/pending_jobs` (with the printer's api_key) → list of
    jobs.
  - `POST /receipt_printer/ack` (job_id, status, optional error_message).
- Handle and surface HTTP errors, timeouts, and unexpected response shapes distinctly (don't let a malformed response crash the poll loop silently).
- Test coverage: correct request shape/headers sent; successful response parsed into typed job objects; various failure responses (401, 404, 500, timeout, malformed JSON) are handled without raising unhandled exceptions out of the client.

### 5. Poll loop / orchestration
- For each configured printer, on an interval: fetch pending jobs, render and send each one via its connection, ack success/failure back to Odoo.
- Must not let one printer's failure (offline, USB unplugged) stop polling for other configured printers.
- Retry/backoff behavior on repeated connection failure (don't hammer an offline printer or the Odoo server every second forever — back off, but keep trying).
- Test coverage: with mocked Odoo client and mocked connections, verify the orchestration logic — job success calls ack with `printed`, connection failure calls ack with `failed` and a message (or leaves the job for retry if you decide not to ack on transient failure — decide and document this behavior explicitly, then test it), and one printer's failure doesn't block another's jobs from being processed in the same cycle.

### 6. CLI / entrypoint
- A simple command to run the agent (`python -m print_agent` or similar), reading the config file, starting the poll loop, and logging job activity and errors to stdout/a log file.
- Test coverage: minimal here is fine — focus on config-loading and
  wiring being exercised, not the infinite loop itself (structure the loop so it can be run for a bounded number of iterations in tests).

## Project Structure (expected)

```
print_agent/
    __init__.py
    config.py              # config loading/validation
    connections/
        __init__.py
        base.py             # PrinterConnection interface + exceptions
        usb.py
        network.py
    rendering.py            # payload -> ESC/POS bytes
    odoo_client.py          # HTTP client for the two routes
    orchestrator.py         # poll loop tying it all together
    cli.py                  # entrypoint
    tests/
        test_config.py
        test_connections.py
        test_rendering.py
        test_odoo_client.py
        test_orchestrator.py
        manual/                 # hardware-in-the-loop tests, excluded by default
            test_real_usb_printer.py
            test_real_network_printer.py
    config.example.yaml
    requirements.txt
```

## Build Order

Work in this order; do not start a phase until the previous phase's tests
pass:

1. Config loading + validation + tests.
2. `PrinterConnection` interface + USB implementation + tests (mocked USB).
3. `PrinterConnection` network implementation + tests (mocked socket).
4. Receipt rendering (payload → ESC/POS bytes via dummy printer) + tests.
5. Odoo client (pending_jobs, ack) + tests (mocked HTTP).
6. Orchestrator/poll loop tying 1–5 together + tests.
7. CLI entrypoint + logging.

## Constraints & Conventions

- Python 3.10+, `python-escpos` for ESC/POS generation, `pytest` for testing.
- Keep the connection abstraction genuinely swappable — adding a third
  transport (e.g. Bluetooth) later should mean adding one new class, not touching rendering/orchestration/client code.
- Config format, once chosen, should be documented with a `config.example.yaml` (or `.json`) checked into the repo.
- Log clearly enough that a non-developer running this agent can tell from the console/log file whether it's working, and if not, roughly why (printer unreachable vs. Odoo unreachable vs. bad job payload).
- After each phase, summarize: what was built, what tests were written, test results, and any deviations from this spec with reasoning.

## Out of Scope (do not build)

- The Odoo module itself (separate project).
- Bluetooth or other transports beyond USB/network for now (but keep the abstraction open to it).
- A GUI or installer/packaging — a runnable Python script/module is enough for this phase.
- Multi-tenant / multi-Odoo-instance support — one config, one Odoo backend.