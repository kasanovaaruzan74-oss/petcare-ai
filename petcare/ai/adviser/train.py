"""Rebuild the portable tree and evaluation results from versioned synthetic records."""
import csv
import json
from pathlib import Path

import sklearn
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.tree import DecisionTreeClassifier

from .predict import ACTIONS, FEATURES, feature_values, traverse

HERE = Path(__file__).parent
LABELS = ["populate", "review", "reschedule"]
SEED = 42


def read_set(filename):
    with (HERE / "data" / filename).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def features(row):
    return feature_values(*(int(row[key]) for key in
                            ("done", "overdue", "upcoming", "minutes_until_next")))


def tree_nodes(estimator):
    nodes = []
    tree = estimator.tree_
    for i in range(tree.node_count):
        if tree.children_left[i] == tree.children_right[i]:
            nodes.append({"action": str(estimator.classes_[tree.value[i][0].argmax()])})
        else:
            nodes.append({"feature": int(tree.feature[i]), "threshold": float(tree.threshold[i]),
                          "left": int(tree.children_left[i]), "right": int(tree.children_right[i])})
    return nodes


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    train = read_set("train.csv")
    suites = ["upcoming_cats", "overdue_dogs", "empty_rabbits", "species_swap"]
    groups = {row["pet_id"] for row in train}
    estimator = DecisionTreeClassifier(max_depth=3, random_state=SEED)
    estimator.fit([features(row) for row in train], [row["expected"] for row in train])
    model = {"model_id": "balnur-care-tree", "model_version": "1.0",
             "features": list(FEATURES), "nodes": tree_nodes(estimator)}
    metrics = {"scikit_learn": sklearn.__version__, "seed": SEED,
               "training_records": len(train), "training_pets": len(groups),
               "labels": LABELS, "suites": {}}
    expected, predicted = [], []
    for suite in suites:
        cases = read_set(suite + ".csv")
        ids = {row["pet_id"] for row in cases}
        if groups.intersection(ids):
            raise ValueError(f"Pet identity reused between datasets: {suite}")
        groups.update(ids)
        results = []
        for row in cases:
            x = features(row)
            action, path = traverse(model, x)
            if action != estimator.predict([x])[0]:
                raise RuntimeError("Exported tree differs from fitted estimator")
            results.append({"pet_id": row["pet_id"], "expected": row["expected"], "predicted": action,
                            "path_values": {FEATURES[i]: x[i] for i in path},
                            "recommendation": ACTIONS[action]})
            expected.append(row["expected"])
            predicted.append(action)
        correct = sum(item["predicted"] == item["expected"] for item in results)
        metrics["suites"][suite] = {"correct": correct, "count": len(results), "cases": results}
    metrics["macro_f1"] = f1_score(expected, predicted, labels=LABELS, average="macro", zero_division=0)
    metrics["confusion_matrix"] = confusion_matrix(expected, predicted, labels=LABELS).tolist()
    save(HERE / "model.json", model)
    save(HERE / "evaluation.json", metrics)
    print(f"Depth {estimator.get_depth()}, held out {len(predicted)}, macro-F1 {metrics['macro_f1']:.3f}")
    print(metrics["confusion_matrix"])


if __name__ == "__main__":
    main()
