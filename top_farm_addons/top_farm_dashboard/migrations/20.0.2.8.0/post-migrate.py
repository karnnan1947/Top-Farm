# Dashboard access per user (20.0.2.8.0): the farm users of the database keep seeing both dashboards and their
# reports after the upgrade. An administrator then unticks Flock / Layer Dashboard or Broiler Dashboard on the users
# of the other team. Users created afterwards start with neither.
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    farm_users = env['res.users'].with_context(active_test=False).search(
        [('all_group_ids', 'in', env.ref('top_farm_core.group_farm_user').id)])
    groups = env.ref('top_farm_dashboard.group_farm_layer_dashboard') | \
        env.ref('top_farm_dashboard.group_farm_broiler_dashboard')
    farm_users.write({'group_ids': [(4, group.id) for group in groups]})
