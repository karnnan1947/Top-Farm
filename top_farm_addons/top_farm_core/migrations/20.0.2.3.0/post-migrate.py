# -*- coding: utf-8 -*-


def migrate(cr, version):
    # Broiler batches now end in their own 'Closed' stage: 'Spent / Depleted' is kept for layer flocks.
    cr.execute("""
        UPDATE stock_lot
           SET flock_stage = 'closed'
         WHERE is_flock_batch AND flock_type = 'broiler' AND flock_stage = 'spent'
    """)
