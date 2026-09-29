# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestTopFarmCore(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create Root Analytic Plans
        cls.plan_batch = cls.env['account.analytic.plan'].create({'name': 'Flock Batch Plan'})
        cls.plan_cage = cls.env['account.analytic.plan'].create({'name': 'Cage Row Plan'})

        # Create Analytic Accounts
        cls.analytic_batch_c01 = cls.env['account.analytic.account'].create({
            'name': 'Analytic Batch C-01',
            'plan_id': cls.plan_batch.id,
        })
        cls.analytic_cage_a01 = cls.env['account.analytic.account'].create({
            'name': 'Analytic Cage A-01',
            'plan_id': cls.plan_cage.id,
        })

        # Create Farm Hierarchy Locations
        cls.wh = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.today = fields.Date.context_today(cls.wh)
        cls.farm_loc = cls.env['stock.location'].create({
            'name': 'Farm 1',
            'usage': 'internal',
            'location_id': cls.wh.lot_stock_id.id,
            'farm_hierarchy_level': 'farm',
        })
        cls.batch_loc = cls.env['stock.location'].create({
            'name': 'Batch C-01',
            'usage': 'internal',
            'location_id': cls.farm_loc.id,
            'farm_hierarchy_level': 'batch',
            'chick_arrival_date': cls.today - timedelta(days=140),  # 20 weeks ago
            'farm_analytic_account_id': cls.analytic_batch_c01.id,
        })
        cls.cage_loc = cls.env['stock.location'].create({
            'name': 'Cage A-01',
            'usage': 'internal',
            'location_id': cls.batch_loc.id,
            'farm_hierarchy_level': 'cage',
            'farm_analytic_account_id': cls.analytic_cage_a01.id,
        })
        cls.mortality_loc = cls.env['stock.location'].create({
            'name': 'Mortality Loss',
            'usage': 'inventory',
        })
        cls.feed_consumption_loc = cls.env['stock.location'].create({
            'name': 'Feed Consumption',
            'usage': 'inventory',
        })

        cls.bird = cls.env['product.product'].create({
            'name': 'Layer Hen',
            'is_storable': True,
            'is_farm_bird': True,
            'standard_price': 2.5,
        })
        cls.feed = cls.env['product.product'].create({
            'name': 'Layer Mash',
            'is_storable': True,
            'standard_price': 0.5,
        })

        cls.farm_manager = new_test_user(cls.env, login='farm_manager', groups='top_farm_core.group_farm_manager')
        cls.farm_operator = new_test_user(cls.env, login='farm_operator', groups='top_farm_core.group_farm_user')

    def _run_move(self, product, qty, source, destination, **values):
        move = self.env['stock.move'].create({
            'product_id': product.id,
            'product_uom': product.uom_id.id,
            'product_uom_qty': qty,
            'location_id': source.id,
            'location_dest_id': destination.id,
            **values,
        })
        move._action_confirm()
        move._action_assign()
        move.quantity = qty
        move.picked = True
        move._action_done()
        return move

    def test_01_parent_batch_auto_resolution(self):
        """Verify cage automatically resolves its parent batch."""
        self.assertEqual(self.cage_loc.parent_batch_location_id, self.batch_loc)
        self.assertEqual(self.batch_loc.parent_batch_location_id, self.batch_loc)
        self.assertFalse(self.farm_loc.parent_batch_location_id)

    def test_01b_parent_batch_through_unclassified_row(self):
        """A cage under an unclassified row still finds the batch above the row."""
        row = self.env['stock.location'].create({'name': 'Row 1', 'location_id': self.batch_loc.id})
        cage = self.env['stock.location'].create({
            'name': 'Cage R1-01',
            'location_id': row.id,
            'farm_hierarchy_level': 'cage',
        })
        self.assertEqual(cage.parent_batch_location_id, self.batch_loc)

    def test_01c_moving_a_cage_follows_the_new_batch(self):
        """Re-parenting a cage re-resolves its batch, and its stage follows the new batch."""
        batch_c02 = self.env['stock.location'].create({
            'name': 'Batch C-02',
            'location_id': self.farm_loc.id,
            'farm_hierarchy_level': 'batch',
            'batch_stage': 'laying',
        })
        self.cage_loc.location_id = batch_c02
        self.assertEqual(self.cage_loc.parent_batch_location_id, batch_c02)
        self.assertEqual(self.cage_loc.batch_stage, 'laying')

    def test_02_orphan_cage_raises_validation_error(self):
        """Verify cage without a parent batch raises ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['stock.location'].create({
                'name': 'Orphan Cage',
                'usage': 'internal',
                'location_id': self.farm_loc.id,  # Farm 1 is not a batch!
                'farm_hierarchy_level': 'cage',
            })

    def test_02b_unclassifying_a_batch_orphans_its_cages(self):
        """A batch with cages under it cannot silently stop being a batch."""
        with self.assertRaises(ValidationError):
            self.batch_loc.farm_hierarchy_level = False
            self.env.flush_all()

    def test_03_flock_age_calculation(self):
        """Verify flock age calculation in weeks."""
        self.assertEqual(self.batch_loc.flock_age_weeks, 20.0)
        self.assertEqual(self.cage_loc.flock_age_weeks, 20.0)

    def test_04_analytic_distribution_format(self):
        """Verify the Odoo 19 multi-plan comma-separated analytic distribution key."""
        dist = self.cage_loc.get_analytic_distribution_for_cage()
        expected_key = f"{self.analytic_batch_c01.id},{self.analytic_cage_a01.id}"
        self.assertEqual(dist, {expected_key: 100.0})
        # On the batch itself only its own account is used, never "42,42"
        self.assertEqual(self.batch_loc.get_analytic_distribution_for_cage(),
                         {str(self.analytic_batch_c01.id): 100.0})

    def test_04b_same_plan_accounts_rejected(self):
        """Batch and cage accounts from one plan would collide on one column, so they are refused."""
        same_plan_account = self.env['account.analytic.account'].create({
            'name': 'Cage in Batch Plan',
            'plan_id': self.plan_batch.id,
        })
        with self.assertRaises(ValidationError):
            self.env['stock.location'].create({
                'name': 'Cage A-02',
                'location_id': self.batch_loc.id,
                'farm_hierarchy_level': 'cage',
                'farm_analytic_account_id': same_plan_account.id,
            })

    def test_05_stage_transition_propagation(self):
        """Verify transitioning batch to laying propagates to sub-cages."""
        self.assertEqual(self.batch_loc.batch_stage, 'pre_laying')
        self.assertEqual(self.cage_loc.batch_stage, 'pre_laying')
        self.assertFalse(self.farm_loc.batch_stage)
        self.assertFalse(self.wh.lot_stock_id.batch_stage, "Non-farm locations carry no flock stage")

        self.batch_loc.with_user(self.farm_manager).action_start_laying_phase()
        self.assertEqual(self.batch_loc.batch_stage, 'laying')
        self.assertEqual(self.cage_loc.batch_stage, 'laying')

        new_cage = self.env['stock.location'].create({
            'name': 'Cage A-03',
            'location_id': self.batch_loc.id,
            'farm_hierarchy_level': 'cage',
        })
        self.assertEqual(new_cage.batch_stage, 'laying', "A cage added later joins the flock's current stage")

        with self.assertRaises(UserError):
            self.batch_loc.with_user(self.farm_manager).action_start_laying_phase()

    def test_06_live_bird_count(self):
        """Birds in a cage count on the cage, its batch and its farm; feed is never counted."""
        self.env['stock.quant']._update_available_quantity(self.bird, self.cage_loc, 1000)
        self.env['stock.quant']._update_available_quantity(self.feed, self.cage_loc, 250)
        self.assertEqual(self.cage_loc.get_live_bird_count(), 1000)
        self.assertEqual(self.batch_loc.get_live_bird_count(), 1000)
        locations = self.farm_loc | self.batch_loc | self.cage_loc
        self.assertEqual(locations.mapped('live_bird_count'), [1000, 1000, 1000])

    def test_07_analytic_hook_scrap_from_cage(self):
        """An outgoing move from a cage creates ONE analytic line holding both plan columns."""
        self.env['stock.quant']._update_available_quantity(self.bird, self.cage_loc, 100)
        move = self._run_move(self.bird, 10, self.cage_loc, self.mortality_loc)
        line = move.analytic_account_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line[self.plan_batch._column_name()], self.analytic_batch_c01)
        self.assertEqual(line[self.plan_cage._column_name()], self.analytic_cage_a01)
        self.assertAlmostEqual(line.amount, -25.0)
        self.assertEqual(line.name, self.bird.display_name, "A move with no reference still names its line")

    def test_07a_analytic_hook_mortality_scrap(self):
        """A stock.scrap of dead birds from a cage is charged to the batch and the cage."""
        self.env['stock.quant']._update_available_quantity(self.bird, self.cage_loc, 100)
        scrap = self.env['stock.scrap'].create({
            'product_id': self.bird.id,
            'product_uom_id': self.bird.uom_id.id,
            'scrap_qty': 4,
            'location_id': self.cage_loc.id,
            'scrap_location_id': self.mortality_loc.id,
        })
        scrap.do_scrap()
        line = scrap.move_ids.analytic_account_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line[self.plan_batch._column_name()], self.analytic_batch_c01)
        self.assertEqual(line[self.plan_cage._column_name()], self.analytic_cage_a01)
        self.assertAlmostEqual(line.amount, -10.0)
        self.assertEqual(self.cage_loc.get_live_bird_count(), 96)

    def test_07b_analytic_hook_explicit_cage_on_feed_move(self):
        """Feed issued from the silo is charged to the cage stamped on the move."""
        silo = self.wh.lot_stock_id
        self.env['stock.quant']._update_available_quantity(self.feed, silo, 500)
        move = self._run_move(self.feed, 50, silo, self.feed_consumption_loc, farm_cage_location_id=self.cage_loc.id)
        line = move.analytic_account_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line[self.plan_cage._column_name()], self.analytic_cage_a01)
        self.assertAlmostEqual(line.amount, -25.0)

    def test_07b2_feed_for_two_cages_in_one_picking(self):
        """Two cage-stamped feed moves in one picking are not merged: each cage bears its own cost."""
        cage_a02 = self.env['stock.location'].create({
            'name': 'Cage A-02',
            'location_id': self.batch_loc.id,
            'farm_hierarchy_level': 'cage',
        })
        silo = self.wh.lot_stock_id
        self.env['stock.quant']._update_available_quantity(self.feed, silo, 500)
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.wh.int_type_id.id,
            'location_id': silo.id,
            'location_dest_id': self.feed_consumption_loc.id,
            'move_ids': [Command.create({
                'product_id': self.feed.id,
                'product_uom': self.feed.uom_id.id,
                'product_uom_qty': qty,
                'location_id': silo.id,
                'location_dest_id': self.feed_consumption_loc.id,
                'farm_cage_location_id': cage.id,
            }) for cage, qty in ((self.cage_loc, 50), (cage_a02, 40))],
        })
        picking.action_confirm()
        self.assertEqual(len(picking.move_ids), 2, "Moves for different cages must not be merged")
        picking.action_assign()
        picking.move_ids.picked = True
        picking.button_validate()
        lines = picking.move_ids.analytic_account_line_ids
        by_cage = {line[self.plan_cage._column_name()]: line.amount for line in lines}
        self.assertEqual(len(lines), 2)
        self.assertAlmostEqual(by_cage[self.analytic_cage_a01], -25.0)
        # Cage A-02 has no cage account of its own, so its line carries only the batch account
        batch_only = lines.filtered(lambda l: not l[self.plan_cage._column_name()])
        self.assertAlmostEqual(batch_only.amount, -20.0)
        self.assertEqual(batch_only[self.plan_batch._column_name()], self.analytic_batch_c01)

    def test_07c_incoming_moves_stay_untagged(self):
        """Birds or eggs arriving into a cage carry no analytic cost, even with a cage stamped."""
        supplier = self.env.ref('stock.stock_location_suppliers')
        move = self._run_move(self.bird, 10, supplier, self.cage_loc, farm_cage_location_id=self.cage_loc.id)
        self.assertFalse(move.analytic_account_line_ids)

    def test_08_security_access_rights(self):
        """Operators can read and edit locations but cannot delete them or start the laying phase."""
        self.assertEqual(self.cage_loc.with_user(self.farm_operator).live_bird_count, 0)
        with self.assertRaises(AccessError):
            self.batch_loc.with_user(self.farm_operator).action_start_laying_phase()
        with self.assertRaises(AccessError):
            self.cage_loc.with_user(self.farm_operator).unlink()
