# Top Farm

Poultry-layer farm ERP on Odoo 20 Enterprise, built as four addons. Version 20.0.2.0.0 implements the revised
workflow (`Top_Farm_Revised_Workflow_Implementation_Plan.md`): farm infrastructure is permanent, and a **flock
batch is a lot** (`stock.lot`) that moves through it.

| Module | Purpose |
|---|---|
| `top_farm_core` | Farm / Brooding Nursery / Laying Shed / Cage locations, flock lots (arrival date, age, stage, flock analytic account), flock lot creation on dispatch to brooding (manual or automated `[Estate Code]-[Date]`), Brooding-to-Cage allocation wizard, Flock + Cage analytic hook, farm security roles |
| `top_farm_operations` | Daily feed and medication per flock in a brooding nursery or cage, graded egg collections lotted under the parent flock, 50 % rolling hen-day laying transition, MO split engine |
| `top_farm_mortality` | Daily mortality per flock in a brooding nursery or cage, cumulative threshold with manager approval, scrap charged to the flock |
| `top_farm_dashboard` | Flock KPIs dashboard, Pre-Laying Flock Investment report, flock lifetime P&L, egg revenue allocation, BI views |

## Layout

```
top_farm_addons/                        Odoo addons folder (add it to addons_path)
Top_Farm_Flock_Workflow_Test_Report/    Flock lifecycle test report (DOCX + PDF), screenshots and the scripts that produced them
Top_Farm_*.md                           Architecture and implementation plans
```

## Install

Add `top_farm_addons` to the Odoo `addons_path`, then:

```
odoo-bin -d <db> -i top_farm_dashboard --stop-after-init
```

Version 2.0 replaces the batch locations of 1.x with flock lots. There is no migration of 1.x data: build a fresh
database (the 1.x test database `topfarm20` stays on the old design).

## Design notes

- Odoo moves a lot unchanged from source to destination. Chicks dispatched to a brooding nursery under their
  hatchery lot are re-labelled there as their flock lot through the virtual location *Flock Lot Conversion*
  (out under the hatchery lot, in under the flock lot, same value). Keep that location without a valuation
  account: the conversion then posts no journal entry and leaves the stock value unchanged.
- Approach A (manual): the clerk fills the Flock Lot column of the transfer lines; validation is refused without
  it. Approach B (automated): `[Estate Code]-[DD-MM-YYYY]`, with the estate code set on the farm location and
  the date taken from the hatchery lot's arrival or from the transfer validation.
- One flock per cage: the allocation wizard refuses a cage that still holds another flock.
- Flock costs go to the flock analytic account (Flock Batches plan); cage costs land on one analytic line with
  both the flock and the cage account, so the cage accounts must belong to another root plan (Farm Cages).
- Flock and cage costs are analytic items (`account.analytic.line`), not journal items. Reports read analytic items.
- The pre-laying investment counts the chicks placed, then the feed, medication and other costs tagged to the
  flock until the Laying Phase start date; laying feed and mortality scraps are excluded.
- The plan's GL codes 600000 / 610000 / 630000 collide with Odoo's generic chart. Agree the real codes with the
  client's chart before go-live.
