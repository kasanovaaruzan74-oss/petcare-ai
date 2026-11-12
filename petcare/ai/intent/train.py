"""Train and evaluate Aruzhan's Kazakh query classifier from checked-in data."""
import csv
import json
from pathlib import Path

import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

from .predict import MODEL_ID, VERSION, analyze, classify_intent, load_model, score, words

HERE = Path(__file__).parent
LABELS = ("general", "activity", "feeding")


def dataset(name):
    with (HERE / "data" / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_json(path, obj, compact=False):
    options = {"separators": (",", ":")} if compact else {"indent": 2}
    path.write_text(json.dumps(obj, ensure_ascii=False, **options) + "\n", encoding="utf-8")


def main():
    train = dataset("train")
    vectorizer = TfidfVectorizer(analyzer=analyze, max_features=1100)
    inputs = vectorizer.fit_transform([r["text"] for r in train])
    classifier = LogisticRegression(C=8.0, max_iter=500, random_state=42)
    classifier.fit(inputs, [r["intent"] for r in train])
    model = {"model_id": MODEL_ID, "model_version": VERSION, "classes": classifier.classes_.tolist(),
             "vocab": {s: int(i) for s, i in sorted(vectorizer.vocabulary_.items())},
             "idf": vectorizer.idf_.round(8).tolist(), "bias": classifier.intercept_.round(8).tolist(),
             "coef": classifier.coef_.round(8).tolist()}
    write_json(HERE / "model.json", model, compact=True)
    load_model.cache_clear()
    groups = {r["family"] for r in train}
    seen_text = {" ".join(words(r["text"])) for r in train}
    report = {"model_id": MODEL_ID, "version": VERSION, "sklearn": sklearn.__version__,
              "training_rows": len(train), "training_families": len(groups), "suites": {}}
    # Development families used to design rejection are not part of any test suite.
    for development in ("dev_normal", "dev_colloquial", "dev_ambiguous"):
        rows = dataset(development)
        ids = {r["family"] for r in rows}
        texts = {" ".join(words(r["text"])) for r in rows}
        if groups & ids or seen_text & texts:
            raise ValueError(f"Data leakage in {development}")
        groups.update(ids)
        seen_text.update(texts)
    for suite in ("normal", "colloquial", "ambiguous"):
        rows = dataset(suite)
        ids = {r["family"] for r in rows}
        texts = {" ".join(words(r["text"])) for r in rows}
        if groups & ids or seen_text & texts:
            raise ValueError(f"Data leakage in {suite}")
        groups.update(ids)
        seen_text.update(texts)
        outputs = []
        for row in rows:
            expected = classifier.predict_proba(vectorizer.transform([row["text"]]))[0]
            winner, probability = score(row["text"], model)[:2]
            if winner != classifier.classes_[expected.argmax()] or abs(probability - expected.max()) > 1e-6:
                raise RuntimeError("JSON model and scikit-learn disagree")
            inferred = classify_intent(row["text"])
            outputs.append({**row, "actual": inferred["intent"], "reason": inferred["reason"],
                            "confidence": inferred["confidence"]})
        gold = [r["intent"] for r in rows]
        pred = [r["actual"] for r in outputs]
        metrics = {"count": len(rows), "correct": sum(a == b for a, b in zip(gold, pred))}
        if suite == "ambiguous":
            metrics["clarify_rate"] = pred.count("clarify") / len(pred)
        else:
            metrics["macro_f1"] = f1_score(gold, pred, labels=LABELS, average="macro", zero_division=0)
            metrics["errors_by_true_class"] = {label: sum(a == label and a != b for a, b in zip(gold, pred))
                                               for label in LABELS}
        report["suites"][suite] = {**metrics, "predictions": outputs}
        print(suite, metrics)
    write_json(HERE / "evaluation.json", report)


if __name__ == "__main__":
    main()
