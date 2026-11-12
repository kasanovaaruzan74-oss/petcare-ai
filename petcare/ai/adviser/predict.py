"""Inference with a frozen decision tree and owner-scoped SQLite records."""
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

ARTIFACT = Path(__file__).with_name("model.json")
FEATURES = ("task_count", "done_count", "overdue_count", "upcoming_count",
            "minutes_until_next", "empty_log")
ACTIONS = {
    "populate": "Күтім жоспарын толықтырыңыз.",
    "review": "Алдағы тапсырманы қараңыз.",
    "reschedule": "Өтіп кеткен тапсырманы қайта жоспарлаңыз.",
}
KIND_ALIASES = {
    "тамақтандыру": "feeding", "ас": "feeding", "food": "feeding", "nutrition": "feeding",
    "ойын": "play", "ойын/белсенділік": "activity", "exercise": "activity",
    "серуен": "walk", "вакцинация": "vaccine", "vaccination": "vaccine",
    "күтім кестесі": "general", "schedule": "general", "care": "general",
}
INTENT_KINDS = {
    "general": None, "feeding": {"feeding"}, "activity": {"play", "walk", "activity"},
    "play": {"play", "activity"}, "walk": {"walk"}, "vaccine": {"vaccine"},
}
FEATURE_LABELS = {
    "task_count": "жазба саны", "done_count": "орындалғаны",
    "overdue_count": "мерзімі өткен тапсырма", "upcoming_count": "алдағы тапсырма",
    "minutes_until_next": "келесі тапсырмаға дейінгі минут",
    "empty_log": "бос журнал белгісі",
}


def normalize_kind(value):
    key = str(value).strip().casefold()
    return KIND_ALIASES.get(key, key)


def feature_values(done, overdue, upcoming, minutes):
    count = done + overdue + upcoming
    return [count, done, overdue, upcoming, minutes, int(count == 0)]


def chronological(entry):
    return entry[0], entry[1]["id"]


@lru_cache(maxsize=1)
def load_model():
    try:
        artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        if artifact["features"] != list(FEATURES) or not artifact["nodes"]:
            raise ValueError("incompatible artifact")
        return artifact
    except (OSError, ValueError, KeyError) as error:
        raise RuntimeError("Күтім моделі жүктелмеді. Модель файлын қайта орнатыңыз.") from error


def traverse(model, values):
    """Return both the predicted class and the feature indices on its decision path."""
    index = 0
    path = []
    for _ in range(len(model["nodes"])):
        node = model["nodes"][index]
        if "action" in node:
            return node["action"], path
        feature = node["feature"]
        path.append(feature)
        index = node["left"] if values[feature] <= node["threshold"] else node["right"]
    raise ValueError("Модель ағашы зақымданған.")


def recommend(store, session, pet_id, intent="general", as_of=None):
    """Use the current owner's selected pet and local civil schedule time."""
    now = as_of if as_of is not None else datetime.now()
    if now.tzinfo is not None:
        raise ValueError("Кестенің жергілікті уақытын уақыт белдеуінсіз енгізіңіз.")
    scope = normalize_kind(intent)
    if scope not in INTENT_KINDS:
        raise ValueError("Сұрақтың күтім санатын нақтылаңыз.")
    pet = next((item for item in store.list_pets(session) if item["id"] == pet_id), None)
    if pet is None:
        raise ValueError("Таңдалған жануар өз тізіміңізден табылмады.")

    allowed = INTENT_KINDS[scope]
    done = 0
    overdue, upcoming = [], []
    for task in store.tasks(session, pet_id=pet_id):
        if allowed is not None and normalize_kind(task["task_type"]) not in allowed:
            continue
        if task["status"] == "done":
            done += 1
            continue
        if task["status"] != "planned":
            raise ValueError("Күтім жазбасының мәртебесі танылмады.")
        stamp = datetime.fromisoformat(task["scheduled_at"])
        bucket = overdue if stamp < now else upcoming
        bucket.append((stamp, task))
    next_task = min(upcoming, key=chronological) if upcoming else None
    minutes = int((next_task[0] - now).total_seconds() // 60) if next_task else -1
    values = feature_values(done, len(overdue), len(upcoming), minutes)
    model = load_model()
    action, path = traverse(model, values)
    chosen = None
    if action == "review":
        chosen = next_task
    elif action == "reschedule" and overdue:
        chosen = min(overdue, key=chronological)
    message = ACTIONS[action]
    evidence = []
    if chosen:
        stamp, task = chosen
        message += f" {task['title']} — {stamp:%d.%m.%Y %H:%M}."
        evidence.append({"task_id": task["id"], "scheduled_at": task["scheduled_at"],
                         "title": task["title"]})

    facts = []
    for feature in dict.fromkeys(path):
        key = FEATURES[feature]
        value = values[feature]
        if key == "minutes_until_next" and value == -1:
            facts.append("алдағы тапсырма тіркелмеген")
        else:
            facts.append(f"{FEATURE_LABELS[key]}: {value}")
    return {
        "model_id": model["model_id"], "model_version": model["model_version"],
        "action": action, "result": message,
        "input_summary": f"{pet['name']} · {now:%d.%m.%Y %H:%M} · "
                         f"тиісті жазба: {values[0]}, орындалғаны: {done}",
        "reason": "Модель шешіміне әсер еткен белгілер: " + "; ".join(facts) + ".",
        "evidence": evidence,
        "limitations": "Оқу деректері синтетикалық. Кеңес тек енгізілген күтім кестесіне сүйенеді.",
    }
