# Print Agent

A standalone local print agent that polls an Odoo `receipt_printer` module for pending print jobs and sends them to physical printers. Supports ESC/POS receipt printers, HP inkjet/laser printers, and USB-connected printers.

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 2. Configure

Copy the example config and edit it:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your Odoo URL, printer(s), and API keys. See `config.example.yaml` for all options.

### 3. Run

```bash
# Start the print service (continuous polling)
python -m print_agent -c config.yaml

# Or open the config editor in your browser
python -m print_agent.gui
```

This starts the poll loop — the agent will continuously check Odoo for pending jobs and print them.

## CLI Options

```
python -m print_agent [OPTIONS]

Options:
  -c, --config PATH   Path to YAML config file (default: config.yaml)
  -v, --verbose       Enable debug logging
  --once              Run a single poll cycle then exit (for testing)
  --job-delay SECS    Seconds to wait between print jobs (default: 2.0)
```

Examples:

```bash
# Continuous polling with verbose logging
python -m print_agent -c config.yaml --verbose

# Single test cycle
python -m print_agent -c config.yaml --once

# Faster printing (1 second between jobs)
python -m print_agent -c config.yaml --job-delay 1

# Slower printing for slow printers (5 seconds between jobs)
python -m print_agent -c config.yaml --job-delay 5
```

### Job Delay

The `--job-delay` option controls how long the agent waits between sending print jobs to a printer. This prevents overwhelming the printer with back-to-back jobs, which can cause lag or missed pages.

| Printer Type | Recommended Delay | Reason |
|-------------|-------------------|--------|
| ESC/POS receipt (thermal) | 1–2 seconds | Fast printers, small receipts |
| HP inkjet/laser | 2–5 seconds | Slower processing, larger documents |
| USB receipt | 1–2 seconds | Similar to network ESC/POS |

If your printer is lagging or skipping jobs, increase the delay. If jobs are piling up and printing too slowly, decrease it.

## Configuration

### Via Web GUI

```bash
python -m print_agent.gui          # opens at http://localhost:8080
python -m print_agent.gui -p 3000  # custom port
python -m print_agent.gui -c my_config.yaml  # custom config file
```

The GUI is a standalone editor — it reads/writes `config.yaml` directly. The service reads config on startup, so restart the service after making changes in the GUI. The GUI and service are completely independent and can run at the same time.

### Via Config File

Copy the example config and edit it:

```yaml
odoo_url: "http://localhost:8069"

printers:
  # ESC/POS receipt printer (thermal, port 9100)
  - name: receipt_main
    connection_type: network
    host: "192.168.1.100"
    port: 9100
    api_key: "your-printer-api-key"

  # HP/standard inkjet/laser printer
  - name: hp_office
    connection_type: ipp
    host: "192.168.1.50"
    port: 3911
    api_key: "your-printer-api-key"

  # USB-connected receipt printer
  - name: receipt_usb
    connection_type: usb
    vendor_id: 0x0456
    product_id: 0x0808
    api_key: "your-usb-printer-api-key"
```

### Connection Types

| Type | Use For | Port |
|------|---------|------|
| `network` | ESC/POS receipt printers (thermal) | 9100 (default) |
| `ipp` | HP, Brother, Canon inkjet/laser printers | 631 or printer-specific |
| `usb` | USB-connected receipt printers | N/A |

### Finding your printer's port

For HP printers, the port depends on how it's connected:

- **Network (TCP/IP)**: Check the printer's network settings page. Common ports: 9100, 631, 515, or custom (like 3911).
- **USB**: The OS assigns a device path (Linux: `/dev/usb/lp0`, Windows: check Device Manager).

The `ipp` connection type automatically tries IPP protocol, raw HTTP, and raw TCP — so it works even if the printer doesn't support IPP.

## Running Tests

```bash
source .venv/bin/activate
python -m pytest print_agent/tests/ -v
```

## Project Structure

```
print_agent/
├── __init__.py
├── __main__.py           # Entry point
├── cli.py                # CLI argument parsing
├── config.py             # YAML config loading
├── connections/
│   ├── base.py           # PrinterConnection ABC + exceptions
│   ├── network.py        # ESC/POS via raw TCP (port 9100)
│   ├── usb.py            # USB via python-escpos
│   └── ipp.py            # HP/standard printers (IPP + HTTP + raw TCP)
├── rendering.py          # Payload → ESC/POS bytes or raw image
├── odoo_client.py        # HTTP client for Odoo API
├── orchestrator.py       # Poll loop tying everything together
├── tests/
│   ├── test_config.py
│   ├── test_connections.py
│   ├── test_ipp.py
│   ├── test_odoo_client.py
│   ├── test_orchestrator.py
│   ├── test_rendering.py
│   └── test_cli.py
├── config.example.yaml
└── requirements.txt
```

## How It Works

1. **Polls Odoo** via `GET /receipt_printer/pending_jobs` for each configured printer
2. **Renders** the payload (base64 images for IPP/USB, ESC/POS bytes for network printers)
3. **Sends** to the printer via the appropriate connection type
4. **Acks** the job back to Odoo via `POST /receipt_printer/ack` with status `printed` or `failed`

The agent handles multiple printers independently — one printer going offline doesn't block the others. Failed jobs are acked as `failed` so Odoo knows they won't print.

## Requirements

- Python 3.10+
- Dependencies in `requirements.txt`: `pyyaml`, `python-escpos`, `requests`, `Pillow`

## Running Script as Service

To run the script as a service, make sure you have the following installed:
1. Python
2. Git
3. [Choclatey](https://chocolatey.org/install)

Follow the steps below: 
1. In a priviledged Powershell session install NSSM with ```bash choco install nssm ```
2. Clone the Github repo in C:/print_agent for example
3. Create python virtual environment and activate it
4. Install python dependencies
5. Configure printers (either with config.yaml or on site by running ```bash python -m print_agent.gui```)
6. Create NSSM service by running ``` nssm start OdooPrintAgent ``` with the following details:
   1. Application path: location of python in created virtual environment e.g. ``` C:\print_agent\.venv\Scripts\python.exe ```
   2. Application startup directory: directory script is installed in e.g. ``` C:\print_agent\ ```
   3. Arguements: ``` -m print_agent --config  C:\print_agent\config.yaml ```
   4. Optionally can configure details in details tab
7. Set auto start with ``` nssm set OdooPrintAgent Start SERVICE_AUTO_START ```
8. Set logging locations with ``` nssm set OdooPrintAgent AppStderr C:\print_agent\service_stderr.log ```  and ``` nssm set OdooPrintAgent AppStdout C:\print_agent\service_stdout.log ``` 
9. Start service with ``` nssm start OdooPrintAgent ```

Some useful commands are ``` nssm stop OdooPrintAgent ``` to stop the service ``` nssm restart OdooPrintAgent ``` to restart the agent and ``` nssm edit OdooPrintAgent ``` to edit configuration of the service and running Win + R and services.msc to get list of running services

