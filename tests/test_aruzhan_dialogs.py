"""Verify the comparison, reminder and save dialogs through real Qt controls."""
import os
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QFileDialog, QPlainTextEdit, QPushButton, QTableWidget

from petcare.db import Store
from petcare.services.scoring import rank_plans
from petcare.ui import MainWindow, dialogs


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    store = Store(":memory:")
    store.register("Аружан", "a@example.test", "test-password")
    session = store.login("a@example.test", "test-password")
    store.seed_demo(session)
    win = MainWindow(store, session, clock=lambda: datetime(2026, 10, 29, 18), rank_plans=rank_plans)
    yield win
    win.close()
    app.processEvents()
    store.close()


def test_comparison_supports_third_plan_and_displays_equal_leaders(window, monkeypatch):
    def use(dialog):
        results = dialog.findChild(QPlainTextEdit, "planScores")
        assert "80/100" in results.toPlainText() and "70/100" in results.toPlainText()
        assert "0.50 × 40 = 20.00" in results.toPlainText()
        next(b for b in dialog.findChildren(QPushButton) if "Жоспар қосу" in b.text()).click()
        grid = dialog.findChild(QTableWidget, "planInputs")
        assert grid.rowCount() == 3
        assert "Тең нәтиже — А жоспары, №3 жоспар" in results.toPlainText()
        grid.cellWidget(2, 2).setValue(2)
        assert "Ұсынылған жоспар — №3 жоспар" in results.toPlainText()
        return 0

    monkeypatch.setattr(QDialog, "exec", use)
    dialogs.compare(window)


def test_export_changes_preview_and_writes_selected_file(window, monkeypatch, tmp_path):
    target = tmp_path / "жоспар"
    notices = []
    monkeypatch.setattr(window, "notice", notices.append)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), "JSON (*.json)"))

    def use(dialog):
        formats = dialog.findChild(QComboBox, "reportFormat")
        preview = dialog.findChild(QPlainTextEdit, "reportPreview")
        assert preview.toPlainText().startswith("Жануар,")
        formats.setCurrentIndex(formats.findData("json"))
        assert preview.toPlainText().startswith("[")
        next(b for b in dialog.findChildren(QPushButton) if b.text() == "Файлды сақтау").click()
        data = target.with_suffix(".json").read_bytes()
        assert data == window.store.export_report(window.session, file_format="json")
        assert data.decode() == preview.toPlainText()
        return 0

    monkeypatch.setattr(QDialog, "exec", use)
    dialogs.export(window)
    assert len(notices) == 1


def test_reminder_window_updates_selected_period(window, monkeypatch):
    def use(dialog):
        grid = dialog.findChild(QTableWidget)
        assert grid.rowCount() == 1 and grid.item(0, 1).text() == "Luna"
        dialog.findChild(QComboBox).setCurrentIndex(2)
        assert grid.rowCount() == 3 and grid.item(2, 1).text() == "Barney"
        return 0

    monkeypatch.setattr(QDialog, "exec", use)
    dialogs.reminders(window)
