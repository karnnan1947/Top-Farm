# Shared helpers, prepended to every phase script piped into `odoo-bin shell` (see run.sh).
# `env` is provided by the Odoo shell (superuser); business actions run as the admin (Farm Manager) or the
# Farm Operator, like in the client's daily use.
import json
import os
from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError

RESULTS = os.environ.get('TF_RESULTS') or os.path.join(
    r'C:\pycharmproject\odoo20\Top-Farm\Top_Farm_Flock_Workflow_Test_Report\test_scripts', 'results')
os.makedirs(RESULTS, exist_ok=True)
PHASE = os.environ.get('TF_PHASE', 'adhoc')

admin = env.ref('base.user_admin')
env = env(user=admin, context=dict(env.context, tz='Asia/Colombo'))
su = env(su=True)
company = env.company
TODAY = fields.Date.context_today(env['res.users'].browse(admin.id))


def _path(name):
    return os.path.join(RESULTS, name)


def load(name, default=None):
    try:
        with open(_path(name), encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {} if default is None else default


def dump(name, data):
    with open(_path(name), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)


IDS = load('ids.json')


def save_ids(**values):
    IDS.update({k: (v.id if hasattr(v, '_name') else v) for k, v in values.items()})
    dump('ids.json', IDS)


def rec(model, key):
    return env[model].browse(IDS[key])


# checks of this phase replace the previous run of the same phase
CHECKS = [c for c in load('checks.json', []) if c.get('phase') != PHASE]


def check(tc, label, expected, actual, ok=None):
    ok = (expected == actual) if ok is None else bool(ok)
    CHECKS.append({'phase': PHASE, 'tc': tc, 'label': label, 'expected': expected, 'actual': actual,
                   'status': 'PASS' if ok else 'FAIL'})
    print(('PASS ' if ok else 'FAIL ') + f'{tc} {label}  [expected {expected} | actual {actual}]', flush=True)
    dump('checks.json', CHECKS)
    return ok


def close(a, b, tol=0.01):
    return abs((a or 0.0) - (b or 0.0)) <= tol


def log(*args):
    print('>>', *args, flush=True)


def user(login):
    return env(user=su['res.users'].search([('login', '=', login)]))


def loc(name, parent=None):
    domain = [('name', '=', name)]
    if parent:
        domain.append(('location_id', '=', parent.id))
    return env['stock.location'].search(domain, limit=1)


def prod(name):
    return env['product.product'].search([('name', '=', name)], limit=1)


def lot(name, product=None):
    domain = [('name', '=', name)]
    if product:
        domain.append(('product_id', '=', product.id))
    return env['stock.lot'].search(domain, limit=1)


def analytic_lines(account, extra=None):
    """Analytic items carrying `account` in any plan column."""
    plan_field = account.plan_id.root_id._column_name()
    return su['account.analytic.line'].search([(plan_field, '=', account.id)] + (extra or []))


def plan_col(plan):
    return plan.root_id._column_name()
