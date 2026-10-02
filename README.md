# Collections Copilot — Adda Wale

A proposed system for the CIBC Collections Hackathon: trusted Customer 360, governed natural-language insights, and grounded agent assist with human review.

Team: Prakhar Gupta, Aryan Shrivastava, Krish Agarwal and Ved Maurya.

**Current phase: system design.** No application or database has been implemented or provisioned. This repository records a reviewable design, not measured results or a production system.

## Design

- [System design](docs/system-design.md)
- [Architecture diagram source](docs/architecture.mmd)
- [Chosen target tables, relationships and metric catalog](docs/data-model.md)
- [Submission requirements](docs/requirements.md)
- [Independent review and decisions](docs/reviews/codex-review.md)
- [Technical references and integration state](docs/technical-evidence.md)

The local submission draft is `submission/Adda Wale_SystemDesign.pdf`: one architecture page, four design pages and a one-page data contract. The source JSON and renderer reproduce it. All data-source field mappings stay TBC until the incoming dataset is profiled.

## Render the submission draft

Use Python 3.10+ with `requirements-pdf.txt` installed in your own virtual environment, then run:

```sh
mkdir -p submission/previews
python scripts/generate_submission.py
pdftoppm -scale-to 1100 -png 'submission/Adda Wale_SystemDesign.pdf' submission/previews/page
```

The renderer verifies six pages, headings and member names. Rendered pages still require visual inspection. Source data, organizer PDFs/text extracts, credentials, local prompts and raw model responses are excluded from the remote repository. In this workspace the renderer libraries are installed under `.venv/libdeps` to avoid altering system packages.

## Engineering agreement

The user supervises. Codex coordinates, verifies and consolidates; Claude Opus 5.5 (high effort) supplies architecture and independent reviews. Feature Dev was used for an initial architect consultation; that plugin subagent used its default Sonnet model. Subsequent reviews ran directly on Opus. File ownership or isolated worktrees will prevent concurrent conflicting edits during the build.

## Status

The supervisor made the GitHub repository public to enable access; original preference was private. Confidential source documents remain local. CockroachDB is proposed, but no CockroachDB plugin connection or database provisioning is established. Data dictionary overview is available; the team has defined its target schema, and incoming field mappings will be confirmed from the dataset. Organizer submission is not performed by this repository setup.

## Verified delivery state

The six-page PDF has passed page-count, heading, member-name, text-boundary and visual checks. Local Git history and reviewed project files have been pushed to `pg1590/cibc-collections-copilot` over SSH after the supervisor added the public authentication key. Source PDFs, local extracts, credentials and raw model responses remain excluded. The generated PDF and portable delivery backups remain local. The GitHub connector previously returned `403 Resource not accessible by integration`; SSH provides the verified upload path. Organizer submission has not been performed.
