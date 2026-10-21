# Phase 9b: invoice the delivered eggs and spent hens (the invoice lines inherit the flock analytic account).
flock = rec('stock.lot', 'flock')
for key in ('so_eggs', 'so_hens'):
    so = rec('sale.order', key)
    if not so.invoice_ids:
        invoice = so._create_invoices()
        invoice.action_post()
        save_ids(**{f'inv_{key[3:]}': invoice})
acc = str(flock.flock_analytic_account_id.id)
for key, label in (('so_eggs', 'egg'), ('so_hens', 'spent hen')):
    so = rec('sale.order', key)
    check(f'TC-09-0{2 if label == "egg" else 3}', f'{label} sale lines tagged 100 % to the flock account',
          [{acc: 100.0}] * len(so.order_line), [l.analytic_distribution for l in so.order_line])
inv_eggs, inv_hens = rec('account.move', 'inv_eggs'), rec('account.move', 'inv_hens')
check('TC-09-04', 'egg invoice amount', 3000 * 45 + 2000 * 40 + 600 * 50 + 200 * 20.0, inv_eggs.amount_untaxed)
check('TC-09-05', 'spent hen invoice amount', IDS['hens_sold'] * 650.0, inv_hens.amount_untaxed)
check('TC-09-06', 'egg invoice lines carry the flock analytic account', True,
      all(acc in (l.analytic_distribution or {}) for l in inv_eggs.invoice_line_ids))
check('TC-09-07', 'flock has no live birds left after the spent hen sale', 0, flock.live_bird_count)
env.cr.commit()
