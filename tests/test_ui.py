"""Exercise the real Qt navigation against the SQLite store in a headless session."""
import os
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QTableWidget
from PySide6.QtWidgets import QMessageBox

from petcare.db import Store
from petcare.ui import MainWindow


@pytest.fixture
def workspace(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "ui.sqlite3")
    store.register("Балнұр Кенже", "sample@example.org", "example-strong-pass")
    session = store.login("sample@example.org", "example-strong-pass")
    store.seed_demo(session)
    window = MainWindow(store, session, clock=lambda: datetime(2026, 10, 29, 18))
    window.show()
    app.processEvents()
    yield window
    window.close()
    app.processEvents()
    store.close()


def click(window, caption):
    widget = next(b for b in window.centralWidget().findChildren(QPushButton) if b.text().strip() == caption)
    widget.click()


def test_registry_search_edit_survives_reopening(workspace):
    click(workspace, "Жануарларым")
    current = workspace.centralWidget()
    current.findChild(QLineEdit, "petSearch").setText("Luna")
    grid = current.findChild(QTableWidget, "petRegistry")
    assert grid.rowCount() == 1
    grid.cellWidget(0,5).click()
    workspace.centralWidget().findChild(QLineEdit,"petName").setText("Luna II")
    click(workspace, "Өзгерісті сақтау")
    assert workspace.store.list_pets(workspace.session, query="Luna")[0]["name"] == "Luna II"


def test_adviser_displays_time_from_selected_pet_and_clears_stale_answer(workspace):
    from PySide6.QtWidgets import QComboBox
    click(workspace, "Ақылды көмекші")
    current = workspace.centralWidget()
    click(workspace, "Тамақтандыру тәртібі")
    assert "19:00" in " ".join(t.text() for t in current.findChildren(QLabel))
    current.findChild(QComboBox,"advicePet").setCurrentIndex(2)
    assert "19:00" not in " ".join(t.text() for t in current.findChildren(QLabel))
    click(workspace, "Күтім кестесін қарау")
    assert current.findChild(QLabel,"adviceResult").text()


def test_status_update_refreshes_dashboard(workspace):
    assert workspace.store.stats(workspace.session, workspace.clock().date())["done_count"] == 1
    click(workspace, "Белгілеу")
    assert workspace.store.stats(workspace.session, workspace.clock().date())["done_count"] == 2


def test_delete_needs_confirmation_and_removes_selected_pet(workspace, monkeypatch):
    pet = workspace.store.list_pets(workspace.session, query="Luna")[0]
    workspace.pet_form(pet)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    click(workspace, "Профильді жою")
    assert workspace.store.list_pets(workspace.session, query="Luna")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    click(workspace, "Профильді жою")
    assert workspace.store.list_pets(workspace.session, query="Luna") == []
    assert workspace.centralWidget().findChild(QTableWidget, "petRegistry").rowCount() == 9

