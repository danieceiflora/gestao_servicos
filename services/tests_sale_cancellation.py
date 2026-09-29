from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from django.urls import reverse

from pagamentos.models import GatewayCharge, PosChargeAttempt
from pagamentos.settlement import apply_charge_status
from services.models import Billing, Installment, Sale, SaleItem, SalePayment, StockMovement, User
from services.sale_cancellation import cancel_sale, lock_open_installment
from services.tests_pos_payments import PaymentFixtures


class SaleCancellationTests(PaymentFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.sale = Sale.objects.create(client=self.customer, user=self.user, status='RASCUNHO', total_amount=150, stock_reduced=True)
        Sale.objects.filter(pk=self.sale.pk).update(status='FINALIZADA')
        self.sale.refresh_from_db()
        SaleItem.objects.create(sale=self.sale, product=self.product, quantity=1, unit_price=150)
        self.billing = Billing.objects.create(sale=self.sale, client=self.customer, total_amount=150)
        self.inst = Installment.objects.create(billing=self.billing, amount=150, due_date=date.today(), installment_number=1, payment_method=self.pix)
        gateway_patch = patch('services.sale_cancellation.AsaasGateway')
        self.cancel_gateway = gateway_patch.start().return_value
        self.addCleanup(gateway_patch.stop)
        self.cancel_gateway.get_charge.side_effect = lambda external_id: self.result(amount=150, external_id=external_id)
        self.cancel_gateway.cancel_charge.return_value = True

    def charge(self, external_id='pay_cancel', status='PENDING', method='PIX'):
        return GatewayCharge.objects.create(installment=self.inst, config=self.config, payment_method=self.pix,
            external_id=external_id, status=status, method=method, amount=150, due_date=date.today())

    def assert_active(self):
        self.sale.refresh_from_db()
        self.billing.refresh_from_db()
        self.inst.refresh_from_db()
        self.assertNotEqual(self.sale.status, 'CANCELADO')
        self.assertNotEqual(self.billing.status, 'CANCELADO')
        self.assertNotEqual(self.inst.status, 'CANCELADO')
        self.assertFalse(StockMovement.objects.filter(product=self.product).exists())

    def test_cancel_multiple_pix_and_boleto_and_repeat(self):
        self.charge()
        self.charge('pay_boleto', 'OVERDUE', 'BOLETO')
        self.assertTrue(cancel_sale(self.sale.pk, self.user).success)
        self.sale.refresh_from_db()
        self.billing.refresh_from_db()
        self.inst.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual((self.sale.status, self.billing.status, self.inst.status), ('CANCELADO',) * 3)
        self.assertFalse(self.sale.stock_reduced)
        self.assertEqual(self.product.current_stock, 11)
        self.assertEqual(self.cancel_gateway.cancel_charge.call_count, 2)
        self.assertEqual(GatewayCharge.objects.filter(status='CANCELLED').count(), 2)
        self.assertTrue(cancel_sale(self.sale.pk, self.user).success)
        self.assertEqual(StockMovement.objects.filter(product=self.product).count(), 1)
        self.assertEqual(self.cancel_gateway.cancel_charge.call_count, 2)

    def test_cancel_without_gateway(self):
        self.assertTrue(cancel_sale(self.sale.pk, self.user).success)
        self.cancel_gateway.get_charge.assert_not_called()

    def test_cancel_without_billing_or_stock(self):
        self.billing.delete()
        self.sale.stock_reduced = False
        self.sale.save()
        self.assertTrue(cancel_sale(self.sale.pk, self.user).success)
        self.assertFalse(StockMovement.objects.exists())

    def test_manual_partial_receipt_blocks_before_gateway(self):
        self.charge()
        SalePayment.objects.create(venda=self.sale, installment=self.inst, metodo_pagamento=self.cash,
                                   valor_bruto=10, valor_tarifa=0, valor_liquido=10, data_previsao=date.today())
        self.assertFalse(cancel_sale(self.sale.pk, self.user).success)
        self.cancel_gateway.get_charge.assert_not_called()
        self.assert_active()

    def test_local_paid_gateway_blocks(self):
        self.charge(status='RECEIVED')
        self.assertFalse(cancel_sale(self.sale.pk, self.user).success)
        self.cancel_gateway.cancel_charge.assert_not_called()
        self.assert_active()

    def test_remote_receipt_is_committed_and_blocks_deletion(self):
        charge = self.charge()
        self.cancel_gateway.get_charge.return_value = self.result(status='RECEIVED', amount=150)
        self.cancel_gateway.get_charge.side_effect = None
        self.assertFalse(cancel_sale(self.sale.pk, self.user).success)
        self.cancel_gateway.cancel_charge.assert_not_called()
        self.assertEqual(SalePayment.objects.get(gateway_charge=charge).valor_bruto, 150)
        self.assert_active()

    def test_false_response_does_not_cancel_locally(self):
        self.charge()
        self.cancel_gateway.cancel_charge.return_value = False
        self.assertFalse(cancel_sale(self.sale.pk, self.user).success)
        self.assert_active()

    def test_partial_success_committed_then_retry_only_remaining(self):
        first = self.charge()
        second = self.charge('pay_second')
        self.cancel_gateway.cancel_charge.side_effect = [True, TimeoutError('timeout')]
        self.assertFalse(cancel_sale(self.sale.pk, self.user).success)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, 'CANCELLED')
        self.assertEqual(second.status, 'PENDING')
        self.assert_active()
        self.cancel_gateway.cancel_charge.reset_mock(side_effect=True)
        self.cancel_gateway.cancel_charge.return_value = True
        self.assertTrue(cancel_sale(self.sale.pk, self.user).success)
        self.cancel_gateway.cancel_charge.assert_called_once_with(second.external_id)

    def test_timeout_after_remote_delete_reconciles_on_retry(self):
        charge = self.charge()
        self.cancel_gateway.cancel_charge.side_effect = TimeoutError('timeout')
        self.assertFalse(cancel_sale(self.sale.pk, self.user).success)
        self.cancel_gateway.get_charge.side_effect = None
        self.cancel_gateway.get_charge.return_value = self.result(status='CANCELLED', amount=150)
        self.cancel_gateway.cancel_charge.reset_mock()
        self.assertTrue(cancel_sale(self.sale.pk, self.user).success)
        self.cancel_gateway.cancel_charge.assert_not_called()
        charge.refresh_from_db()
        self.assertEqual(charge.status, 'CANCELLED')

    def test_payment_wins_race_with_delete(self):
        charge = self.charge()
        self.cancel_gateway.get_charge.side_effect = [self.result(amount=150), self.result(status='RECEIVED', amount=150)]
        self.cancel_gateway.cancel_charge.return_value = False
        self.assertFalse(cancel_sale(self.sale.pk, self.user).success)
        self.assertTrue(SalePayment.objects.filter(gateway_charge=charge).exists())
        self.assert_active()

    def test_webhook_receipt_during_delete_is_preserved(self):
        charge = self.charge()
        def receive_then_delete(external_id):
            apply_charge_status(charge.pk, 'RECEIVED', 148)
            return True
        self.cancel_gateway.cancel_charge.side_effect = receive_then_delete
        self.assertFalse(cancel_sale(self.sale.pk, self.user).success)
        charge.refresh_from_db()
        self.assertEqual(charge.status, 'RECEIVED')
        self.assertTrue(SalePayment.objects.filter(gateway_charge=charge).exists())
        self.assert_active()

    def test_unknown_pos_emission_blocks(self):
        PosChargeAttempt.objects.create(installment=self.inst, state='UNKNOWN')
        self.cancel_gateway.find_charge_by_reference.return_value = None
        self.assertFalse(cancel_sale(self.sale.pk, self.user).success)
        self.assert_active()

    def test_already_cancelled_and_delayed_pending_event(self):
        charge = self.charge(status='CANCELLED')
        self.assertTrue(cancel_sale(self.sale.pk, self.user).success)
        self.cancel_gateway.cancel_charge.assert_not_called()
        apply_charge_status(charge.pk, 'PENDING')
        charge.refresh_from_db()
        self.assertEqual(charge.status, 'CANCELLED')

    def test_new_installment_operation_blocked_after_cancellation(self):
        cancel_sale(self.sale.pk, self.user)
        with transaction.atomic(), self.assertRaisesMessage(ValueError, 'cancelada'):
            lock_open_installment(self.inst.pk)

    def test_post_only_and_permissions_and_actual_detail_button(self):
        url = reverse('sale_cancel', kwargs={'number': self.sale.number})
        self.assertEqual(self.client.get(url).status_code, 405)
        detail = self.client.get(reverse('sale_detail', kwargs={'number': self.sale.number}))
        self.assertContains(detail, 'Cancelando…')
        self.assertContains(detail, url)
        user = User.objects.create_user(username='cannot-cancel', phone='')
        self.client.force_login(user)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assert_active()
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, 'CANCELADO')
