from __future__ import annotations

from pywinauto import Application


def main() -> None:
    app = Application(backend="uia").connect(title_re=".*Fakturama.*")
    window = app.top_window()
    window.print_control_identifiers()


if __name__ == "__main__":
    main()
