# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # Valuation entries posted before 20.0.2.1.0 have no analytic distribution on their expense line:
    # stamp it, so the Profit and Loss by analytic account shows the past flock costs, without doubling them.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['stock.move']._farm_backfill_valuation_analytics()
