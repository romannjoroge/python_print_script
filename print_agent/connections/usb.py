"""USB printer connection implementation."""

from __future__ import annotations

from print_agent.connections.base import PrinterConnection, PrinterConnectionError


class UsbPrinterConnection(PrinterConnection):
    """USB printer using python-escpos under the hood."""

    def __init__(
        self,
        vendor_id: int | None = None,
        product_id: int | None = None,
        device_path: str | None = None,
    ) -> None:
        self._vendor_id = vendor_id
        self._product_id = product_id
        self._device_path = device_path
        self._device = None

    def connect(self) -> None:
        try:
            from escpos.escpos import Escpos

            if self._device_path:
                self._device = Escpos()
                # For device path, we'd need custom setup;
                # for now, rely on vendor_id/product_id path
            else:
                self._device = Escpos(
                    usbVendor=self._vendor_id,
                    usbProduct=self._product_id,
                )
        except Exception as e:
            raise PrinterConnectionError(f"Failed to open USB device: {e}") from e

    def send(self, data: bytes) -> None:
        if self._device is None:
            raise PrinterConnectionError("USB printer not connected")
        try:
            self._device.write(data)
        except Exception as e:
            raise PrinterConnectionError(f"USB write failed: {e}") from e

    def disconnect(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    def is_available(self) -> bool:
        return self._device is not None
