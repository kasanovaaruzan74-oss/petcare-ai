from datetime import datetime

import pytest

from petcare.ai.adviser import recommend

NOW = datetime(2026, 10, 29, 18, 0)


class ExampleStore:
    """The caller is allowed to view only Luna. Tasks arrive in unsorted order."""
    def __init__(self, rows=()):
        self.rows = rows

    def list_pets(self, session):
        assert session == "owner"
        return [{"id": 8, "name": "Luna", "species": "Мысық"}]

    def tasks(self, session, pet_id):
        assert session == "owner" and pet_id == 8
        return self.rows


def task(identifier, hour, kind="feeding", status="planned"):
    return {"id": identifier, "title": f"Тапсырма {identifier}", "task_type": kind,
            "status": status, "scheduled_at": f"2026-10-29T{hour}:00"}


def test_next_meal_comes_from_selected_journal():
    store = ExampleStore([task(2, "22:00"), task(3, "13:00", "walk"), task(1, "19:00", "Тамақтандыру")])
    advice = recommend(store, "owner", 8, "feeding", NOW)
    assert advice["action"] == "review"
    assert advice["evidence"] == [{"task_id": 1, "title": "Тапсырма 1",
                                   "scheduled_at": "2026-10-29T19:00:00"}]
    assert "19:00" in advice["result"] and "Luna" in advice["input_summary"]


def test_unfinished_overdue_takes_priority_and_done_is_ignored():
    tasks = [task(1, "08:00", status="done"), task(4, "12:00"), task(2, "17:00"), task(5, "19:00")]
    advice = recommend(ExampleStore(tasks), "owner", 8, "general", NOW)
    assert advice["action"] == "reschedule"
    assert advice["evidence"][0]["task_id"] == 4
    assert "мерзімі өткен" in advice["reason"]


@pytest.mark.parametrize("rows", [[], [task(1, "08:00", status="done")], [task(2, "18:00", "play")]])
def test_empty_relevant_plan_never_fabricates_an_entry(rows):
    advice = recommend(ExampleStore(rows), "owner", 8, "feeding", NOW)
    assert advice["action"] == "populate" and not advice["evidence"]


def test_at_current_time_is_an_upcoming_task():
    advice = recommend(ExampleStore([task(1, "18:00", "Серуен")]), "owner", 8, "activity", NOW)
    assert advice["action"] == "review"


def test_access_and_unknown_intent():
    with pytest.raises(ValueError, match="тізіміңізден"):
        recommend(ExampleStore(), "owner", 99, "general", NOW)
    with pytest.raises(ValueError, match="нақтылаңыз"):
        recommend(ExampleStore(), "owner", 8, "unknown", NOW)


def test_owner_scoped_sqlite_demo(tmp_path):
    from petcare.db import Store

    store = Store(tmp_path / "pets.sqlite")
    try:
        store.register("Балнұр", "balnur@example.test", "ExamplePass123!")
        session = store.login("balnur@example.test", "ExamplePass123!")
        store.seed_demo(session)
        ids = {r["name"]: r["id"] for r in store.list_pets(session)}
        for pet, intent, action in (("Luna", "feeding", "review"),
                                    ("Charlie", "walk", "reschedule"),
                                    ("Moti", "general", "populate")):
            assert recommend(store, session, ids[pet], intent, NOW)["action"] == action
        store.register("Екінші", "other@example.test", "AnotherPass123!")
        other = store.login("other@example.test", "AnotherPass123!")
        with pytest.raises(ValueError, match="тізіміңізден"):
            recommend(store, other, ids["Luna"], "feeding", NOW)
    finally:
        store.close()
