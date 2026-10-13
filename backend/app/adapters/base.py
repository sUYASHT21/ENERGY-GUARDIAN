"""Device adapter interfaces.

Command delivery
----------------
Every non-dry-run command is first persisted with status ``pending``. A *transport* then
gets it to the device:

* ``Esp32HttpPullTransport`` — the ESP32 polls ``GET /api/v1/esp32/commands`` (or receives
  pending commands in the telemetry response). Works behind NAT/firewalls, no inbound ports
  on the device. This is the default for ``esp32`` and ``emulator`` devices.
* ``SimulatedTransport`` — the in-process simulator plays the role of the device and uses the
  exact same fetch/ack service functions as the HTTP endpoints.

Acknowledgement, timeout and failure handling are transport-independent (see
``app.services.commands``). To add e.g. an MQTT or push-HTTP transport, implement
``CommandTransport`` and register it in ``TRANSPORTS``.
"""
from __future__ import annotations

from typing import Protocol

from ..models import Command, Device


class CommandTransport(Protocol):
    name: str

    def dispatch(self, command: Command, device: Device) -> None:
        """Called after a command is queued. Pull transports need not do anything."""


class Esp32HttpPullTransport:
    name = "esp32_http_pull"

    def dispatch(self, command: Command, device: Device) -> None:
        # Device collects the command on its next poll / telemetry post.
        return None


class SimulatedTransport:
    name = "simulated"

    def dispatch(self, command: Command, device: Device) -> None:
        # The simulator polls the queue every tick through services.commands.fetch_pending.
        return None


TRANSPORTS: dict[str, CommandTransport] = {
    "esp32": Esp32HttpPullTransport(),
    "emulator": Esp32HttpPullTransport(),
    "simulated": SimulatedTransport(),
}


def transport_for(device: Device) -> CommandTransport:
    return TRANSPORTS[device.kind]
