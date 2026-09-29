# Training data

`data/processed/models.pkl` contains only the fitted models. The rows they learned from are here.
All files are UTF-8 CSV and open directly in Excel.

| File | Rows | What it is |
|---|---|---|
| `incidents_unified_full.csv` | 46,756 | The final merged dataset (Source A text-rich + Source B event log), all 76 columns. |
| `train_resolution_time.csv` | 44,826 | Resolution-time model. Features known when a ticket opens; target `resolution_hours`. Time-based split: earliest 80% `train`, latest 20% `test`. |
| `train_fix_accuracy.csv` | 44,826 | Fix-accuracy model. Features known at resolution; target `reopened` (1 = reopened). Stratified random 80/20 split. |
| `train_text_classifiers.csv` | 3,129 | Text classifiers (TF-IDF + logistic regression). `text` is the title and description; one `<task>_label` and `<task>_split` column pair per task. |

In `train_text_classifiers.csv`, `<task>_split = not used` means the row has no label for that task or its
class had fewer than 5 examples. Priority, impact and urgency labels exist only for Source B rows.

Caveats stated by the training code: Source B text is synthetic and was conditioned on these fields, so text
classifier scores are optimistic relative to real free text. Reopened labels come from the real `Reopen_Time`.

Regenerate with `python scripts/export_training_data.py`.
