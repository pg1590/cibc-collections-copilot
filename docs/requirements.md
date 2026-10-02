# Requirements and submission checklist

Authority: current problem statement, pages 1-3. The broader deck describes later build expectations and is supplementary.

| Requirement | Submission location | Verification |
|---|---|---|
| One PDF, at most six pages; no application code | submission/Adda Wale_SystemDesign.pdf | PDF page count and visual review |
| Team and four member names | Architecture page 1 | Text extraction |
| Three layers, named tools, AI locations, human review | Architecture page 1 | Diagram inspection |
| Summary (problem, use case, users, three lines) | Design page 2 | Heading and content review |
| Business value and measurement | Design page 2 | Baseline, denominators, no invented uplift |
| Golden C360 and cross-source identity matching | Design page 2 | Ambiguity, lineage, grain and quality controls |
| Plain-English questions, shown SQL/source, refusal | Design page 3 | Authorization and evidence boundaries |
| Exactly one AI use case; features and explanation | Design page 4 | Explicit selected use case |
| AI usage and rationale | Design page 4 | Runtime AI vs deterministic controls |
| Batch vs real-time scalability | Design page 5 | MVP vs expansion clearly separated |
| Governance, protected attributes, hardship, review | Design page 5 | Customer-impact approval gate |
| 36-hour build plan | Design page 5 | Fits Oct 3 09:00 to Oct 4 21:00 IST |
| Contract owner, schema, >=3 quality rules, allowed uses, refresh | Contract page 6 | Proposed schema; source mappings TBC |

## Design rubric
Business impact 25%; technical quality 25%; smart AI 20%; clarity 20%; responsible AI 10%. No scoring results are claimed.

## Assumptions requiring confirmation
- Data dictionary overview received; supervisor authorizes target schema decisions. Source mappings/sensitivity tags remain TBC until the incoming dataset is profiled.
- Currency, source timestamp semantics, account ownership/cardinality, identity crosswalks, role assignment fields, consent enums and retention policy: TBC.
- Organization-approved LLM provider/model, permitted data export, credentials and deployment connectivity: TBC. Prototype uses synthetic data only.
- Organizer submission portal and final filename treatment of spaces: TBC. Current filename follows TeamName_SystemDesign.pdf literally.
- Deadline conflict: current statement 23:00 IST vs older announcement 21:00 IST; internal review target before 21:00.

## Known confirmed schedule
2 Oct 2026 design; overnight top 50 selection; 3 Oct 09:00 dataset and build start; 4 Oct 21:00 build deadline; top 10 finalists. All times IST.
