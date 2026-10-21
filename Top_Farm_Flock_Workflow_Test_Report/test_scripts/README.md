# Top Farm flock workflow test: scripts

Scripts that produced `../Top_Farm_Flock_Workflow_Test_Report.docx` / `.pdf` and `../screenshots/` on database
`topfarm20_flock` (Odoo 20.0 Enterprise, Top Farm modules 20.0.2.0.0).

| Folder | Content |
|---|---|
| `data/` | Phases piped into `odoo-bin shell` (each prefixed with `common.py`): master data, the daily records, and `p10_verify.py`, which recomputes every expected amount and compares it with Odoo. |
| `browser/` | Playwright steps (`playwright-core` + installed Chrome). They click the business buttons and save each screenshot with its caption. |
| `report/` | `gen_report.js` builds the .docx from `results/` and the screenshots (npm package `docx`); `word_export.py` refreshes the table of contents and exports the PDF through Word. |
| `results/` | `checks.json` (all checks), `shots.json` (screenshot captions), `summary.json` (verification tables), `ids.json` (record ids of the run). |

## Run

1. Install a fresh database: `odoo-bin -d topfarm20_flock -i top_farm_dashboard,purchase_stock,sale_management,accountant`.
2. `./run.sh serve` (port 8021, kept running).
3. `TF_NODE_MODULES=<folder with docx and playwright-core> ./run_all.sh` runs every phase in order and stops at the first failure.
4. `NODE_PATH=$TF_NODE_MODULES node report/gen_report.js`, then `python report/word_export.py ../Top_Farm_Flock_Workflow_Test_Report.docx`.

The phases are idempotent only on a fresh database: rebuild it before running `run_all.sh` again.
