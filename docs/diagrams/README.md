# AI engine diagrams

Mermaid sources for the finals deck "Inside the AI engine". Each `.mmd` file has a rendered `.png` beside it.

| File | Shows |
| --- | --- |
| `arch.mmd` | Seven input/output layers and the payload passed between them |
| `er.mmd` | Identity resolution: blocking, pair scoring, threshold and margin test |
| `hardship.mmd` | Hardship classifier: note → 9 cues → logistic regression → served rule |
| `planner.mmd` | Ask: rule parser, then Gemini plan JSON, validation, reviewed SQL |
| `callnote.mmd` | Call wrap-up: Whisper, Gemini extraction with rule fallback, quote verification |

Re-render (needs Node and a local Chromium):

```sh
npx -p @mermaid-js/mermaid-cli@11.4.2 mmdc -i docs/diagrams/arch.mmd -o docs/diagrams/arch.png \
  -c docs/diagrams/mermaid-theme.json -b '#F5F7F4' -s 2 -w 2400
```
