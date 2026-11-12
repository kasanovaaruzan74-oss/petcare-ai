"""Compare daily care plans by available time and target care frequency."""
import math


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Жоспар көрсеткіші нақты сан болуы керек.")
    return value


def normalize_plan(plan):
    """Keep the original indicators alongside unitless fits in the range [0, 1]."""
    name = str(plan.get("name") or "").strip()
    if not name:
        raise ValueError("Жоспардың атауын енгізіңіз.")
    raw_keys = ("available_minutes", "required_minutes", "planned_count", "target_count")
    if any(key in plan for key in raw_keys):
        available, required, planned, target = (_number(plan.get(key)) for key in raw_keys)
        if available < 0 or required <= 0 or planned < 0 or target <= 0:
            raise ValueError("Қолжетімді уақыт пен күтім саны теріс болмауы керек. Қажетті уақыт пен мақсат нөлден үлкен болуы тиіс.")
        if not float(planned).is_integer() or not float(target).is_integer():
            raise ValueError("Күтім санын бүтін санмен енгізіңіз.")
        time_fit = min(1.0, available / required)
        frequency_fit = min(1.0, planned / target)
    else:
        time_fit = _number(plan.get("time_fit"))
        frequency_fit = _number(plan.get("frequency_fit"))
        if not (0 <= time_fit <= 1 and 0 <= frequency_fit <= 1):
            raise ValueError("Нормаланған көрсеткіштер 0 мен 1 аралығында болуы керек.")
    return dict(plan, name=name, time_fit=time_fit, frequency_fit=frequency_fit)


def rank_plans(plans, weights=(0.6, 0.4)):
    """Return raw data, normalized fits, weighted points and competition ranks."""
    if len(weights) != 2:
        raise ValueError("Екі салмақ көрсетіңіз.")
    time_weight, frequency_weight = map(_number, weights)
    if min(weights) < 0 or not math.isclose(sum(weights), 1, rel_tol=0, abs_tol=1e-12):
        raise ValueError("Салмақтар теріс болмауы және қосындысы 1 болуы керек.")
    ranked = []
    for plan in plans:
        row = normalize_plan(plan)
        time_points = 100 * time_weight * row["time_fit"]
        frequency_points = 100 * frequency_weight * row["frequency_fit"]
        row.update(time_points=time_points, frequency_points=frequency_points,
                   score=round(time_points + frequency_points, 10))
        ranked.append(row)
    if len(ranked) < 2:
        raise ValueError("Салыстыру үшін кемінде екі жоспар қажет.")
    ranked.sort(key=lambda row: -row["score"])
    for index, row in enumerate(ranked):
        equal_previous = index > 0 and row["score"] == ranked[index - 1]["score"]
        equal_next = index + 1 < len(ranked) and row["score"] == ranked[index + 1]["score"]
        row["rank"] = ranked[index - 1]["rank"] if equal_previous else index + 1
        row["tied"] = equal_previous or equal_next
    return ranked
