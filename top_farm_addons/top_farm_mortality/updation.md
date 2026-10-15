# top_farm_mortality — updation.md

Living log of (A) known limitations, (B) deviations from `Top_Farm_Module_3_Mortality_Standalone_Design.md`,
(C) overlap with the other Top Farm modules, (D) verification status. Update it in the same commit as any change.

Status: **built**. Depends on **`top_farm_core`** (client decision after the build review; the original design
was standalone, see B0). Tested on a fresh Odoo 19.0 Community database (`topfarm_test`, throwaway). See section D.

---

## A. Known limitations

| # | Limitation | Impact / workaround |
|---|---|---|
| L1 | Reversal is valued at the bird product's **current** cost, not the original scrap cost. | With FIFO/average drift the reversal amount can differ slightly from the original loss. |
| L2 | One lot per log. | Deaths in a cage with several lots need one log per lot. Cumulative % still sums across them. |
| L3 | A journal entry to the loss account only posts if the bird category is `real_time` **and** the "Bird Mortality" location has a Loss Account. | Otherwise stock + analytic lines are created but no journal entry. The Mortality Controls form shows a warning. |
| L4 | Cage and batch analytic accounts must be in different analytic plans. | Enforced by `top_farm_core` (constraint on the location). |
| L5 | Backdated logs still move stock **today**. | Scrap/reversal date is the posting date; only the log's `date` (daily window) is backdated. |
| L6 | Opening population for a date = live now − birds moved into the cage after that day (net of transfers out) + done deaths from that date. | Rebuilt from stock history since 20.0.1.1.0 (before, transfers after a backdated date were ignored, which could hide a mortality spike). Birds moved out *during* the incident day itself are not in the base (end-of-day population). |
| L7 | After one entry pushes a cage over the threshold, later entries that day also need approval. | Intended (anti-bypass). |
| L8 | Threshold is one value per company, not per cage or flock stage. | Use the minimum-dead-bird floor for small/young cages. |
| L9 | No second-approver rule; a manager can approve their own entry (client decision). | Audited via approved_by / date / chatter. |
| L10 | Quantities are integers; fractional quant quantities are floored in the live count. | Birds are whole units. |
| L11 | Mortality loss uses the product's accounting valuation of a bird (e.g. standard price 2.00). | Accountant decision (expense vs capitalise pre-laying cost) is outside this module. |

## B. Deviations from the approved design (what changed while building, and why)

| # | Design said | Built | Why |
|---|---|---|---|
| B0 | Standalone, no `top_farm_core`. | **Depends on `top_farm_core`.** Removed from this module: the `is_farm_bird` product flag, the analytic-account field on locations, the own cage/batch model, and the own analytic distribution. It now uses core's hierarchy, `is_farm_bird`, `farm_analytic_account_id`, `get_live_bird_count()` and `get_analytic_distribution_for_cage()`. | Client decision: core's versions of the flag, hook and bird count are authoritative; mortality keeps its own groups and menu. The module can no longer be installed without core. |
| B1 | Scrap to `Virtual Locations/Scrapped`; loss account set on that location. | Module creates its own location **Bird Mortality** (usage "Inventory adjustment", top level) and scraps there. | Odoo 19 has **no** separate "Scrapped" location and no "Virtual Locations" parent. The only inventory-usage location is "Inventory adjustment", shared with stock counts, so a loss account on it would mix counting losses with mortality. |
| B2 | Batch and cage analytic accounts as two keys, each 100%. | **One combined key** (`"batch,cage": 100`) = one analytic line with both plan columns, taken from core's `get_analytic_distribution_for_cage()`. | Verified in `stock_account/models/analytic_account.py`: two keys create two full-amount lines and double-count cost. The test asserts exactly one line. |
| B3 | Threshold in standard Odoo Settings. | Dedicated form **Mortality > Configuration > Mortality Controls** (model `farm.mortality.config`, one per company). | Odoo's Settings screen can only be saved by Settings administrators, so a Mortality Manager could not change it. |
| B4 | Manager group implies Stock Administrator. | Manager implies **Operator** (which implies Inventory User) only. | Least privilege; approving/reversing needs no stock admin rights. |
| B5 | Draft preview "filled by onchange". | Same, but values are saved with `force_save`; the authoritative numbers are recomputed and frozen at Submit. | As designed; noted for clarity. |
| B6 | (not specified) | Reverse move needs a reference. | A move without picking/scrap/inventory has an empty computed reference and Odoo's journal-entry builder crashes on it (found by the tests). |
| B6b | (not specified) | The Reverse move is marked `is_inventory` with an `inventory_name`. | The supported way to give a picking-less move a reference (B6). Side effect: it appears under the "Inventory" filter in Stock Moves reporting. |
| B7 | (not specified) | Reject/Reverse wizard has an explicit access rule (managers). | Odoo 19 requires an ACL even for transient models (found by the tests). |
| B8 | Mortality tags its own scrap/reversal analytics. | Core already tags the **outgoing scrap** from a cage. Mortality only tags the **Reverse** move (incoming, which core skips) by reusing core's `get_analytic_distribution_for_cage()`, so the reversal offsets the original line. | Avoids a second hook doing the same job. |
| B9 | Menu "Mortality" root. | Same. Menus: Mortality Records, Analysis, Configuration > Mortality Controls. | — |

## C. Relationship with the other Top Farm modules (checked against `top_farm_core` code and the Module 2/4 plans)

| Area | Decision |
|---|---|
| `is_farm_bird` flag | **Core's.** Mortality has no copy, so the product form shows one checkbox. Core does not require the product to be storable; a non-storable bird has no quants, so the live-stock guard simply blocks it. |
| `stock.move._get_analytic_distribution` | **Core's** for the scrap (outgoing from a cage). Mortality adds a small override only for the Reverse move (see B8). |
| Live bird count | **Core's** `get_live_bird_count()` is used for the cage population in the threshold maths. Mortality also needs counts **per product and per lot** for the hard guard; that is a quant query of its own because core has no per-lot count. |
| Groups | **Mortality keeps its own** Operator/Manager groups (separate privilege from core's Farm groups). A user may hold both. |
| Menus | **Mortality keeps its own "Mortality" menu root** (Mortality Records, Analysis, Configuration > Mortality Controls). It sits beside core's "Top Farm" root. |
| Settings | Core has its laying-phase settings in the standard Settings screen. Mortality has its own **Mortality Controls** form (B3). No clash. |
| Module 4 plan (`top_farm_dashboard`) | Plan has its own `farm.mortality.report` SQL view. **Do not duplicate:** mortality ships a pivot/graph (Mortality > Analysis). The plan's SQL view reads `available_live_birds`, which does not exist here; the equivalent stored column is **`opening_population`** (plus `cumulative_dead`, `mortality_pct`). |
| Module 2 plan (`top_farm_operations`) | The old Module 3 plan hung its menu under Module 2's menu. Not used: mortality has its own menu and needs nothing from Module 2. |

## D. Verification status

| Item | Status |
|---|---|
| Analytic hook fires on scrap moves; lines created under periodic valuation | Verified in Odoo 19.0 source |
| `stock.scrap.action_validate()` returns a wizard (no exception) on short stock | Verified in source; module checks `scrap.state` |
| Combined analytic key gives one line with both plan columns | Verified in source (`_perform_analytic_distribution`); asserted by test |
| Automated tests (`--test-tags top_farm_mortality`, 14 tests) | See latest result below |
| UI/browser walkthrough (forms, buttons, menus rendering) | **Not yet done** — to do with the setup guide |

Latest automated run (2026-10-01, fresh Odoo 19.0 Community DB, `--test-tags top_farm_mortality`): **14 tests, 0 failed, 0 errors.**
Covers: scrap + single analytic line + journal entry, threshold/approve, cumulative on opening population, pending counts, hard guard (per lot, pending-aware), floor, reject, reverse (offsets analytics, excluded from totals), security, self-approval, date rules, config limits, lot rules, bird flag + form onchange.
