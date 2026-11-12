"""Start the signed-in desktop app or an isolated Figma demonstration."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import secrets
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from petcare.db import Store
from petcare.ui import MainWindow


def main():
    parser = argparse.ArgumentParser(description="PetCare AI")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="Open the synthetic demo in memory")
    mode.add_argument("--db", type=Path, help="Use a specific local SQLite database")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("PetCare AI")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "ui" / "brand.svg")))
    default_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "PetCareAI"
    store = Store(":memory:" if args.demo else args.db or default_dir / "petcare.sqlite3")
    try:
        session = None
        clock = datetime.now
        if args.demo:
            password = secrets.token_urlsafe(24)
            store.register("Аружан Касанова", "demo@example.invalid", password)
            session = store.login("demo@example.invalid", password)
            store.seed_demo(session)
            clock = lambda: datetime(2026, 10, 29, 18, 0)
        window = MainWindow(store, session=session, clock=clock, demo=args.demo)
        window.show()
        return app.exec()
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

