# CIBC Collections Hackathon

## Source precedence
- Current problem statement: parent folder's CIBC Collections Hackathon Problem Statement.pdf; extracted at docs/sources/problem-statement.txt.
- Supplementary challenge deck: parent folder's collection hackathon.pdf; extracted at docs/sources/challenge-brief.txt. Its judging criteria differ and must not override tonight's rubric.
- Announcement image gives a 21:00 design deadline, conflicting with the current problem statement's 23:00 deadline. Aim for supervisor review by 21:00.
- The referenced 31-table data dictionary is not in the workspace; the supervisor confirms organizers will provide it shortly. Dataset is released tomorrow. Source mappings, fields and model labels remain TBC.

## Requirements
Three layers: (1) Data Product Factory with one golden customer ID and C360; (2) plain-English insights showing SQL or sources and refusing out-of-scope questions; (3) exactly one operational AI use case. Governance spans all three: access control, monitoring, human review, exclusion of protected attributes from decisions, financial hardship flags.

Tonight: one PDF, maximum six pages, named TeamName_SystemDesign.pdf. Page 1 includes team and members and architecture. Pages 2-5 use the exact nine headings required in the current statement. Page 6 holds the draft data contract: owner, schema, at least three quality rules, allowed uses and refresh frequency. No application code submitted.

Rubric: business impact 25%, technical quality 25%, smart AI use 20%, clarity 20%, governance/responsible AI 10%.

Timeline (IST): design 2 Oct 17:00-23:00; top 50 overnight; data/build start 3 Oct 09:00; build ends 4 Oct 21:00; top ten finalists selected.

## Preferences and constraints
- Team: Adda Wale. Members: Prakhar Gupta, Aryan Shrivastava, Krish Agarwal, Ved Maurya. Supervisor: Prakhar Gupta.
- Collaborating model requested: Claude Opus 5.5, high effort.
- Feature Dev is cached locally; load for this session via --plugin-dir, avoiding global installation.
- CockroachDB is a permitted preference, not a reason to overbuild. Codex plugin search returned no results; Claude has no MCP servers configured. Do not claim a managed database exists.
- This new local repo is under cibc-collections-copilot because the parent .git mount is not a usable Git repository.
- GitHub connector identifies pg1590. Supervisor created pg1590/cibc-collections-copilot and made it public; connector now reports push/admin permission. Source material and raw agent outputs remain local.

## Dictionary overview received
Source: docs/sources/data-dictionary-about.txt. Snapshot 28 Sep 2026; history Oct 2016-Sep 2026; ~1M customers, ~1.84M accounts. CSV, yearly Parquet, JSON transcripts, optional WAV. Separate product customer keys confirmed. Tables/Columns/Relationships sheets are NOT present. All source mappings remain TBC. Temporal windows use snapshot time.

## Collaboration round 2
Opus directly reviewed Codex corrections; no subagents used. Dedup keys separated from file lineage; agent assist reduced to cue extraction plus templated brief with optional narrative. Joint exposures split; semantic support reviewed independently.

## Supervisor schema decision
Supervisor authorizes target tables, columns and relationships to be designed by the team. docs/data-model.md defines the logical schema and eight initial metrics. Incoming physical source mappings still need tomorrow's dataset; no source fields are represented as observed facts.

## Remote state
Canonical repo: pg1590/cibc-collections-copilot. Connector reports push/admin permission after supervisor made it public. Reviewed project files may be uploaded; confidential source PDFs/extracts and raw model responses remain local.

## Earlier remote write blocker (resolved through SSH)
Actual README upload failed with connector 403; local SSH keys are not accepted by GitHub. Remote remains empty/public. No data or project files uploaded. Resolve repository-app installation/authenticated Git access before attempting push; source-material exclusions continue to apply.

## Resume check — 2 October 2026
GitHub connector still reports repository push/admin permission, but an actual README create retry returned 403 `Resource not accessible by integration`. Repository contents returned 404 `This repository is empty`. Connector installation listing includes two other accounts, with no pg1590 installation visible. This points to missing repository-app installation access; permission metadata alone is insufficient. No GitHub CLI is installed locally. The six-page PDF and portable backups remain available; application implementation and organizer submission still await supervisor instructions.

## SSH delivery completed — 2 October 2026
Supervisor added the local Ed25519 public authentication key to GitHub. SSH authenticated as pg1590; `git ls-remote origin` confirmed an empty repository before the initial push. `git push -u origin main` succeeded, uploading reviewed tracked project files and local Git history. Sensitive source material and raw reviews were never tracked. The generated PDF and portable backups remain local. Use SSH for subsequent Git operations; the connector write failure has not been resolved or retested. Application implementation and organizer submission remain outside the current scope.

## Plain-language revision — 2 October 2026
Supervisor requested simpler wording and only necessary content. Rewrote submission-content.json, generated system-design.md and the architecture labels in plain English; removed extra design sections while retaining the nine required headings, one operational use case, controls and data-contract requirements. Increased body/table font sizes. Regenerated the six-page PDF and inspected all six pages; required names/headings and text-boundary checks pass. Detailed internal data-model/review documents remain supporting material. No application implementation or organizer submission occurred.
