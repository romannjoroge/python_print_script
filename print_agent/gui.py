"""Simple web-based configuration editor.

Run standalone to edit config.yaml via a browser.
Does NOT affect the running service — service reads config on startup only.

Usage:
    python -m print_agent.gui
    python -m print_agent.gui --port 8080
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

CONFIG_PATH = "config.yaml"
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Print Agent Config</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; background: #f5f5f5; padding: 20px; }
h1 { margin-bottom: 20px; color: #333; }
.container { max-width: 800px; margin: 0 auto; }
.card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.card h2 { font-size: 16px; margin-bottom: 12px; color: #555; }
label { display: block; font-size: 13px; color: #666; margin-bottom: 4px; }
input, select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; margin-bottom: 12px; }
input:focus, select:focus { outline: none; border-color: #4a90d9; }
.row { display: flex; gap: 12px; }
.row > div { flex: 1; }
.btn { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
.btn-primary { background: #4a90d9; color: white; }
.btn-primary:hover { background: #357abd; }
.btn-danger { background: #e74c3c; color: white; }
.btn-danger:hover { background: #c0392b; }
.btn-secondary { background: #95a5a6; color: white; }
.btn-secondary:hover { background: #7f8c8d; }
.btn-group { display: flex; gap: 8px; margin-top: 12px; }
.printer-card { border: 1px solid #eee; border-radius: 6px; padding: 16px; margin-bottom: 12px; position: relative; }
.printer-card h3 { font-size: 14px; margin-bottom: 8px; color: #333; }
.remove-btn { position: absolute; top: 8px; right: 8px; background: none; border: none; color: #e74c3c; cursor: pointer; font-size: 18px; }
.msg { padding: 10px; border-radius: 4px; margin-bottom: 12px; display: none; }
.msg-success { background: #d4edda; color: #155724; }
.msg-error { background: #f8d7da; color: #721c24; }
.hidden { display: none; }
</style>
</head>
<body>
<div class="container">
<h1>Print Agent Configuration</h1>
<div id="msg" class="msg"></div>

<form id="configForm">
  <div class="card">
    <h2>Odoo Connection</h2>
    <label for="odoo_url">Odoo URL</label>
    <input type="text" id="odoo_url" name="odoo_url" placeholder="http://localhost:8069">
  </div>

  <div class="card">
    <h2>Printers</h2>
    <div id="printers"></div>
    <button type="button" class="btn btn-secondary" onclick="addPrinter()">+ Add Printer</button>
  </div>

  <div class="btn-group">
    <button type="submit" class="btn btn-primary">Save Configuration</button>
  </div>
</form>
</div>

<script>
let config = { printers: [] };

async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        config = await resp.json();
        document.getElementById('odoo_url').value = config.odoo_url || '';
        renderPrinters();
    } catch(e) { showError('Failed to load config: ' + e); }
}

function renderPrinters() {
    const container = document.getElementById('printers');
    container.innerHTML = '';
    config.printers.forEach((p, i) => {
        const div = document.createElement('div');
        div.className = 'printer-card';
        div.innerHTML = `
            <button type="button" class="remove-btn" onclick="removePrinter(${i})">&times;</button>
            <h3>Printer ${i + 1}</h3>
            <div class="row">
                <div><label>Name</label><input value="${p.name||''}" onchange="config.printers[${i}].name=this.value"></div>
                <div><label>API Key</label><input value="${p.api_key||''}" onchange="config.printers[${i}].api_key=this.value"></div>
            </div>
            <div class="row">
                <div><label>Connection Type</label>
                    <select onchange="updateConnectionType(${i}, this.value)">
                        <option value="network" ${p.connection_type==='network'?'selected':''}>Network (ESC/POS)</option>
                        <option value="ipp" ${p.connection_type==='ipp'?'selected':''}>IPP (HP/Standard)</option>
                        <option value="usb" ${p.connection_type==='usb'?'selected':''}>USB</option>
                    </select>
                </div>
                <div><label>Host</label><input value="${p.host||''}" onchange="config.printers[${i}].host=this.value" ${p.connection_type==='usb'?'disabled':''}></div>
                <div><label>Port</label><input type="number" value="${p.port||''}" onchange="config.printers[${i}].port=parseInt(this.value)"></div>
            </div>
            <div id="usb-fields-${i}" class="${p.connection_type==='usb'?'':'hidden'}">
                <div class="row">
                    <div><label>Vendor ID (hex)</label><input value="${p.vendor_id||''}" onchange="config.printers[${i}].vendor_id=parseInt(this.value)"></div>
                    <div><label>Product ID (hex)</label><input value="${p.product_id||''}" onchange="config.printers[${i}].product_id=parseInt(this.value)"></div>
                    <div><label>Device Path</label><input value="${p.device_path||''}" onchange="config.printers[${i}].device_path=this.value"></div>
                </div>
            </div>
        `;
        container.appendChild(div);
    });
}

function addPrinter() {
    config.printers.push({name:'', connection_type:'network', host:'', port:9100, api_key:''});
    renderPrinters();
}

function removePrinter(i) {
    config.printers.splice(i, 1);
    renderPrinters();
}

function updateConnectionType(i, type) {
    config.printers[i].connection_type = type;
    if (type === 'network') config.printers[i].port = 9100;
    if (type === 'ipp') config.printers[i].port = 631;
    if (type === 'usb') config.printers[i].port = 0;
    renderPrinters();
}

function showMsg(text, isError) {
    const el = document.getElementById('msg');
    el.textContent = text;
    el.className = 'msg ' + (isError ? 'msg-error' : 'msg-success');
    el.style.display = 'block';
    setTimeout(() => el.style.display = 'none', 3000);
}

function showError(text) { showMsg(text, true); }
function showSuccess(text) { showMsg(text, false); }

document.getElementById('configForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    config.odoo_url = document.getElementById('odoo_url').value;
    try {
        const resp = await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config, null, 2)
        });
        if (resp.ok) showSuccess('Configuration saved!');
        else showError('Failed to save: ' + await resp.text());
    } catch(err) { showError('Save failed: ' + err); }
});

loadConfig();
</script>
</body>
</html>"""


class ConfigHandler(BaseHTTPRequestHandler):
    config_path: str = CONFIG_PATH

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_html()
        elif self.path == "/api/config":
            self._serve_config()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/config":
            self._save_config()
        else:
            self.send_error(404)

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode())

    def _serve_config(self):
        try:
            with open(self.config_path) as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            data = {"odoo_url": "", "printers": []}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _save_config(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        try:
            with open(self.config_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            self.send_error(500, str(e))

    def log_message(self, format, *args):
        pass  # Suppress request logging


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print Agent Config Editor")
    parser.add_argument("-p", "--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")
    args = parser.parse_args(argv)

    ConfigHandler.config_path = args.config
    server = HTTPServer(("localhost", args.port), ConfigHandler)
    print(f"Config editor running at http://localhost:{args.port}")
    print(f"Editing: {os.path.abspath(args.config)}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
