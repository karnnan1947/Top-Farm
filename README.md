# Top Farm

Poultry-layer farm ERP on Odoo 19 (Community and Enterprise), built as four addons:

| Module | Purpose | Status |
|---|---|---|
| `top_farm_core` | Farm / Batch / Cage location hierarchy, flock lifecycle, live bird counts, Batch + Cage analytic costing, farm security roles | Done, tested |
| `top_farm_operations` | Daily feed log, egg harvest, MO split engine | Planned |
| `top_farm_mortality` | Daily mortality scrap with approval guard | Planned |
| `top_farm_dashboard` | KPIs: hen-day %, FCR, cage P&L | Planned |

## Layout

```
top_farm_addons/        Odoo addons folder (add it to addons_path)
  top_farm_core/
Module1_Test_Report/    Functional guide + test report for Module 1 (DOCX, PDF, screenshots)
Top_Farm_*.md           Architecture and per-module implementation plans
```

## Install and test

Add `top_farm_addons` to the Odoo `addons_path`, then:

```
odoo-bin -d <db> -i top_farm_core --stop-after-init
odoo-bin -d <db> -u top_farm_core --test-enable --test-tags=/top_farm_core --stop-after-init
```

Module 1 dependencies: `stock`, `stock_account`, `analytic`. Current result: 16 / 16 tests pass on Odoo 19 Community and Enterprise.

## Notes for the next modules

- `top_farm_operations` must define `mrp.production.farm_collection_id` (the core analytic hook reads it) and stamp `farm_cage_location_id` on feed moves.
- `batch_stage` is held on the batch; cages follow it automatically. Never write it on cages.
- Batch / Cage costs are recorded on analytic items (`account.analytic.line`), not on journal items. Dashboards must read analytic items.
- The plan's GL codes 600000 / 610000 / 630000 collide with Odoo's generic chart. Agree the real codes with the client's chart before go-live.
