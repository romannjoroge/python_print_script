"""Tests for config loading and validation."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from print_agent.config import (
    Config,
    ConfigError,
    PrinterConfig,
    NetworkPrinterConfig,
    UsbPrinterConfig,
)


VALID_CONFIG = {
    "odoo_url": "http://localhost:8069",
    "printers": [
        {
            "name": "receipt_main",
            "connection_type": "network",
            "host": "192.168.1.100",
            "port": 9100,
            "api_key": "abc123",
        },
        {
            "name": "receipt_usb",
            "connection_type": "usb",
            "vendor_id": 0x0456,
            "product_id": 0x0808,
            "api_key": "def456",
        },
    ],
}


def _write_config(data: dict) -> str:
    """Write a YAML config to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        yaml.dump(data, f)
    return path


class TestConfigLoading:
    def test_valid_config_loads_correctly(self):
        path = _write_config(VALID_CONFIG)
        try:
            config = Config.from_file(path)
            assert config.odoo_url == "http://localhost:8069"
            assert len(config.printers) == 2
        finally:
            os.unlink(path)

    def test_network_printer_config_fields(self):
        path = _write_config(VALID_CONFIG)
        try:
            config = Config.from_file(path)
            net = [p for p in config.printers if p.connection_type == "network"][0]
            assert isinstance(net, NetworkPrinterConfig)
            assert net.name == "receipt_main"
            assert net.host == "192.168.1.100"
            assert net.port == 9100
            assert net.api_key == "abc123"
        finally:
            os.unlink(path)

    def test_usb_printer_config_fields(self):
        path = _write_config(VALID_CONFIG)
        try:
            config = Config.from_file(path)
            usb = [p for p in config.printers if p.connection_type == "usb"][0]
            assert isinstance(usb, UsbPrinterConfig)
            assert usb.name == "receipt_usb"
            assert usb.vendor_id == 0x0456
            assert usb.product_id == 0x0808
            assert usb.api_key == "def456"
        finally:
            os.unlink(path)

    def test_usb_with_device_path(self):
        data = {
            "odoo_url": "http://localhost:8069",
            "printers": [
                {
                    "name": "usb_dev",
                    "connection_type": "usb",
                    "device_path": "/dev/usb/lp0",
                    "api_key": "key1",
                },
            ],
        }
        path = _write_config(data)
        try:
            config = Config.from_file(path)
            usb = config.printers[0]
            assert isinstance(usb, UsbPrinterConfig)
            assert usb.device_path == "/dev/usb/lp0"
        finally:
            os.unlink(path)

    def test_network_printer_default_port(self):
        data = {
            "odoo_url": "http://localhost:8069",
            "printers": [
                {
                    "name": "no_port",
                    "connection_type": "network",
                    "host": "10.0.0.1",
                    "api_key": "k",
                },
            ],
        }
        path = _write_config(data)
        try:
            config = Config.from_file(path)
            assert config.printers[0].port == 9100
        finally:
            os.unlink(path)


class TestConfigValidation:
    def test_missing_odoo_url_raises(self):
        data = {"printers": []}
        path = _write_config(data)
        try:
            with pytest.raises(ConfigError, match="odoo_url"):
                Config.from_file(path)
        finally:
            os.unlink(path)

    def test_missing_printers_raises(self):
        data = {"odoo_url": "http://localhost:8069"}
        path = _write_config(data)
        try:
            with pytest.raises(ConfigError, match="printers"):
                Config.from_file(path)
        finally:
            os.unlink(path)

    def test_empty_printers_list_is_valid(self):
        data = {"odoo_url": "http://localhost:8069", "printers": []}
        path = _write_config(data)
        try:
            config = Config.from_file(path)
            assert len(config.printers) == 0
        finally:
            os.unlink(path)

    def test_missing_printer_name_raises(self):
        data = {
            "odoo_url": "http://localhost:8069",
            "printers": [
                {"connection_type": "network", "host": "x", "api_key": "k"},
            ],
        }
        path = _write_config(data)
        try:
            with pytest.raises(ConfigError, match="name"):
                Config.from_file(path)
        finally:
            os.unlink(path)

    def test_missing_printer_api_key_raises(self):
        data = {
            "odoo_url": "http://localhost:8069",
            "printers": [
                {"name": "p", "connection_type": "network", "host": "x"},
            ],
        }
        path = _write_config(data)
        try:
            with pytest.raises(ConfigError, match="api_key"):
                Config.from_file(path)
        finally:
            os.unlink(path)

    def test_missing_connection_type_raises(self):
        data = {
            "odoo_url": "http://localhost:8069",
            "printers": [{"name": "p", "api_key": "k"}],
        }
        path = _write_config(data)
        try:
            with pytest.raises(ConfigError, match="connection_type"):
                Config.from_file(path)
        finally:
            os.unlink(path)

    def test_unknown_connection_type_raises(self):
        data = {
            "odoo_url": "http://localhost:8069",
            "printers": [
                {"name": "p", "connection_type": "bluetooth", "api_key": "k"},
            ],
        }
        path = _write_config(data)
        try:
            with pytest.raises(ConfigError, match="Unknown connection type"):
                Config.from_file(path)
        finally:
            os.unlink(path)

    def test_network_missing_host_raises(self):
        data = {
            "odoo_url": "http://localhost:8069",
            "printers": [
                {"name": "p", "connection_type": "network", "api_key": "k"},
            ],
        }
        path = _write_config(data)
        try:
            with pytest.raises(ConfigError, match="host"):
                Config.from_file(path)
        finally:
            os.unlink(path)

    def test_usb_missing_both_vendor_product_and_device_path_raises(self):
        data = {
            "odoo_url": "http://localhost:8069",
            "printers": [
                {"name": "p", "connection_type": "usb", "api_key": "k"},
            ],
        }
        path = _write_config(data)
        try:
            with pytest.raises(ConfigError, match="vendor_id.*product_id|device_path"):
                Config.from_file(path)
        finally:
            os.unlink(path)

    def test_nonexistent_file_raises(self):
        with pytest.raises(ConfigError, match="not found"):
            Config.from_file("/nonexistent/config.yaml")

    def test_invalid_yaml_raises(self):
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w") as f:
            f.write("{{invalid yaml}}")
        try:
            with pytest.raises(ConfigError):
                Config.from_file(path)
        finally:
            os.unlink(path)
