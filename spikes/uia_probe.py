"""Standalone, read only UIA discovery probe for Fakturama.

Run this first, before any automation code is built, to confirm real UIA
control types and names come back for a running Fakturama window. This
script must not write to or click anything in Fakturama; it only connects
and prints back discoverable control identifiers.

Usage (on the Windows 11 ARM VM, with Fakturama already running):
    python spikes/uia_probe.py

If the printed control tree comes back sparse (few or no named controls
for what should be a rich Java/Eclipse RCP UI), see the README section on
Java Access Bridge: run "jabswitch.exe /enable" and relaunch Fakturama,
then rerun this probe.
"""

from __future__ import annotations

from pywinauto import Application


def main() -> None:
    """Connect to the running Fakturama window and print its control tree."""
    app = Application(backend="uia").connect(title_re=".*Fakturama.*")
    window = app.top_window()
    window.print_control_identifiers()


if __name__ == "__main__":
    main()
