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


def test_pet_name_validation_and_added_record_confirmation(workspace):
    click(workspace, "Жануар қосу")
    form = workspace.centralWidget()
    click(workspace, "Сақтау")
    name = form.findChild(QLineEdit, "petName")
    assert name.property("invalid") is True
    assert form.findChild(QLabel, "petFormError").text()
    name.setText("Том")
    assert not name.property("invalid")
    click(workspace, "Сақтау")
    assert "Том" in workspace.centralWidget().findChild(QLabel, "saveNotice").text()
    assert len(workspace.store.list_pets(workspace.session, query="Том")) == 1


def test_natural_question_runs_both_models_and_shows_input_evidence(workspace):
    click(workspace, "Ақылды көмекші")
    chat = workspace.centralWidget()
    chat.findChild(QLineEdit, "adviceQuestion").setText("Келесі тамақтандыру қашан?")
    click(workspace, "Жіберу")
    assert "Тамақтандыру" in chat.findChild(QLabel, "intentCategory").text()
    assert chat.findChild(QLabel, "intentEvidence").text()
    assert "Luna" in chat.findChild(QLabel, "adviceSummary").text()
    assert "19:00" in chat.findChild(QLabel, "adviceResult").text()


def test_all_quick_questions_use_the_classifier_and_clarification_skips_adviser(workspace, monkeypatch):
    from petcare.ui import assistant
    calls = []

    def clarify(query):
        calls.append(query)
        return {"intent": "clarify", "reason": "Тақырыпты нақтылаңыз."}

    def unexpected_advice(*args):
        pytest.fail("Clarification must not produce a care recommendation")

    monkeypatch.setattr(workspace, "classify_intent", clarify)
    monkeypatch.setattr(assistant, "recommend", unexpected_advice)
    click(workspace, "Ақылды көмекші")
    for caption, question in assistant.QUICK_QUESTIONS:
        click(workspace, caption)
        assert calls[-1] == question
    answers = workspace.centralWidget().findChildren(QLabel, "adviceResult")
    assert len(answers) == 3
    assert all("нақтылаңыз" in widget.text() for widget in answers)


def test_model_failure_keeps_entered_question_for_retry(workspace, monkeypatch):
    def failing_model(query):
        raise RuntimeError("private internal details")

    monkeypatch.setattr(workspace, "classify_intent", failing_model)
    click(workspace, "Ақылды көмекші")
    chat = workspace.centralWidget()
    entry = chat.findChild(QLineEdit, "adviceQuestion")
    entry.setText("Келесі тамақтандыру қашан?")
    click(workspace, "Жіберу")
    assert "қайта жіберіңіз" in chat.findChild(QLabel, "adviceError").text()
    assert entry.text() and not chat.findChildren(QLabel, "adviceSummary")


def test_session_logout_and_login_through_normal_form(workspace):
    old = workspace.session
    workspace.sign_out()
    with pytest.raises(ValueError):
        workspace.store.owner(old)
    click(workspace, "Кіру")
    form = workspace.centralWidget()
    assert form.findChild(QLabel, "loginMessage").text()
    form.findChild(QLineEdit, "loginEmail").setText("sample@example.org")
    form.findChild(QLineEdit, "loginPassword").setText("example-strong-pass")
    click(workspace, "Кіру")
    assert workspace.session != old and workspace.store.owner(workspace.session)
    assert "Негізгі бет" in {b.text().strip() for b in workspace.centralWidget().findChildren(QPushButton)}


def test_signup_and_reset_forms_use_store_and_delivery_callback(workspace, monkeypatch):
    from petcare import mail
    from petcare.ui.widgets import Form

    workspace.sign_out()
    email = "new-owner@example.org"
    sent_codes = []
    monkeypatch.setattr(mail, "send_reset_code", lambda recipient, code: sent_codes.append((recipient, code)))

    def complete_signup(form):
        fields = form.findChildren(QLineEdit)
        for widget, value in zip(fields, ["Аружан", email, "sample-pass-1234", "sample-pass-1234"]):
            widget.setText(value)
        next(b for b in form.findChildren(QPushButton) if b.text() == "Аккаунт ашу").click()
        return form.result()

    monkeypatch.setattr(Form, "exec", complete_signup)
    click(workspace, "Аккаунт ашу")
    assert workspace.centralWidget().findChild(QLineEdit, "loginEmail").text() == email

    def complete_reset(form):
        address, code_box, new_password = form.findChildren(QLineEdit)
        address.setText(email)
        next(b for b in form.findChildren(QPushButton) if b.text() == "Код жіберу").click()
        assert sent_codes[0][0] == email
        code_box.setText(sent_codes[0][1])
        new_password.setText("replacement-pass-1234")
        next(b for b in form.findChildren(QPushButton) if b.text() == "Құпиясөзді жаңарту").click()
        return form.result()

    monkeypatch.setattr(Form, "exec", complete_reset)
    click(workspace, "Құпиясөзді ұмыттым")
    form = workspace.centralWidget()
    form.findChild(QLineEdit, "loginPassword").setText("replacement-pass-1234")
    click(workspace, "Кіру")
    assert workspace.store.profile(workspace.session)["email"] == email

