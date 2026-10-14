# Local model evaluation

```json
{
  "name": "Financial hardship review triage",
  "version": "c360-financial-v2",
  "algorithm": "class-balanced logistic regression",
  "target": "public note label clear/possible versus none",
  "input_features": [
    "income_loss",
    "income_reduction",
    "income_delay",
    "payment_difficulty",
    "hardship_request",
    "expense_pressure",
    "illness_or_injury",
    "separation",
    "disaster_or_evacuation"
  ],
  "train_rows": 374,
  "test_rows": 126,
  "missing_label_records": 0,
  "split": "Customer-grouped heldout split, seed 1590",
  "heldout": {
    "precision": 1.0,
    "recall": 0.9474,
    "f1": 0.973,
    "balanced_accuracy": 0.9737,
    "confusion_matrix": [
      [
        88,
        0
      ],
      [
        2,
        36
      ]
    ]
  },
  "heldout_rules_only": {
    "precision": 1.0,
    "recall": 1.0,
    "f1": 1.0,
    "balanced_accuracy": 1.0,
    "confusion_matrix": [
      [
        88,
        0
      ],
      [
        0,
        38
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
  "cross_validation": {
    "protocol": "StratifiedGroupKFold(5) by customer, shuffled, seeds [0, 1, 2, 3, 4]; mean/std over 25 folds; pooled counts over all folds",
    "rules_only_definition": "positive when any cue fires",
    "model": {
      "precision": {
        "mean": 0.9795,
        "std": 0.028
      },
      "recall": {
        "mean": 0.9524,
        "std": 0.0341
      },
      "f1": {
        "mean": 0.9652,
        "std": 0.0204
      },
      "balanced_accuracy": {
        "mean": 0.972,
        "std": 0.017
      },
      "pooled": {
        "precision": 0.9789,
        "recall": 0.9521,
        "f1": 0.9653,
        "balanced_accuracy": 0.9718,
        "confusion_matrix": [
          [
            1755,
            15
          ],
          [
            35,
            695
          ]
        ]
      }
    },
    "rules_only": {
      "precision": {
        "mean": 0.9803,
        "std": 0.0269
      },
      "recall": {
        "mean": 1.0,
        "std": 0.0
      },
      "f1": {
        "mean": 0.9899,
        "std": 0.014
      },
      "balanced_accuracy": {
        "mean": 0.9958,
        "std": 0.0057
      },
      "pooled": {
        "precision": 0.9799,
        "recall": 1.0,
        "f1": 0.9898,
        "balanced_accuracy": 0.9958,
        "confusion_matrix": [
          [
            1755,
            15
          ],
          [
            0,
            730
          ]
        ]
      }
    }
  },
  "limitations": [
    "Small synthetic labelled set; no demonstrated production or business uplift.",
    "Cue-only classifier misses unsupported wording, typos and hardship not covered by POL-COLL-004 s4.2 cue phrases.",
    "Cues were designed with error analysis on training notes of the seed-1590 split; CV folds include those notes, so CV is optimistic. See docs/hardship-detector-evaluation.md.",
    "The regularised model can score a note with a single cue below 0.5; serving also flags any cue sentence for review.",
    "Rule cues are binary; score is a review aid, not an eligibility decision.",
    "No protected fields or unrestricted text are model inputs. Fairness groups are evaluation-only.",
    "Low support groups cannot establish fairness."
  ],
  "coefficients": {
    "income_loss": 2.4547,
    "income_reduction": 2.0939,
    "income_delay": 0.5099,
    "payment_difficulty": 3.6997,
    "hardship_request": 3.831,
    "expense_pressure": 2.3976,
    "illness_or_injury": 1.8287,
    "separation": 1.3279,
    "disaster_or_evacuation": 0.6724
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
