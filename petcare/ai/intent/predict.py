"""Portable inference for an exported TF-IDF and multinomial logistic regression."""
from collections import Counter
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import unicodedata

HERE = Path(__file__).parent
MODEL_ID = "aruzhan-kz-care-intent"
VERSION = "1.0"
NAMES = {"general": "Күтім кестесі", "activity": "Ойын және белсенділік",
         "feeding": "Тамақтандыру", "clarify": "Нақтылау"}
LIMITATIONS = "Модель күнделікті күтім туралы үш тақырыптағы оқу мысалдарымен үйретілген."
# This boundary is applied before model routing. A classifier cannot assess health.
CLINICAL = re.compile(
    r"диагноз|дозиров|антибиот|вакцин|екпе|ауырып|ауырад|ауырсын|"
    r"улан|ауру|кусып|кусу|кусты|кызуы|кан кет|таблет|дари|"
    r"миллиграм|\bмг\b|дармек|емдеу|жаракат|жаралан|тыныс ал|"
    r"диаре|жотел|аксап|аксайды|талма|симптом|болезн|рвот|отрав|лекар|температур"
)
# Require a reference to the app's scope before routing. These stems admit
# topics; only the trained classifier selects one of the three routes.
SCOPE = re.compile(
    r"\b(?:кутим|кесте|план|жоспар|кунтизбе|тапсырма|миндет|еске сал|"
    r"кун тартиб|шаруа|истер|белсенди|серуен|кыдыр|жаттыгу|жаттыгы|"
    r"ойын|ойна|доп|кимыл|козгалыс|аулага|далага|сыртка|таза ауа|"
    r"тамак|тамаг|корек|азык|азыг|жем|асты|астан|аска|асын|ас\b)"
)
# Shared spelling normalization lets unaccented keyboard input use the same terms.
FOLD = str.maketrans("әқғңөұүһі", "акгноуухи")


def words(text):
    normalized = unicodedata.normalize("NFC", text).casefold().translate(FOLD)
    return re.findall(r"[^\W_]+", normalized, re.UNICODE)


def word_grams(word):
    padded = " " + word + " "
    for size in (2, 3, 4):
        for i in range(len(padded) - size + 1):
            yield padded[i:i + size]


def analyze(text):
    return [gram for word in words(text) for gram in word_grams(word)]


@lru_cache(maxsize=1)
def load_model():
    try:
        model = json.loads((HERE / "model.json").read_text(encoding="utf-8"))
        if model["model_id"] != MODEL_ID or model["model_version"] != VERSION:
            raise ValueError("incompatible model")
        return model
    except (OSError, KeyError, ValueError) as exc:
        raise RuntimeError("Сұрақ моделін ашу мүмкін болмады.") from exc


def score(text, model):
    tokens = words(text)
    vocab = model["vocab"]
    terms = analyze(text)
    counts = Counter(vocab[gram] for gram in terms if gram in vocab)
    tfidf = {i: count * model["idf"][i] for i, count in counts.items()}
    norm = math.sqrt(sum(weight * weight for weight in tfidf.values())) or 1
    weights = {i: weight / norm for i, weight in tfidf.items()}
    logits = [bias + sum(weight * coefficients[i] for i, weight in weights.items())
              for bias, coefficients in zip(model["bias"], model["coef"])]
    peak = max(logits)
    unscaled = [math.exp(value - peak) for value in logits]
    total = sum(unscaled)
    probabilities = [v / total for v in unscaled]
    order = sorted(range(len(logits)), key=logits.__getitem__, reverse=True)
    winner, runner_up = order[:2]
    # Attribute the fitted logit difference to the original words in the question.
    cues = []
    strong = set()
    for token in dict.fromkeys(tokens):
        per_word = Counter(vocab[g] for g in word_grams(token) if g in vocab)
        scores = [sum(count * model["idf"][i] * coefs[i] / norm
                      for i, count in per_word.items()) for coefs in model["coef"]]
        contribution = scores[winner] - scores[runner_up]
        if contribution > 0.045 and len(token) >= 2:
            cues.append((contribution, token))
        ranked = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
        if scores[ranked[0]] - scores[ranked[1]] > 0.28:
            strong.add(model["classes"][ranked[0]])
    cues.sort(reverse=True)
    coverage = sum(counts.values()) / max(1, len(terms))
    return (model["classes"][winner], probabilities[winner], probabilities[runner_up],
            coverage, [token for _, token in cues[:2]], strong)


def classify_intent(question):
    if not isinstance(question, str):
        raise ValueError("Сұрақты мәтін түрінде енгізіңіз.")
    model = load_model()
    question = question.strip()
    normalized = " ".join(words(question))
    intent, confidence, second, coverage, cues, strong = score(question, model)
    mixed = {"feeding", "activity"}.issubset(strong) and any(
        word in normalized.split() for word in ("алде", "жане", "немесе", "ме", "ма")
    )
    if CLINICAL.search(normalized):
        intent, cues = "clarify", []
        reason = "Бұл сұрақ жануар денсаулығына қатысты. Денсаулық мәселесін ветеринармен талқылаңыз."
    elif mixed:
        intent = "clarify"
        reason = "Сұрақта тамақтандыру мен белсенділік қатар кездеседі. Біреуін таңдаңыз."
    elif (not SCOPE.search(normalized) or confidence < 0.52 or confidence - second < 0.14
          or coverage < 0.22 or not cues):
        intent, cues = "clarify", []
        reason = "Күтім кестесі, тамақтандыру немесе ойын туралы нақты сұрақ қойыңыз."
    # Return literal words for UI highlighting, retaining the user's spelling.
    originals = re.findall(r"[^\W_]+", unicodedata.normalize("NFC", question), re.UNICODE)
    literal = {w.casefold().translate(FOLD): w for w in originals}
    cues = [literal.get(cue, cue) for cue in cues]
    if intent != "clarify":
        reason = f"Санат — {NAMES[intent]}. Модельге әсер еткен сөздер: {', '.join(cues)}."
    return {"intent": intent, "result": intent, "reason": reason, "evidence": cues,
            "confidence": round(confidence, 4), "input_summary": question,
            "model_id": MODEL_ID, "model_version": VERSION, "limitations": LIMITATIONS}
