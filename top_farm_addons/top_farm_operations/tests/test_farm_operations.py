# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestTopFarmOperations(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.today = fields.Date.context_today(cls.env.user)
        wh = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        Loc = cls.env['stock.location']
        AA = cls.env['account.analytic.account']
        plan_batch = cls.env['account.analytic.plan'].create({'name': 'Ops Test Batch Plan'})
        cls.plan_cage = cls.env['account.analytic.plan'].create({'name': 'Ops Test Cage Plan'})

        farm = Loc.create({'name': 'Ops Farm', 'location_id': wh.lot_stock_id.id, 'farm_hierarchy_level': 'farm'})
        cls.laying_batch = Loc.create({
            'name': 'Batch C-01', 'location_id': farm.id, 'farm_hierarchy_level': 'batch', 'batch_stage': 'laying',
            'chick_arrival_date': cls.today - timedelta(days=150),
            'farm_analytic_account_id': AA.create({'name': 'Ops Batch C-01', 'plan_id': plan_batch.id}).id,
        })
        cls.cage = Loc.create({
            'name': 'Cage A-01', 'location_id': cls.laying_batch.id, 'farm_hierarchy_level': 'cage',
            'farm_analytic_account_id': AA.create({'name': 'Ops Cage A-01', 'plan_id': cls.plan_cage.id}).id,
        })
        cls.young_batch = Loc.create({
            'name': 'Batch C-02', 'location_id': farm.id, 'farm_hierarchy_level': 'batch',
            'chick_arrival_date': cls.today - timedelta(days=70),
            'farm_analytic_account_id': AA.create({'name': 'Ops Batch C-02', 'plan_id': plan_batch.id}).id,
        })
        cls.young_cage = Loc.create({
            'name': 'Cage B-01', 'location_id': cls.young_batch.id, 'farm_hierarchy_level': 'cage',
            'farm_analytic_account_id': AA.create({'name': 'Ops Cage B-01', 'plan_id': cls.plan_cage.id}).id,
        })
        cls.silo = Loc.create({'name': 'Ops Silo', 'location_id': wh.lot_stock_id.id})
        cls.egg_store = Loc.create({'name': 'Ops Eggs', 'location_id': wh.lot_stock_id.id})
        cls.feed_consumption = Loc.create({'name': 'Ops Feed Consumption', 'usage': 'inventory', 'company_id': cls.company.id})
        cls.med_consumption = Loc.create({'name': 'Ops Med Consumption', 'usage': 'inventory', 'company_id': cls.company.id})

        Product = cls.env['product.product']
        kg = cls.env.ref('uom.product_uom_kgm')
        cls.feed = Product.create({'name': 'Layer Mash', 'is_storable': True, 'farm_input_type': 'feed',
                                   'uom_id': kg.id, 'standard_price': 0.5})
        cls.grit = Product.create({'name': 'Oyster Grit', 'is_storable': True, 'farm_input_type': 'feed',
                                   'uom_id': kg.id, 'standard_price': 0.2})
        cls.vaccine = Product.create({'name': 'ND Vaccine', 'is_storable': True, 'farm_input_type': 'medication',
                                      'standard_price': 1.0})
        cls.bird = Product.create({'name': 'Layer Hen', 'is_storable': True, 'is_farm_bird': True})
        cls.eggs = {grade: Product.create({'name': f'{grade.title()} Eggs', 'is_storable': True, 'tracking': 'lot'})
                    for grade in ('large', 'medium', 'jumbo', 'damage')}
        cls.company.write({
            'farm_feed_consumption_location_id': cls.feed_consumption.id,
            'farm_medication_consumption_location_id': cls.med_consumption.id,
            'farm_egg_location_id': cls.egg_store.id,
            **{f'farm_egg_{grade}_product_id': product.id for grade, product in cls.eggs.items()},
        })

        Quant = cls.env['stock.quant']
        Quant._update_available_quantity(cls.feed, cls.silo, 1000)
        Quant._update_available_quantity(cls.grit, cls.silo, 100)
        Quant._update_available_quantity(cls.vaccine, cls.silo, 50)
        Quant._update_available_quantity(cls.bird, cls.cage, 1000)
        Quant._update_available_quantity(cls.bird, cls.young_cage, 500)

        cls.operator = new_test_user(cls.env, login='ops_operator', groups='top_farm_core.group_farm_user')

    # -------------------------------------------------------------------------
    def _feed_log(self, cage, lines, date=None, user=None, confirm=True):
        Log = self.env['farm.feed.log'].with_user(user) if user else self.env['farm.feed.log']
        log = Log.create({
            'cage_location_id': cage.id,
            'date': date or self.today,
            'line_ids': [Command.create({'product_id': product.id, 'source_location_id': self.silo.id, 'quantity': qty})
                         for product, qty in lines],
        })
        if confirm:
            log.action_confirm()
        return log

    def _collection(self, large=0, medium=0, jumbo=0, damage=0, date=None, user=None):
        Collection = self.env['farm.egg.collection'].with_user(user) if user else self.env['farm.egg.collection']
        return Collection.create({
            'cage_location_id': self.cage.id, 'date': date or self.today,
            'qty_large': large, 'qty_medium': medium, 'qty_jumbo': jumbo, 'qty_damage': damage,
        })

    def _on_hand(self, product, location):
        return product.with_context(location=location.id).qty_available

    def _feed_by_grade(self, collection, feed=None):
        feed = feed or self.feed
        return {mo.product_id: sum(mo.move_raw_ids.filtered(lambda m: m.product_id == feed).mapped('quantity'))
                for mo in collection.production_ids}

    # ------------------------------------------------------------------ feed log
    def test_01_pre_laying_feed_is_expensed_at_once(self):
        """Plan test 1: 50 kg pre-laying feed goes straight from the silo to Feed Consumption."""
        log = self._feed_log(self.young_cage, [(self.feed, 50)])
        self.assertEqual(log.feeding_phase, 'pre_laying')
        self.assertEqual(log.state, 'reconciled')
        self.assertEqual(log.picking_ids.state, 'done')
        self.assertEqual(log.picking_ids.location_dest_id, self.feed_consumption)
        self.assertEqual(self._on_hand(self.feed, self.silo), 950)
        move = log.picking_ids.move_ids
        self.assertEqual(move.farm_cage_location_id, self.young_cage, "Moves carry the cage for Batch/Cage costing")
        line = move.analytic_account_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line[self.plan_cage._column_name()], self.young_cage.farm_analytic_account_id)
        self.assertAlmostEqual(line.amount, -25.0)

    def test_02_laying_feed_is_staged_and_medication_expensed(self):
        """Plan test 2: laying feed is not deducted; medication is expensed in every phase."""
        log = self._feed_log(self.cage, [(self.feed, 100), (self.vaccine, 2)])
        self.assertEqual(log.feeding_phase, 'laying')
        self.assertEqual(log.state, 'confirmed')
        self.assertEqual(self._on_hand(self.feed, self.silo), 1000, "Laying feed stays in the silo until harvest")
        self.assertEqual(log.picking_ids.location_dest_id, self.med_consumption)
        self.assertEqual(self._on_hand(self.vaccine, self.silo), 48)
        self.assertEqual((log.total_feed_qty, log.total_med_qty), (100, 2))

    def test_03_feeding_phase_is_frozen_once_confirmed(self):
        log = self._feed_log(self.young_cage, [(self.feed, 10)])
        self.young_batch.action_start_laying_phase()
        self.assertEqual(log.feeding_phase, 'pre_laying', "A stage change never rewrites past feed accounting")
        new_log = self._feed_log(self.young_cage, [(self.feed, 10)], confirm=False)
        self.assertEqual(new_log.feeding_phase, 'laying')

    def test_04_stock_shortage_blocks_the_log(self):
        with self.assertRaises(UserError):
            self._feed_log(self.young_cage, [(self.feed, 5000)])
        self.assertEqual(self._on_hand(self.feed, self.silo), 1000)

    def test_05_cage_must_belong_to_the_batch(self):
        with self.assertRaises(ValidationError):
            self.env['farm.feed.log'].create({
                'cage_location_id': self.cage.id, 'batch_location_id': self.young_batch.id,
                'line_ids': [Command.create({'product_id': self.feed.id, 'source_location_id': self.silo.id,
                                             'quantity': 5})],
            })

    def test_06_missing_settings_give_a_clear_error(self):
        self.company.farm_feed_consumption_location_id = False
        with self.assertRaises(UserError):
            self._feed_log(self.young_cage, [(self.feed, 5)])

    # ------------------------------------------------------------------ egg engine
    def test_10_proportional_split(self):
        """Plan test 3: 500/300/100/100 eggs on 100 kg gives 4 MOs with 50/30/10/10 kg of feed."""
        log = self._feed_log(self.cage, [(self.feed, 100)])
        collection = self._collection(large=500, medium=300, jumbo=100, damage=100)
        self.assertEqual(collection.feed_log_ids, log, "The day's staged feed is linked automatically")
        collection.action_generate_split_manufacturing_orders()
        self.assertEqual(collection.state, 'done')
        self.assertEqual(len(collection.production_ids), 4)
        self.assertTrue(all(mo.state == 'done' for mo in collection.production_ids))
        self.assertEqual(self._feed_by_grade(collection), {
            self.eggs['large']: 50, self.eggs['medium']: 30, self.eggs['jumbo']: 10, self.eggs['damage']: 10,
        })
        self.assertEqual(self._on_hand(self.feed, self.silo), 900)
        self.assertEqual(self._on_hand(self.eggs['large'], self.egg_store), 500)
        self.assertEqual((log.state, log.egg_collection_id), ('reconciled', collection))
        raw_line = collection.production_ids.move_raw_ids.analytic_account_line_ids
        self.assertTrue(raw_line)
        self.assertEqual(raw_line[self.plan_cage._column_name()], self.cage.farm_analytic_account_id)

    def test_11_zero_loss_rounding(self):
        """Plan test 4: the feed of all MOs adds up exactly to the staged feed, residue on the largest grade."""
        self._feed_log(self.cage, [(self.feed, 100)])
        collection = self._collection(large=333, medium=333, jumbo=333)
        collection.action_generate_split_manufacturing_orders()
        by_grade = self._feed_by_grade(collection)
        self.assertEqual(round(sum(by_grade.values()), 2), 100.0)
        self.assertEqual(sorted(round(qty, 2) for qty in by_grade.values()), [33.33, 33.33, 33.34])

        self._feed_log(self.cage, [(self.feed, 100)], date=self.today - timedelta(days=1))
        other = self._collection(large=334, medium=333, jumbo=333, date=self.today - timedelta(days=1))
        other.action_generate_split_manufacturing_orders()
        self.assertEqual(round(sum(self._feed_by_grade(other).values()), 2), 100.0)

    def test_12_every_feed_line_is_split(self):
        """Two feed products in the log: each MO consumes both, in proportion."""
        self._feed_log(self.cage, [(self.feed, 100), (self.grit, 10)])
        collection = self._collection(large=750, medium=250)
        collection.action_generate_split_manufacturing_orders()
        self.assertEqual(self._feed_by_grade(collection), {self.eggs['large']: 75, self.eggs['medium']: 25})
        self.assertEqual(self._feed_by_grade(collection, self.grit), {self.eggs['large']: 7.5, self.eggs['medium']: 2.5})

    def test_13_egg_lot(self):
        """Plan test 5: graded eggs carry the daily batch lot LOT-EGG-<batch>-<YYYYMMDD>."""
        self._feed_log(self.cage, [(self.feed, 10)])
        collection = self._collection(large=100)
        collection.action_generate_split_manufacturing_orders()
        quant = self.env['stock.quant'].search([('product_id', '=', self.eggs['large'].id),
                                                ('location_id', '=', self.egg_store.id)])
        self.assertEqual(quant.lot_id.name, f"LOT-EGG-Batch-C-01-{self.today.strftime('%Y%m%d')}")

    def test_14_kpis_and_permanent_live_bird_snapshot(self):
        """Plan test 6: Hen-Day and FCR use the snapshot, which later mortality does not change."""
        self._feed_log(self.cage, [(self.feed, 100)])
        collection = self._collection(large=600, medium=300)
        collection.action_generate_split_manufacturing_orders()
        self.assertEqual(collection.confirmed_live_bird_count, 1000)
        self.assertAlmostEqual(collection.hen_day_rate, 90.0)
        self.assertAlmostEqual(collection.fcr, 1.333)
        self.env['stock.quant']._update_available_quantity(self.bird, self.cage, -100)
        self.assertEqual(self.cage.get_live_bird_count(), 900)
        self.assertEqual(collection.confirmed_live_bird_count, 1000)
        self.assertAlmostEqual(collection.hen_day_rate, 90.0)

    def test_15_produce_needs_staged_feed(self):
        collection = self._collection(large=100)
        with self.assertRaises(UserError):
            collection.action_generate_split_manufacturing_orders()

    def test_16_one_collection_per_cage_per_day(self):
        self._collection(large=10)
        with self.assertRaises(ValidationError):
            self._collection(large=20)

    def test_17_operator_records_and_produces(self):
        """Operators are not Manufacturing users, yet can log feed, produce eggs and see the MOs."""
        self._feed_log(self.cage, [(self.feed, 20)], user=self.operator)
        collection = self._collection(large=150, medium=50, user=self.operator)
        collection.action_generate_split_manufacturing_orders()
        self.assertEqual(collection.state, 'done')
        self.assertEqual(collection.mo_count, 2)
        self.assertEqual(len(collection.with_user(self.operator).production_ids), 2)

    # ------------------------------------------------------------------ nightly cron
    def test_20_cron_expenses_unharvested_feed(self):
        """Plan test 7: yesterday's unharvested laying feed is expensed; today's stays staged."""
        yesterday = self._feed_log(self.cage, [(self.feed, 80)], date=self.today - timedelta(days=1))
        today = self._feed_log(self.cage, [(self.feed, 70)])
        self.env['farm.feed.log']._cron_reconcile_unharvested_feed()
        self.assertEqual(yesterday.state, 'reconciled')
        self.assertEqual(yesterday.picking_ids.location_dest_id, self.feed_consumption)
        self.assertEqual(yesterday.picking_ids.move_ids.farm_cage_location_id, self.cage)
        self.assertTrue(any('maintenance feed' in (m.body or '') for m in yesterday.message_ids))
        self.assertEqual(today.state, 'confirmed')
        self.assertEqual(self._on_hand(self.feed, self.silo), 920)

    def test_21_cron_survives_a_shortage(self):
        """A silo short of stock is reported on its log; the other cages are still processed."""
        yesterday = self.today - timedelta(days=1)
        short = self._feed_log(self.cage, [(self.feed, 5000)], date=yesterday)
        fine = self._feed_log(self.cage, [(self.grit, 10)], date=yesterday)
        self.env['farm.feed.log']._cron_reconcile_unharvested_feed()
        self.assertEqual(short.state, 'confirmed')
        self.assertTrue(any('could not be expensed' in (m.body or '') for m in short.message_ids))
        self.assertEqual(fine.state, 'reconciled')
