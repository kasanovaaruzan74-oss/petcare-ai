"""Aruzhan's decision method, reminder selection, history and report formats."""
from datetime import datetime
import json

import pytest

from petcare.db import Store
from petcare.db.auth import normalized_email
from petcare.services.reports import save_report
from petcare.services.scoring import rank_plans


def raw(name, minutes, count):
    return dict(name=name, available_minutes=30, required_minutes=minutes, planned_count=count, target_count=2)


def test_decision_method_discloses_components_and_ties():
    ranked = rank_plans([raw("A", 30, 1), raw("B", 60, 2), raw("C", 15, 1)])
    assert [p["name"] for p in ranked] == ["A", "C", "B"]
    assert [(p["rank"], p["tied"]) for p in ranked] == [(1, True), (1, True), (3, False)]
    assert [(p["time_fit"], p["frequency_fit"], p["time_points"], p["frequency_points"], p["score"])
            for p in ranked] == [(1, .5, 60, 20, 80), (1, .5, 60, 20, 80), (.5, 1, 30, 40, 70)]
    assert ranked[0]["available_minutes"] == 30 and ranked[-1]["required_minutes"] == 60
    assert rank_plans([raw("A", 10, 10), raw("B", 60, 0)], weights=(0, 1))[0]["score"] == 100
    normalized = [{"name": "A", "time_fit": 1, "frequency_fit": .5},
                  {"name": "B", "time_fit": .5, "frequency_fit": 1}]
    assert [plan["score"] for plan in rank_plans(normalized)] == [80, 70]
    close = [dict(raw("A", 1439, 1), available_minutes=1), dict(raw("B", 1440, 1), available_minutes=1)]
    assert [plan["rank"] for plan in rank_plans(close)] == [1, 2]


def test_decision_rejects_invalid_input():
    with pytest.raises(ValueError):
        rank_plans([raw("A", 1, 1)])
    for invalid in [raw("A", 0, 2), raw("A", 45, -1), raw("A", 20, 1.5),
                    {"name": "A", "time_fit": float("nan"), "frequency_fit": 1}]:
        with pytest.raises(ValueError):
            rank_plans([invalid, raw("B", 15, 1)])
    with pytest.raises(ValueError):
        rank_plans([raw("A", 1, 1), raw("B", 2, 2)], (.6, .6))


@pytest.fixture
def account(tmp_path):
    store = Store(tmp_path / "account.db")
    try:
        store.register("Аружан", "a@example.test", "test-password")
        session = store.login("a@example.test", "test-password")
        store.seed_demo(session)
        yield store, session
    finally:
        store.close()


def test_reminders_include_both_boundaries_and_exclude_other_owners(account):
    store, session = account
    start = datetime(2026, 10, 29, 19)
    end = datetime(2026, 11, 2, 10)
    assert [r["title"] for r in store.reminders(session, start, end)] == ["Кешкі ас", "Вакцинация"]
    vaccines = store.reminders(session, start, task_type="vaccine")
    assert len(vaccines) == 2
    store.complete_task(session, vaccines[0]["id"])
    assert store.reminders(session, start, end, task_type="vaccination") == []
    store.register("Басқа", "other@example.test", "test-password")
    other = store.login("other@example.test", "test-password")
    assert store.reminders(other, start) == []
    with pytest.raises(ValueError):
        store.reminders(session, end, start)
    store.logout(session)
    with pytest.raises(ValueError):
        store.reminders(session, start)


def test_pet_search_history_and_json_export(account):
    store, session = account
    pet = store.list_pets(session, query="lUnA")[0]
    store.save_pet(session, {"breed": "Британдық"}, pet["id"])
    assert [r["name"] for r in store.list_pets(session, "РИТАН", "МЫСЫҚ", "breed")] == ["Luna"]
    assert store.search_pets(session, "luna", {"species": "мысық", "breed": "британдық"})[0]["id"] == pet["id"]
    species = [r["species"].casefold() for r in store.list_pets(session, sort="species")]
    assert species == sorted(species)
    history = store.history(session, "өЗгерТІлді")
    day = datetime.fromisoformat(history[0]["created_at"]).astimezone().strftime("%d.%m.%Y")
    assert history[0] in store.history(session, day)
    data = json.loads(store.export_report(session, "2026-11-01", "2026-11-08", file_format="json"))
    assert [r["Жануар"] for r in data] == ["Luna", "Barney"]
    with pytest.raises(ValueError):
        store.export_report(session, file_format="unknown")


def test_save_failure_preserves_target_and_removes_partial_file(tmp_path, monkeypatch):
    from pathlib import Path

    target = tmp_path / "report.csv"
    target.write_bytes(b"previous")

    def fail(source, destination):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(ValueError, match="сақталмады"):
        save_report(target, b"new", "csv")
    assert target.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("value", ["x@example.org,y@example.org", "A <name@example.org>", "x@example.org\nBcc:hello@example.org"])
def test_email_fields_accept_a_single_mailbox(value):
    with pytest.raises(ValueError):
        normalized_email(value)
