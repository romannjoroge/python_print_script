"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""


@dataclass(frozen=True)
class PrinterConfig:
    """Base printer configuration."""

    name: str
    api_key: str
    connection_type: str


@dataclass(frozen=True)
class NetworkPrinterConfig(PrinterConfig):
    """Network printer (TCP/IP, typically port 9100)."""

    connection_type: Literal["network"] = "network"
    host: str = ""
    port: int = 9100


@dataclass(frozen=True)
class UsbPrinterConfig(PrinterConfig):
    """USB printer connected locally."""

    connection_type: Literal["usb"] = "usb"
    vendor_id: int | None = None
    product_id: int | None = None
    device_path: str | None = None


@dataclass(frozen=True)
class IppPrinterConfig(PrinterConfig):
    """IPP printer (HP inkjet/laser, Brother, Canon, etc.)."""

    connection_type: Literal["ipp"] = "ipp"
    host: str = ""
    port: int = 631
    printer_uri: str = ""


@dataclass(frozen=True)
class Config:
    """Top-level agent configuration."""

    odoo_url: str
    printers: list[PrinterConfig] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: str | Path) -> Config:
        path = Path(path)
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")

        try:
            raw = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {path}: {e}") from e

        if not isinstance(raw, dict):
            raise ConfigError(f"Config must be a YAML mapping, got {type(raw).__name__}")

        # Validate odoo_url
        odoo_url = raw.get("odoo_url")
        if not odoo_url:
            raise ConfigError("Missing required field: 'odoo_url'")

        # Validate printers
        raw_printers = raw.get("printers")
        if raw_printers is None:
            raise ConfigError("Missing required field: 'printers'")

        if not isinstance(raw_printers, list):
            raise ConfigError("'printers' must be a list")

        printers: list[PrinterConfig] = []
        for i, p in enumerate(raw_printers):
            printers.append(_parse_printer(p, index=i))

        return cls(odoo_url=odoo_url, printers=printers)


def _parse_printer(raw: dict, index: int) -> PrinterConfig:
    prefix = f"Printer #{index}"

    name = raw.get("name")
    if not name:
        raise ConfigError(f"{prefix}: missing required field 'name'")

    api_key = raw.get("api_key")
    if not api_key:
        raise ConfigError(f"{prefix} ({name}): missing required field 'api_key'")

    connection_type = raw.get("connection_type")
    if not connection_type:
        raise ConfigError(f"{prefix} ({name}): missing required field 'connection_type'")

    if connection_type == "network":
        host = raw.get("host")
        if not host:
            raise ConfigError(
                f"{prefix} ({name}): network printer requires 'host'"
            )
        return NetworkPrinterConfig(
            name=name,
            api_key=api_key,
            host=host,
            port=raw.get("port", 9100),
        )

    if connection_type == "usb":
        vendor_id = raw.get("vendor_id")
        product_id = raw.get("product_id")
        device_path = raw.get("device_path")

        if device_path is None and (vendor_id is None or product_id is None):
            raise ConfigError(
                f"{prefix} ({name}): USB printer requires either "
                "'device_path' or both 'vendor_id' and 'product_id'"
            )

        return UsbPrinterConfig(
            name=name,
            api_key=api_key,
            vendor_id=vendor_id,
            product_id=product_id,
            device_path=device_path,
        )

    if connection_type == "ipp":
        host = raw.get("host")
        if not host:
            raise ConfigError(
                f"{prefix} ({name}): IPP printer requires 'host'"
            )
        return IppPrinterConfig(
            name=name,
            api_key=api_key,
            host=host,
            port=raw.get("port", 631),
            printer_uri=raw.get("printer_uri", ""),
        )

    raise ConfigError(
        f"{prefix} ({name}): Unknown connection type '{connection_type}'. "
        "Valid types: 'network', 'usb', 'ipp'"
    )
