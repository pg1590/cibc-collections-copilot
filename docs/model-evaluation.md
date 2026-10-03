# Local model evaluation

```json
{
  "name": "Financial hardship review triage",
  "version": "c360-financial-v1",
  "algorithm": "class-balanced logistic regression",
  "target": "public note label clear/possible versus none",
  "input_features": [
    "income_loss",
    "income_reduction",
    "income_delay",
    "payment_difficulty",
    "hardship_request",
    "expense_pressure"
  ],
  "train_rows": 374,
  "test_rows": 126,
  "missing_label_records": 0,
  "split": "Customer-grouped heldout split, seed 1590",
  "heldout": {
    "precision": 0.8929,
    "recall": 0.6579,
    "f1": 0.7576,
    "balanced_accuracy": 0.8119,
    "confusion_matrix": [
      [
        85,
        3
      ],
      [
        13,
        25
      ]
    ]
  },
  "majority_baseline": {
    "precision": 0.0,
    "recall": 0.0,
    "f1": 0.0,
    "balanced_accuracy": 0.5,
    "confusion_matrix": [
      [
        88,
        0
      ],
      [
        38,
        0
      ]
    ]
  },
  "limitations": [
    "Small synthetic labelled set; no demonstrated production or business uplift.",
    "Financial-cue-only classifier misses unsupported wording and nonfinancial hardship.",
    "Rule cues are binary; score is a review aid, not an eligibility decision.",
    "No protected fields or unrestricted text are model inputs. Fairness groups are evaluation-only.",
    "Low support groups cannot establish fairness."
  ],
  "coefficients": {
    "income_loss": 2.1918,
    "income_reduction": 1.7506,
    "income_delay": 0.616,
    "payment_difficulty": -0.9141,
    "hardship_request": 3.5862,
    "expense_pressure": 0.8878
  }
}
```

Feature parity:
```json
{
  "checked": 100,
  "mismatches": 0
}
```
