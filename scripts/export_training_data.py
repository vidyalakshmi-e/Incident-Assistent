"""Export the exact rows the triage models were trained on, so they can be opened in Excel or a notebook.

`data/processed/models.pkl` holds only the fitted models, never their data. This script re-applies the
filters, feature builders and train/test splits of backend/evaluation/train_models.py and writes:

  data/training/incidents_unified_full.csv    the final merged dataset (every row, every column)
  data/training/train_resolution_time.csv     rows + features + target of the resolution-time model
  data/training/train_fix_accuracy.csv        rows + features + target of the fix-accuracy (reopen) model
  data/training/train_text_classifiers.csv    text + labels of the category/priority/impact/urgency classifiers
  data/training/README.md                     what each file is

The train/test row counts are asserted against the counts stored inside models.pkl, so the export cannot
silently drift from what was trained.

Usage: python scripts/export_training_data.py
"""
from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from backend.config.settings import get_settings  # noqa: E402
from backend.evaluation.train_models import SEED  # noqa: E402
from backend.services.triage import OPEN_FEATURES, RESOLVE_FEATURES, open_frame, resolve_frame  # noqa: E402

ENC = "utf-8-sig"  # BOM so Excel opens the CSV as UTF-8


def resolution_time_rows(unified: pd.DataFrame) -> pd.DataFrame:
    df = unified[(unified["source"] == "B_event_log") & unified["resolution_hours"].notna()
                 & (unified["resolution_hours"] >= 0)].sort_values("open_time")
    out = pd.concat([df[["incident_id", "open_time"]].reset_index(drop=True),
                     open_frame(df).reset_index(drop=True)], axis=1)
    out["resolution_hours"] = df["resolution_hours"].to_numpy()
    out["target_log1p_hours"] = np.log1p(df["resolution_hours"].to_numpy())
    cut = int(len(df) * 0.8)  # time-based split: earlier 80% train, latest 20% test
    out["split"] = np.where(np.arange(len(df)) < cut, "train", "test")
    return out[["incident_id", "split", "open_time", *OPEN_FEATURES, "resolution_hours", "target_log1p_hours"]]


def fix_accuracy_rows(unified: pd.DataFrame) -> pd.DataFrame:
    df = unified[(unified["source"] == "B_event_log") & unified["resolution_hours"].notna()].copy()
    X, y = resolve_frame(df), df["reopened"].astype(int).to_numpy()
    idx = np.arange(len(df))
    _, _, _, _, itr, _ = train_test_split(X, y, idx, test_size=0.2, random_state=SEED, stratify=y)
    out = X.reset_index(drop=True)
    out.insert(0, "incident_id", df["incident_id"].to_numpy())
    out.insert(1, "split", np.where(np.isin(idx, itr), "train", "test"))
    out["reopened"] = y
    return out[["incident_id", "split", *RESOLVE_FEATURES, "reopened"]]


def text_classifier_rows(kb: pd.DataFrame) -> pd.DataFrame:
    text = (kb["title"].fillna("") + ". " + kb["description"].fillna("")).to_numpy()
    out = pd.DataFrame({"incident_id": kb["incident_id"].to_numpy(), "source": kb["source"].to_numpy(), "text": text})
    b = (kb["source"] == "B_event_log").to_numpy()
    labels = {"category": kb["category"].astype(str).to_numpy()}
    for f in ("priority", "impact", "urgency"):
        lab = kb[f].astype(str).to_numpy()
        labels[f] = np.where(b & (lab != "Not Set"), lab, None)
    for name, lab in labels.items():
        mask = pd.notna(lab)
        idx = np.arange(len(kb))[mask]
        y = lab[mask].astype(str)
        counts = pd.Series(y).value_counts()
        keep = np.isin(y, counts[counts >= 5].index)  # classes with < 5 examples are dropped from training
        idx, y = idx[keep], y[keep]
        _, _, _, _, itr, _ = train_test_split(text[idx], y, idx, test_size=0.25, random_state=SEED, stratify=y)
        split = np.full(len(kb), "not used", dtype=object)
        split[idx] = "test"
        split[itr] = "train"
        out[f"{name}_label"] = np.where(split != "not used", lab, None)
        out[f"{name}_split"] = split
    return out


def check_counts(name: str, rows: pd.DataFrame, split_col: str, want: dict) -> None:
    got = {"n_train": int((rows[split_col] == "train").sum()), "n_test": int((rows[split_col] == "test").sum())}
    assert got == {"n_train": want["n_train"], "n_test": want["n_test"]}, f"{name}: export {got} != trained {want}"
    print(f"  ok  {name}: train {got['n_train']:,} / test {got['n_test']:,} (matches models.pkl)")


README = """# Training data

`data/processed/models.pkl` contains only the fitted models. The rows they learned from are here.
All files are UTF-8 CSV and open directly in Excel.

| File | Rows | What it is |
|---|---|---|
| `incidents_unified_full.csv` | {n_unified:,} | The final merged dataset (Source A text-rich + Source B event log), all {c_unified} columns. |
| `train_resolution_time.csv` | {n_rt:,} | Resolution-time model. Features known when a ticket opens; target `resolution_hours`. Time-based split: earliest 80% `train`, latest 20% `test`. |
| `train_fix_accuracy.csv` | {n_fx:,} | Fix-accuracy model. Features known at resolution; target `reopened` (1 = reopened). Stratified random 80/20 split. |
| `train_text_classifiers.csv` | {n_tx:,} | Text classifiers (TF-IDF + logistic regression). `text` is the title and description; one `<task>_label` and `<task>_split` column pair per task. |

In `train_text_classifiers.csv`, `<task>_split = not used` means the row has no label for that task or its
class had fewer than 5 examples. Priority, impact and urgency labels exist only for Source B rows.

Caveats stated by the training code: Source B text is synthetic and was conditioned on these fields, so text
classifier scores are optimistic relative to real free text. Reopened labels come from the real `Reopen_Time`.

Regenerate with `python scripts/export_training_data.py`.
"""


if __name__ == "__main__":
    s = get_settings()
    unified = pd.read_parquet(s.processed_dir / "incidents_unified.parquet")
    kb = pd.read_parquet(s.processed_dir / "kb_records.parquet")
    with (s.processed_dir / "models.pkl").open("rb") as fh:
        bundle = pickle.load(fh)

    out_dir = Path(s.processed_dir).parent / "training"
    out_dir.mkdir(parents=True, exist_ok=True)

    rt, fx, tx = resolution_time_rows(unified), fix_accuracy_rows(unified), text_classifier_rows(kb)
    print("Checking the export against models.pkl:")
    check_counts("resolution_time", rt, "split", bundle["resolution_time"]["test_metrics"])
    check_counts("fix_accuracy", fx, "split", bundle["fix_accuracy"]["test_metrics"])
    for task, m in bundle["text_classifier_metrics"].items():
        check_counts(f"text:{task}", tx, f"{task}_split", m)

    unified.to_csv(out_dir / "incidents_unified_full.csv", index=False, encoding=ENC)
    rt.to_csv(out_dir / "train_resolution_time.csv", index=False, encoding=ENC)
    fx.to_csv(out_dir / "train_fix_accuracy.csv", index=False, encoding=ENC)
    tx.to_csv(out_dir / "train_text_classifiers.csv", index=False, encoding=ENC)
    (out_dir / "README.md").write_text(README.format(
        n_unified=len(unified), c_unified=unified.shape[1], n_rt=len(rt), n_fx=len(fx), n_tx=len(tx)), encoding="utf-8")
    print(f"Wrote {out_dir}")
    for p in sorted(out_dir.iterdir()):
        print(f"  {p.name:36} {p.stat().st_size / 1e6:8.1f} MB")
