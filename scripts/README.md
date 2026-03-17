# Demo scripts

**Run from the project root with the project venv activated** so dependencies (PyGithub, pydantic, etc.) are available:

```bash
source .venv/bin/activate   # or:  .venv\Scripts\activate  on Windows
python scripts/demo_pr.py [REPO] [PR]
python scripts/demo_ticket.py [TICKET] [ORG]
python scripts/demo_author.py [AUTHOR] [ORG] [SINCE]
```

| Script | Description | Example |
|--------|-------------|--------|
| **demo_pr.py** | Analyze a single PR (metrics + AI report + markdown). | `python scripts/demo_pr.py FloQastInc/close 5194` |
| **demo_ticket.py** | Find a merged PR that mentions a Jira ticket and run full analysis. | `python scripts/demo_ticket.py CLOSE-13455 FloQastInc` |
| **demo_author.py** | Analyze all merged PRs by an author in the last N days (org-wide). | `python scripts/demo_author.py c-sachanocetto_floqast FloQastInc 15d` |

## Usage

```bash
# Single PR (defaults: FloQastInc/close, PR 5194)
python scripts/demo_pr.py
python scripts/demo_pr.py FloQastInc/checklist-service 15

# By Jira ticket (defaults: CLOSE-13455, org FloQastInc)
python scripts/demo_ticket.py
python scripts/demo_ticket.py CLOSE-13054 FloQastInc

# By author (defaults: c-sachanocetto_floqast, FloQastInc, 15d)
python scripts/demo_author.py
python scripts/demo_author.py c-matiasgabrielsfer_floqast FloQastInc 30d
```

Reports are written to `reports/` (e.g. `reports/pr_5194_report.md`). Ensure `.env` has at least `GITHUB_TOKEN`; Jira and AI keys are optional for richer reports.
