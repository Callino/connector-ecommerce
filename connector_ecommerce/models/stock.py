# -*- coding: utf-8 -*-
# © 2013-2015 Camptocamp
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from openerp import models, fields, api

from openerp.addons.connector.session import ConnectorSession
from .event import on_picking_out_done, on_tracking_number_added, on_product_qty
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    related_backorder_ids = fields.One2many(
        comodel_name='stock.picking',
        inverse_name='backorder_id',
        string="Related backorders",
    )

    @api.multi
    def write(self, vals):
        res = super(StockPicking, self).write(vals)
        if vals.get('carrier_tracking_ref'):
            session = ConnectorSession.from_env(self.env)
            for record_id in self.ids:
                on_tracking_number_added.fire(session, self._name, record_id)
        return res

    @api.multi
    def do_transfer(self):
        # The key in the context avoid the event to be fired in
        # StockMove.action_done(). Allow to handle the partial pickings
        self_context = self.with_context(__no_on_event_out_done=True)
        result = super(StockPicking, self_context).do_transfer()
        session = ConnectorSession.from_env(self.env)
        for picking in self:
            if picking.picking_type_id.code != 'outgoing':
                continue
            if picking.related_backorder_ids:
                method = 'partial'
            else:
                method = 'complete'
            on_picking_out_done.fire(session, 'stock.picking',
                                     picking.id, method)

        return result


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.multi
    def action_done(self):
        _logger.info("in stock.move action_done")
        session = ConnectorSession.from_env(self.env)
        fire_event = not self.env.context.get('__no_on_event_out_done')
        if fire_event:
            pickings = self.mapped('picking_id')
            states = {p.id: p.state for p in pickings}

        result = super(StockMove, self).action_done()

        if fire_event:
            # Do fire the on_move_done event every time - to be able to track stock value !
            for move in self:
                on_product_qty.fire(session, 'product.product',
                                    move.product_id.id)

        if fire_event:
            _logger.info("do fire an event")
            for picking in pickings:
                _logger.info("do fire an event for picking %r", picking)
                if states[picking.id] != 'done' and picking.state == 'done':
                    if picking.picking_type_id.code != 'outgoing':
                        continue
                    # partial pickings are handled in
                    # StockPicking.do_transfer()
                    on_picking_out_done.fire(session, 'stock.picking',
                                             picking.id, 'complete')

        return result

    @api.multi
    def write(self, vals):
        fire_event = not self.env.context.get('__no_on_event_out_done')
        res = super(StockMove, self).write(vals)
        if fire_event:
            session = ConnectorSession.from_env(self.env)
            # Do fire the on_move_done event every time - to be able to track stock value !
            for move in self:
                on_product_qty.fire(session, 'product.product',
                                    move.product_id.id)
        return res

    @api.multi
    def create(self, vals):
        fire_event = not self.env.context.get('__no_on_event_out_done')
        res = super(StockMove, self).create(vals)
        if fire_event:
            session = ConnectorSession.from_env(self.env)
            # Do fire the on_move_done event every time - to be able to track stock value !
            on_product_qty.fire(session, 'product.product',
                                res.product_id.id)
        return res

