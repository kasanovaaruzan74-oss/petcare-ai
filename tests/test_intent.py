import json
from datetime import datetime

import pytest

from petcare.ai.adviser import recommend
from petcare.ai.intent import classify_intent
from petcare.ai.intent import predict
from petcare.db import Store


@pytest.mark.parametrize(("text", "topic"), [
    ("Күтім кестесінде қандай әрекет бар?", "general"),
    ("Қашан серуендейміз?", "activity"),
    ("Келесі тамақтандыру қашан?", "feeding"),
    ("Luna үшін күнделікті күтімді қалай жоспарлаймын?", "general"),
    ("Luna-ны бүгін неше рет тамақтандырамын?", "feeding"),
])
def test_chat_routes_and_literal_evidence(text, topic):
    result = classify_intent(text)
    assert result["intent"] == result["result"] == topic
    assert result["input_summary"] == text
    assert result["evidence"] and all(word in text for word in result["evidence"])
    assert 0 <= result["confidence"] <= 1
    assert all(result[k] for k in ("reason", "model_id", "model_version", "limitations"))


@pytest.mark.parametrize("text", ["Ол ше?", "???", "", "Құпиясөзді қалай өзгертемін?",
                                  "Жем беру ме әлде серуенге шығу ма?"])
def test_unclear_unsupported_and_mixed_questions(text):
    assert classify_intent(text)["intent"] == "clarify"


@pytest.mark.parametrize("text", ["Мысық тамақтан соң құсып жатыр", "Итке дәріні қашан беремін?",
                                  "Вакцина мерзімі қай күнге келеді?"])
def test_health_topic_supersedes_care_routing(text):
    result = classify_intent(text)
    assert result["intent"] == "clarify"
    assert "ветеринар" in result["reason"] and result["evidence"] == []


def test_actual_database_flows_from_question_to_specific_journal_row(tmp_path):
    store = Store(tmp_path / "test.sqlite")
    try:
        store.register("Демо", "demo@example.test", "DemoPassword123!")
        owner = store.login("demo@example.test", "DemoPassword123!")
        store.seed_demo(owner)
        luna = next(p for p in store.list_pets(owner) if p["name"] == "Luna")
        question = classify_intent("Luna-ны бүгін неше рет тамақтандырамын?")
        advice = recommend(store, owner, luna["id"], question["intent"], datetime(2026, 10, 29, 18))
        assert advice["model_id"] != question["model_id"]
        assert advice["evidence"][0]["title"] == "Кешкі ас" and "19:00" in advice["result"]
    finally:
        store.close()


def test_committed_report_matches_shipped_model():
    report = json.loads((predict.HERE / "evaluation.json").read_text(encoding="utf-8"))
    for suite in report["suites"].values():
        for row in suite["predictions"]:
            result = classify_intent(row["text"])
            assert (row["actual"], row["confidence"]) == (result["intent"], result["confidence"])


def test_missing_artifact_has_readable_error(monkeypatch, tmp_path):
    predict.load_model.cache_clear()
    monkeypatch.setattr(predict, "HERE", tmp_path)
    with pytest.raises(RuntimeError, match="Сұрақ моделін"):
        classify_intent("Келесі тамақтандыру қашан?")
