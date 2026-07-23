"""Base printer connection interface and exceptions."""

from __future__ import annotations

from abc import ABC, abstractmethod


class PrinterConnectionError(Exception):
    """Raised when a printer connection operation fails."""


class PrinterNotAvailableError(PrinterConnectionError):
    """Raised when a printer is not reachable."""


class PrinterConnection(ABC):
    """Abstract interface for printer connections."""

    @abstractmethod
    def connect(self) -> None:
        """Open the connection to the printer."""

    @abstractmethod
    def send(self, data: bytes) -> None:
        """Send raw bytes to the printer."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection to the printer."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the printer is currently connected."""
