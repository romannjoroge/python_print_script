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
python -m print_agent -c config.yaml
```

This starts the poll loop — the agent will continuously check Odoo for pending jobs and print them.

## CLI Options

```
python -m print_agent [OPTIONS]

Options:
  -c, --config PATH   Path to YAML config file (default: config.yaml)
  -v, --verbose       Enable debug logging
  --once              Run a single poll cycle then exit (for testing)
```

Examples:

```bash
# Continuous polling with verbose logging
python -m print_agent -c config.yaml --verbose

# Single test cycle
python -m print_agent -c config.yaml --once
```

## Configuration

See `config.example.yaml` for a full example. Key fields:

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
