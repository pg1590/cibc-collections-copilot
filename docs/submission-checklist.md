# Final submission checklist

Organizer update received on 4 October 2026. All times below are IST. The deadline is **21:00 tonight, with no extension**. The form permits **one submission per team**. The team must coordinate one person to submit after checking every attachment and link.

## Time-sensitive actions

| Time | Action | Current status |
|---|---|---|
| Before 17:00 | Invite GitHub user `cibchack26` to the private repo | Owner confirmed the invitation appears in repository access before the deadline. Acceptance has not been independently checked. |
| 19:00 | Obtain the 15 extra benchmark questions | Awaiting organizer release |
| Before 21:00 | Commit/push the complete benchmark and code, refresh the ZIP and submit once | Pending final questions, video and owner checks; deck prepared, refresh after final run |

Repository: <https://github.com/pg1590/cibc-collections-copilot>.

Owner access settings: <https://github.com/pg1590/cibc-collections-copilot/settings/access>. The owner confirmed the invitation was sent. Keep the repository private and verify acceptance when the organizer accepts. Invitation acceptance remains a separate action by the invitee.

## Required files in GitHub

| Requirement | Repository file | Check |
|---|---|---|
| Code | `app/`, `frontend/`, `scripts/`, `tests/` | Committed with dependency lock files |
| Run instructions, phase 1 changes and AI tool disclosure | `README.md` | Present |
| Architecture PDF or PNG | `docs/architecture-build.pdf`, `docs/architecture-build.png` | Diagram drawn with ReportLab code. No image-generation tool used. |
| C360 contract starting from DC-COLL-001 | `config/c360-contract.yaml` | References the source contract and specifies ownership, schema, rules, refresh and uses |
| Counted quality issues and their handling | `docs/data-quality-report.md` | Generated from measured counts, with handling for each check and unresolved-source limitations |
| Benchmark at the exact required path | `submission/benchmark_answers.csv` | Currently 35 released rows. Final file must also include all 15 extra questions. |

## Form attachments and links

- Repository link above, with organizer access verified.
- Code ZIP backup for the final committed revision. The package builder archives tracked files from HEAD and excludes local datasets, model files, dependencies and secrets.
- A demo video link, **at most five minutes**, on Drive or similar. Use access **Anyone with the link** and verify playback in a signed-out browser. The user will record the demo using `docs/demo-walkthrough.md`.
- Presentation **PDF only**, at most ten slides under the build instructions. Use the PDF in `../deliverables/` after reviewing its current claims.

## Final benchmark and backup commands

After the extra questions arrive, save the actual organizer CSV outside tracked customer data. Run from the repo root:

```bash
.venv/bin/python scripts/run_benchmark.py --extra /absolute/path/extra_questions.csv
.venv/bin/python scripts/package_submission.py --extra /absolute/path/extra_questions.csv --final --check-only
```

Inspect any unresolved results and correct the application, never the generated answer cells. Confirm the header is exactly `question_id,answer,sql_or_sources,refused`, with lower-case true/false and one answer per released/extra question.

Refresh the nine-slide presentation after the benchmark run, then inspect the PDF:

```bash
.venv/bin/python scripts/generate_pitch_pdf.py
```

Output: `../deliverables/AddaWale-Presentation.pdf`. The current deck contains 35 rows and marks the extra release as pending; it must reflect the final run before submission.

Commit and push the final code and generated CSV before the deadline. Then create the matching ZIP:

```bash
.venv/bin/python scripts/package_submission.py --extra /absolute/path/extra_questions.csv --final
```

Default output: `../deliverables/AddaWale-code-backup.zip`. Its neighboring manifest records the commit, question count and SHA-256. A ZIP generated before 19:00 is an interim backup and must be refreshed.

The format/coverage check does not establish hidden-answer correctness. The public numeric development references validate 12 specific questions. See the accuracy audit for known planner and model limits.

## Final review

Verify that the ZIP commit matches the pushed revision, the benchmark contains all 50 unique questions if the release remains 35 plus 15, the video is accessible and within five minutes, and the presentation is a PDF. Recheck the repo collaborator invitation and visibility through the owner account. Complete all fields and attachments before the team's single form submission.
