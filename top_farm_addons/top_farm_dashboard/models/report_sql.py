"""SQL building blocks shared by the farm reporting views."""

REVENUE_CTES = """
inv AS (
    SELECT * FROM (
        SELECT aml.id AS aml_id, aml.date, aml.company_id, -aml.balance AS revenue,
               aml.quantity * (CASE WHEN am.move_type = 'out_refund' THEN -1 ELSE 1 END) AS inv_qty,
               sol.id AS sol_id,
               CASE sol.product_id
                    WHEN rc.farm_egg_large_product_id THEN 'large'
                    WHEN rc.farm_egg_medium_product_id THEN 'medium'
                    WHEN rc.farm_egg_jumbo_product_id THEN 'jumbo'
                    WHEN rc.farm_egg_damage_product_id THEN 'damage' END AS grade,
               sol.product_id
          FROM account_move_line aml
          JOIN account_move am ON am.id = aml.move_id
          JOIN res_company rc ON rc.id = aml.company_id
          JOIN sale_order_line_invoice_rel rel ON rel.invoice_line_id = aml.id
          JOIN sale_order_line sol ON sol.id = rel.order_line_id
         WHERE am.state = 'posted' AND am.move_type IN ('out_invoice', 'out_refund')
           AND aml.display_type = 'product'
    ) x WHERE grade IS NOT NULL
),
delivered AS (
    SELECT sm.sale_line_id AS sol_id, sml.lot_id,
           SUM(CASE WHEN dst.usage = 'customer' THEN sml.quantity
                    WHEN src.usage = 'customer' THEN -sml.quantity ELSE 0 END) AS qty
      FROM stock_move_line sml
      JOIN stock_move sm ON sm.id = sml.move_id AND sm.state = 'done'
      JOIN stock_location src ON src.id = sml.location_id
      JOIN stock_location dst ON dst.id = sml.location_dest_id
     WHERE sm.sale_line_id IS NOT NULL AND sml.lot_id IS NOT NULL
     GROUP BY sm.sale_line_id, sml.lot_id
),
inv_lot AS (
    SELECT inv.*, d.lot_id, d.qty AS lot_qty, lot.farm_batch_location_id AS batch_id,
           lot.farm_production_date AS production_date,
           d.qty / NULLIF(SUM(d.qty) OVER (PARTITION BY inv.aml_id), 0) AS lot_share
      FROM inv
      JOIN delivered d ON d.sol_id = inv.sol_id AND d.qty > 0
      JOIN stock_lot lot ON lot.id = d.lot_id AND lot.farm_batch_location_id IS NOT NULL
),
egg_cage AS (
    SELECT ec.batch_location_id, ec.date, ec.cage_location_id, g.grade, g.qty,
           SUM(g.qty) OVER (PARTITION BY ec.batch_location_id, ec.date, g.grade) AS batch_qty
      FROM farm_egg_collection ec
     CROSS JOIN LATERAL (VALUES ('large', ec.qty_large), ('medium', ec.qty_medium),
                                ('jumbo', ec.qty_jumbo), ('damage', ec.qty_damage)) AS g(grade, qty)
     WHERE ec.state = 'done' AND g.qty > 0
),
rev AS (
    SELECT il.aml_id, il.date, il.company_id, il.batch_id AS batch_location_id,
           ec.cage_location_id, il.production_date, il.grade, il.product_id,
           il.revenue * il.lot_share * COALESCE(ec.qty::float / ec.batch_qty, 1.0) AS revenue,
           il.inv_qty * il.lot_share * COALESCE(ec.qty::float / ec.batch_qty, 1.0) AS eggs_sold
      FROM inv_lot il
      LEFT JOIN egg_cage ec ON ec.batch_location_id = il.batch_id
                           AND ec.date = il.production_date AND ec.grade = il.grade
)
"""


def plan_columns(env):
    """analytic.line columns holding the root plans of this database (names differ per database)."""
    plans = env['account.analytic.plan'].sudo().search([('parent_id', '=', False)])
    return sorted(set(['account_id'] + [p._column_name() for p in plans]))


def cost_ctes(env):
    cols = ', '.join(f'aal.{c}' for c in plan_columns(env))
    return f"""
line_acc AS (
    SELECT aal.id AS aal_id, acc.id AS account_id
      FROM account_analytic_line aal, LATERAL unnest(ARRAY[{cols}]) AS acc(id)
     WHERE acc.id IS NOT NULL
),
line_loc AS (
    SELECT la.aal_id,
           MAX(CASE WHEN loc.farm_hierarchy_level = 'cage' THEN loc.id END) AS cage_id,
           MAX(CASE WHEN loc.farm_hierarchy_level = 'batch' THEN loc.id END) AS batch_id
      FROM line_acc la
      JOIN stock_location loc ON loc.farm_analytic_account_id = la.account_id
                             AND loc.farm_hierarchy_level IN ('cage', 'batch')
     GROUP BY la.aal_id
),
costs AS (
    SELECT aal.id, aal.date, aal.company_id,
           COALESCE(cage.parent_batch_location_id, ll.batch_id) AS batch_location_id,
           ll.cage_id AS cage_location_id, -aal.amount AS cost,
           CASE
             WHEN pt.is_farm_bird THEN 'mortality'
             WHEN EXISTS (SELECT 1 FROM farm_dashboard_config cfg
                            JOIN farm_dashboard_feed_categ_rel r ON r.config_id = cfg.id
                            JOIN product_category c0 ON c0.id = r.category_id
                           WHERE cfg.company_id = aal.company_id
                             AND pc.parent_path LIKE c0.parent_path || '%') THEN 'feed'
             WHEN EXISTS (SELECT 1 FROM farm_dashboard_config cfg
                            JOIN farm_dashboard_med_categ_rel r ON r.config_id = cfg.id
                            JOIN product_category c0 ON c0.id = r.category_id
                           WHERE cfg.company_id = aal.company_id
                             AND pc.parent_path LIKE c0.parent_path || '%') THEN 'medication'
           END AS cost_type
      FROM account_analytic_line aal
      JOIN line_loc ll ON ll.aal_id = aal.id
      LEFT JOIN stock_location cage ON cage.id = ll.cage_id
      JOIN product_product pp ON pp.id = aal.product_id
      JOIN product_template pt ON pt.id = pp.product_tmpl_id
      JOIN product_category pc ON pc.id = pt.categ_id
)
"""
