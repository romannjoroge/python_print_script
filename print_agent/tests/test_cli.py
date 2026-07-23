"""Tests for CLI entrypoint."""

import os
import tempfile
from unittest.mock import patch

import pytest
import yaml

from print_agent.cli import main


def _write_config(data: dict) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        yaml.dump(data, f)
    return path


VALID_CONFIG = {
    "odoo_url": "http://localhost:8069",
    "printers": [
        {
            "name": "test_printer",
            "connection_type": "network",
            "host": "10.0.0.1",
            "port": 9100,
            "api_key": "test_key",
        }
    ],
}


class TestCLI:
    def test_missing_config_returns_error(self):
        result = main(["--config", "/nonexistent/config.yaml"])
        assert result == 1

    def test_valid_config_runs_once(self):
        path = _write_config(VALID_CONFIG)
        try:
            result = main(["--config", path, "--once"])
            assert result == 0
        finally:
            os.unlink(path)

    def test_default_config_flag(self):
        path = _write_config(VALID_CONFIG)
        try:
            # Simulate running with the config file as cwd default
            result = main(["--config", path, "--once"])
            assert result == 0
        finally:
            os.unlink(path)

    def test_verbose_flag_sets_debug(self):
        path = _write_config(VALID_CONFIG)
        try:
            with patch("print_agent.orchestrator.Orchestrator._poll_once"):
                result = main(["--config", path, "--verbose", "--once"])
            assert result == 0
        finally:
            os.unlink(path)

    def test_empty_printers_list_runs(self):
        data = {"odoo_url": "http://localhost:8069", "printers": []}
        path = _write_config(data)
        try:
            result = main(["--config", path, "--once"])
            assert result == 0
        finally:
            os.unlink(path)

    def test_keyboard_interrupt_returns_zero(self):
        path = _write_config(VALID_CONFIG)
        try:
            with patch("print_agent.orchestrator.Orchestrator.run", side_effect=KeyboardInterrupt):
                result = main(["--config", path])
            assert result == 0
        finally:
            os.unlink(path)
