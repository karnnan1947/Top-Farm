"""SQL building blocks shared by the farm reporting views. Reporting is flock-first: every revenue and cost row
carries the flock lot, and the cage (or brooding nursery) is a second level under it."""

# Invoiced sales of the flock: graded eggs (through the egg lot's parent flock) and live birds such as spent hens
# (the delivered lot is the flock itself). Egg revenue is shared between the cages by their egg counts.
REVENUE_CTES = """
inv AS (
    SELECT * FROM (
        SELECT aml.id AS aml_id, aml.date, aml.company_id, -aml.balance AS revenue,
               aml.quantity * (CASE WHEN am.move_type = 'out_refund' THEN -1 ELSE 1 END) AS inv_qty,
               sol.id AS sol_id,
               CASE WHEN pt.is_farm_bird THEN 'spent_hen'
                    WHEN sol.product_id = rc.farm_egg_large_product_id THEN 'large'
                    WHEN sol.product_id = rc.farm_egg_medium_product_id THEN 'medium'
                    WHEN sol.product_id = rc.farm_egg_jumbo_product_id THEN 'jumbo'
                    WHEN sol.product_id = rc.farm_egg_damage_product_id THEN 'damage' END AS grade,
               sol.product_id
          FROM account_move_line aml
          JOIN account_move am ON am.id = aml.move_id
          JOIN res_company rc ON rc.id = aml.company_id
          JOIN sale_order_line_invoice_rel rel ON rel.invoice_line_id = aml.id
          JOIN sale_order_line sol ON sol.id = rel.order_line_id
          JOIN product_product pp ON pp.id = sol.product_id
          JOIN product_template pt ON pt.id = pp.product_tmpl_id
         WHERE am.state = 'posted' AND am.move_type IN ('out_invoice', 'out_refund')
           AND aml.display_type = 'product'
    ) x WHERE grade IS NOT NULL
),
delivered AS (
    -- birds delivered straight from a cage (spent hens) keep that cage, so their revenue meets their cost there
    SELECT sm.sale_line_id AS sol_id, sml.lot_id,
           CASE WHEN src.farm_hierarchy_level IN ('brooding', 'cage') THEN src.id END AS house_id,
           SUM(CASE WHEN dst.usage = 'customer' THEN sml.quantity
                    WHEN src.usage = 'customer' THEN -sml.quantity ELSE 0 END) AS qty
      FROM stock_move_line sml
      JOIN stock_move sm ON sm.id = sml.move_id AND sm.state = 'done'
      JOIN stock_location src ON src.id = sml.location_id
      JOIN stock_location dst ON dst.id = sml.location_dest_id
     WHERE sm.sale_line_id IS NOT NULL AND sml.lot_id IS NOT NULL
     GROUP BY sm.sale_line_id, sml.lot_id, 3
),
inv_lot AS (
    SELECT inv.*, d.lot_id, d.house_id, d.qty AS lot_qty,
           COALESCE(lot.farm_flock_lot_id, CASE WHEN lot.is_flock_batch THEN lot.id END) AS flock_id,
           lot.farm_production_date AS production_date,
           d.qty / NULLIF(SUM(d.qty) OVER (PARTITION BY inv.aml_id), 0) AS lot_share
      FROM inv
      JOIN delivered d ON d.sol_id = inv.sol_id AND d.qty > 0
      JOIN stock_lot lot ON lot.id = d.lot_id AND (lot.farm_flock_lot_id IS NOT NULL OR lot.is_flock_batch)
),
egg_cage AS (
    SELECT ec.flock_lot_id, ec.date, ec.cage_location_id, g.grade, g.qty,
           SUM(g.qty) OVER (PARTITION BY ec.flock_lot_id, ec.date, g.grade) AS flock_qty
      FROM farm_egg_collection ec
     CROSS JOIN LATERAL (VALUES ('large', ec.qty_large), ('medium', ec.qty_medium),
                                ('jumbo', ec.qty_jumbo), ('damage', ec.qty_damage)) AS g(grade, qty)
     WHERE ec.state = 'done' AND g.qty > 0
),
rev AS (
    SELECT il.aml_id, il.date, il.company_id, il.flock_id AS flock_lot_id, flock.farm_location_id,
           COALESCE(ec.cage_location_id, il.house_id) AS cage_location_id, il.production_date, il.grade, il.product_id,
           il.revenue * il.lot_share * COALESCE(ec.qty::float / ec.flock_qty, 1.0) AS revenue,
           CASE WHEN il.grade = 'spent_hen' THEN 0
                ELSE il.inv_qty * il.lot_share * COALESCE(ec.qty::float / ec.flock_qty, 1.0) END AS eggs_sold,
           CASE WHEN il.grade = 'spent_hen' THEN il.inv_qty * il.lot_share ELSE 0 END AS birds_sold
      FROM inv_lot il
      JOIN stock_lot flock ON flock.id = il.flock_id
      LEFT JOIN egg_cage ec ON ec.flock_lot_id = il.flock_id
                           AND ec.date = il.production_date AND ec.grade = il.grade
)
"""


def plan_columns(env):
    """analytic.line columns holding the root plans of this database (names differ per database)."""
    plans = env['account.analytic.plan'].sudo().search([('parent_id', '=', False)])
    return sorted(set(['account_id'] + [p._column_name() for p in plans]))


def cost_ctes(env):
    """`costs`: every analytic cost line of a flock or cage account, with its flock, cage, farm and cost type:
    feed, medication, mortality (bird scraps and their reversals), depletion (birds leaving otherwise, e.g.
    spent hens sold) or other (heating, labour and other bills tagged to the flock). Revenue lines are left out:
    egg and spent hen revenue come from the invoices through the delivered lots (REVENUE_CTES)."""
    cols = ', '.join(f'aal.{c}' for c in plan_columns(env))
    return f"""
line_acc AS (
    SELECT aal.id AS aal_id, acc.id AS account_id
      FROM account_analytic_line aal, LATERAL unnest(ARRAY[{cols}]) AS acc(id)
     WHERE acc.id IS NOT NULL
),
line_dim AS (
    SELECT la.aal_id, MAX(flock.id) AS flock_id, MAX(cage.id) AS cage_id
      FROM line_acc la
      LEFT JOIN stock_lot flock ON flock.flock_analytic_account_id = la.account_id AND flock.is_flock_batch
      LEFT JOIN stock_location cage ON cage.farm_analytic_account_id = la.account_id
                                   AND cage.farm_hierarchy_level = 'cage'
     GROUP BY la.aal_id
    HAVING MAX(flock.id) IS NOT NULL OR MAX(cage.id) IS NOT NULL
),
line_move AS (
    SELECT rel.account_analytic_line_id AS aal_id, MAX(rel.stock_move_id) AS move_id
      FROM account_analytic_line_stock_move_rel rel
     GROUP BY rel.account_analytic_line_id
),
costs AS (
    SELECT aal.id, aal.date, aal.company_id, ld.flock_id AS flock_lot_id, ld.cage_id AS cage_location_id,
           COALESCE(flock.farm_location_id, cage.parent_farm_location_id) AS farm_location_id,
           aal.product_id, aal.unit_amount AS quantity, -aal.amount AS cost,
           -- laying operation: feed of the egg MOs and staged laying feed expensed unharvested
           (sm.raw_material_production_id IS NOT NULL OR COALESCE(fl.feeding_phase = 'laying', FALSE)) AS laying_phase,
           CASE
             WHEN ga.account_type IN ('income', 'income_other') THEN NULL
             WHEN pt.is_farm_bird THEN
                  CASE WHEN sm.is_scrap OR sm.farm_mortality_log_id IS NOT NULL THEN 'mortality' ELSE 'depletion' END
             WHEN pt.farm_input_type = 'feed' OR EXISTS (
                      SELECT 1 FROM farm_dashboard_config cfg
                        JOIN farm_dashboard_feed_categ_rel r ON r.config_id = cfg.id
                        JOIN product_category c0 ON c0.id = r.category_id
                       WHERE cfg.company_id = aal.company_id
                         AND pc.parent_path LIKE c0.parent_path || '%') THEN 'feed'
             WHEN pt.farm_input_type = 'medication' OR EXISTS (
                      SELECT 1 FROM farm_dashboard_config cfg
                        JOIN farm_dashboard_med_categ_rel r ON r.config_id = cfg.id
                        JOIN product_category c0 ON c0.id = r.category_id
                       WHERE cfg.company_id = aal.company_id
                         AND pc.parent_path LIKE c0.parent_path || '%') THEN 'medication'
             ELSE 'other'
           END AS cost_type
      FROM account_analytic_line aal
      JOIN line_dim ld ON ld.aal_id = aal.id
      LEFT JOIN stock_lot flock ON flock.id = ld.flock_id
      LEFT JOIN stock_location cage ON cage.id = ld.cage_id
      LEFT JOIN line_move lm ON lm.aal_id = aal.id
      LEFT JOIN stock_move sm ON sm.id = lm.move_id
      LEFT JOIN stock_picking sp ON sp.id = sm.picking_id
      LEFT JOIN farm_feed_log fl ON fl.id = sp.farm_feed_log_id
      LEFT JOIN account_account ga ON ga.id = aal.general_account_id
      LEFT JOIN product_product pp ON pp.id = aal.product_id
      LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
      LEFT JOIN product_category pc ON pc.id = pt.categ_id
)
"""
