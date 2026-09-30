import json
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from pagamentos.gateways.base import ChargeResult, ChargeRejected
from pagamentos.models import GatewayCharge, GatewayConfig, PosChargeAttempt
from pagamentos.settlement import apply_charge_status
from services.models import (
    Billing, CashRegister, CashSession, Client, Installment, PaymentMethod,
    Product, Sale, SalePayment, StockMovement, User,
)
from services.pos_payments import start_checkout, ensure_pix, replace_part, cancel_checkout


class PaymentFixtures:
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username='pix-caixa', role=User.Roles.MANAGER, phone='')
        self.customer = Client.objects.create(name='Cliente PIX', cpf='52998224725')
        self.register = CashRegister.objects.create(code='PIX01', name='Caixa PIX')
        self.session = CashSession.objects.create(register=self.register, operator=self.user)
        self.product = Product.objects.create(name='Produto', code='PIX01', default_unit_price=Decimal('150'), current_stock=10)
        self.cash = PaymentMethod.objects.create(descricao='Dinheiro', tipo_provedor='DINHEIRO', codigo_sefaz='01')
        self.pix = PaymentMethod.objects.create(descricao='PIX no caixa', tipo_provedor='PIX', codigo_sefaz='17',
                                               pix_type='DYNAMIC', integra_gateway=True, pos_behavior='WAIT_GATEWAY')
        self.boleto = PaymentMethod.objects.create(descricao='Boleto híbrido', tipo_provedor='BOLETO', codigo_sefaz='15',
                                                  integra_gateway=True, public_billing_enabled=True)
        self.config = GatewayConfig.load()
        self.config.status = 'APPROVED'
        self.config.pix_enabled = self.config.boleto_enabled = True
        self.config.accept_current_fee_terms()
        self.config.save()
        self.client.force_login(self.user)
        self.gateway_patch = patch('services.pos_payments.AsaasGateway')
        self.gateway = self.gateway_patch.start().return_value
        self.addCleanup(self.gateway_patch.stop)
        self.gateway.create_charge.side_effect = lambda data, **kwargs: self.result(
            amount=data.amount, external_id=f'pay_{data.external_reference}',
        )

    def result(self, status='PENDING', amount=Decimal('100'), external_id='pay_test'):
        return ChargeResult(external_id=external_id, status=status, method='PIX', amount=Decimal(amount),
                            due_date=date.today(), pix_copy_paste='pix-test-code', pix_qrcode='cGl4', net_value=Decimal(amount)-Decimal('2.50'))

    def payload(self, payments=None, **changes):
        payload = {
            'session_id': self.session.pk, 'client_id': str(self.customer.pk), 'checkout_key': str(uuid.uuid4()),
            'items': [{'product_id': self.product.pk, 'quantity': '1', 'discount': '0'}],
            'payments': payments if payments is not None else [
                {'method_id': self.cash.pk, 'amount': '50', 'tendered': '50'},
                {'method_id': self.pix.pk, 'amount': '100', 'tendered': '100'},
            ],
        }
        payload.update(changes)
        return payload

    def start(self, payload=None):
        sale = start_checkout(payload or self.payload(), self.user)
        ensure_pix(sale.pk)
        return sale

    def post(self, name, payload, args=None):
        return self.client.post(reverse(name, args=args), json.dumps(payload), content_type='application/json')


class PosPixTests(PaymentFixtures, TestCase):
    def test_manual_pos_payment_uses_fee_snapshot(self):
        self.cash.tarifa_porcentagem = Decimal('2')
        self.cash.tarifa_minima = Decimal('2.50')
        self.cash.tarifa_maxima = Decimal('10')
        self.cash.tarifa_fixa = Decimal('1')
        self.cash.save()
        sale = self.start(self.payload(payments=[
            {'method_id': self.cash.pk, 'amount': '150', 'tendered': '150'},
        ]))
        payment = sale.payments.get()
        self.assertEqual(payment.valor_tarifa, Decimal('4.00'))
        self.assertEqual(payment.valor_liquido, Decimal('146.00'))
        self.assertEqual(payment.fee_terms['maximum'], '10.00')

    def test_mixed_payment_waits_then_settles_once_and_reduces_stock_once(self):
        sale = self.start()
        self.assertEqual(sale.status, 'AGUARDANDO_PAGAMENTO')
        self.assertEqual(sale.billing.get_total_paid(), Decimal('50'))
        self.assertFalse(StockMovement.objects.filter(product=self.product).exists())
        charge = GatewayCharge.objects.get()
        apply_charge_status(charge.pk, 'CONFIRMED', '97.50')
        apply_charge_status(charge.pk, 'RECEIVED', '97.50')
        apply_charge_status(charge.pk, 'PENDING')
        sale.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(sale.status, 'FINALIZADA')
        self.assertEqual(self.product.current_stock, 9)
        self.assertEqual(sale.payments.count(), 2)
        self.assertEqual(sale.cash_movements.count(), 2)
        self.assertEqual(sale.billing.get_remaining_balance(), 0)
        self.assertEqual(sale.billing.installments.count(), 2)
        self.assertEqual(charge.settlement.metodo_pagamento, self.pix)
        self.assertEqual(charge.settlement.cash_session, self.session)

    def test_start_retries_reuse_sale_payments_and_charge(self):
        payload = self.payload()
        sale = self.start(payload)
        retry = self.start(payload)
        self.assertEqual(sale.pk, retry.pk)
        self.assertEqual(self.gateway.create_charge.call_count, 1)
        self.assertEqual(sale.payments.count(), 1)

    def test_multiple_pix_parts_wait_for_all_confirmations(self):
        sale = self.start(self.payload(payments=[
            {'method_id': self.pix.pk, 'amount': '50'}, {'method_id': self.pix.pk, 'amount': '100'},
        ]))
        charges = list(GatewayCharge.objects.order_by('pk'))
        apply_charge_status(charges[0].pk, 'RECEIVED')
        sale.refresh_from_db()
        self.assertEqual(sale.status, 'AGUARDANDO_PAGAMENTO')
        apply_charge_status(charges[1].pk, 'RECEIVED')
        sale.refresh_from_db()
        self.assertEqual(sale.status, 'FINALIZADA')

    def test_unknown_generation_is_reconciled_without_reissuing(self):
        self.gateway.create_charge.side_effect = TimeoutError('timeout')
        sale = self.start()
        attempt = PosChargeAttempt.objects.get()
        self.assertEqual(attempt.state, 'UNKNOWN')
        ensure_pix(sale.pk)
        self.gateway.find_charge_by_reference.return_value = self.result()
        ensure_pix(sale.pk, reconcile=True)
        self.assertEqual(self.gateway.create_charge.call_count, 1)
        self.assertEqual(GatewayCharge.objects.count(), 1)
        self.gateway.find_charge_by_reference.assert_called_once_with(str(attempt.reference))

    def test_uncertain_charge_cannot_be_replaced_or_duplicated(self):
        self.gateway.create_charge.side_effect = TimeoutError('timeout')
        sale = self.start()
        inst = sale.billing.installments.get(pos_payment_behavior='WAIT_GATEWAY')
        with self.assertRaisesMessage(ValueError, 'conciliada'):
            replace_part(sale.pk, inst.pk, [{'method_id': self.cash.pk, 'amount': '100'}])
        self.assertEqual(sale.payments.count(), 1)

    def test_rejected_generation_can_be_retried(self):
        self.gateway.create_charge.side_effect = ChargeRejected('invalid')
        sale = self.start()
        self.assertEqual(PosChargeAttempt.objects.get().state, 'REJECTED')
        self.gateway.create_charge.side_effect = None
        self.gateway.create_charge.return_value = self.result()
        ensure_pix(sale.pk, reconcile=True)
        self.assertEqual(GatewayCharge.objects.count(), 1)

    def test_replace_pending_pix_preserves_received_cash(self):
        sale = self.start()
        inst = sale.billing.installments.get(pos_payment_behavior='WAIT_GATEWAY')
        self.gateway.get_charge.return_value = self.result()
        self.gateway.cancel_charge.return_value = True
        replace_part(sale.pk, inst.pk, [{'method_id': self.cash.pk, 'amount': '100', 'tendered': '120'}])
        inst.refresh_from_db()
        sale.refresh_from_db()
        self.assertEqual(inst.status, 'CANCELADO')
        self.assertEqual(sale.status, 'FINALIZADA')
        self.assertEqual(sale.payments.count(), 2)
        self.assertEqual(sale.billing.get_total_paid(), 150)
        self.assertEqual(sale.billing.get_remaining_balance(), 0)
        self.assertEqual(GatewayCharge.objects.get().status, 'CANCELLED')

    def test_payment_wins_race_against_replacement(self):
        sale = self.start()
        inst = sale.billing.installments.get(pos_payment_behavior='WAIT_GATEWAY')
        self.gateway.get_charge.return_value = self.result('RECEIVED')
        replace_part(sale.pk, inst.pk, [{'method_id': self.cash.pk, 'amount': '100'}])
        self.gateway.cancel_charge.assert_not_called()
        self.assertEqual(sale.billing.installments.count(), 2)
        self.assertEqual(sale.payments.count(), 2)
        self.assertEqual(sale.payments.filter(metodo_pagamento=self.cash).count(), 1)

    def test_cannot_cancel_received_parts(self):
        sale = self.start()
        with self.assertRaisesMessage(ValueError, 'recebimentos'):
            cancel_checkout(sale.pk)
        self.gateway.cancel_charge.assert_not_called()

    def test_cancels_unpaid_checkout_without_stock_movement(self):
        sale = self.start(self.payload(payments=[{'method_id': self.pix.pk, 'amount': '150'}]))
        self.gateway.get_charge.return_value = self.result(amount='150')
        self.gateway.cancel_charge.return_value = True
        cancelled = cancel_checkout(sale.pk)
        self.assertEqual(cancelled.status, 'CANCELADO')
        self.assertFalse(StockMovement.objects.filter(product=self.product).exists())

    def test_requires_identified_customer_and_does_not_record_cash_on_invalid_request(self):
        response = self.post('pos_payment_start', self.payload(client_id=''))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SalePayment.objects.exists())
        self.assertFalse(Sale.objects.exists())
        self.gateway.create_charge.assert_not_called()

    def test_cash_receipt_and_deferred_method_still_work(self):
        deferred = PaymentMethod.objects.create(descricao='Crediário', tipo_provedor='CREDIARIO', codigo_sefaz='99', pos_behavior='RECEIVABLE')
        sale = self.start(self.payload(payments=[
            {'method_id': self.cash.pk, 'amount': '50'}, {'method_id': deferred.pk, 'amount': '100'},
        ]))
        self.assertEqual(sale.status, 'FINALIZADA')
        self.assertEqual(sale.billing.get_remaining_balance(), 100)
        self.gateway.create_charge.assert_not_called()

    def test_pending_checkout_is_recovered_and_blocks_new_sales_close_and_receipt(self):
        sale = self.start()
        self.assertEqual(self.client.get(reverse('pos_home')).context['pending_checkout_id'], sale.pk)
        self.assertEqual(self.client.get(reverse('pos_payment_status', args=[sale.pk])).json()['parts'][1]['copy_paste'], 'pix-test-code')
        self.assertEqual(self.post('pos_payment_start', self.payload()).status_code, 400)
        self.client.post(reverse('pos_close'), {'session_id': self.session.pk})
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'OPEN')
        self.assertEqual(self.client.get(reverse('pos_receipt', args=[sale.number])).status_code, 403)

    def test_another_operator_cannot_read_or_modify_checkout(self):
        sale = self.start()
        other = User.objects.create_user(username='other', role=User.Roles.MANAGER, phone='')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('pos_payment_status', args=[sale.pk])).status_code, 404)
        self.assertEqual(self.post('pos_payment_verify', {}, [sale.pk]).status_code, 404)

    def test_legacy_finalize_cannot_mark_dynamic_pix_received(self):
        payload = self.payload()
        payload['action'] = 'finalize'
        response = self.post('pos_save_sale', payload)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SalePayment.objects.exists())

    def test_real_webhook_repeated_events_are_idempotent(self):
        sale = self.start()
        charge = GatewayCharge.objects.get()
        for event in ('PAYMENT_CONFIRMED', 'PAYMENT_RECEIVED', 'PAYMENT_RECEIVED'):
            response = self.post('pagamentos:asaas_webhook', {'event': event, 'payment': {
                'id': charge.external_id, 'value': 100, 'netValue': 97.5,
            }})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(sale.payments.count(), 2)
        self.assertEqual(sale.cash_movements.count(), 2)

    def test_confirmation_before_creation_response_is_not_lost(self):
        sale = start_checkout(self.payload(), self.user)
        def create(data, **kwargs):
            response = self.post('pagamentos:asaas_webhook', {'event': 'PAYMENT_RECEIVED', 'payment': {
                'id': 'early-pix', 'value': 100, 'netValue': 97.5,
                'billingType': 'PIX', 'externalReference': data.external_reference,
            }})
            self.assertEqual(response.status_code, 200)
            return self.result(external_id='early-pix')
        self.gateway.create_charge.side_effect = create
        ensure_pix(sale.pk)
        sale.refresh_from_db()
        self.assertEqual(sale.status, 'FINALIZADA')
        self.assertEqual(GatewayCharge.objects.count(), 1)
        self.assertEqual(sale.payments.count(), 2)
        self.assertEqual(GatewayCharge.objects.get().status, 'RECEIVED')

    def test_completed_checkout_can_be_recovered_after_lost_response(self):
        payload = self.payload(payments=[{'method_id': self.cash.pk, 'amount': '150'}])
        sale = self.start(payload)
        response = self.client.get(reverse('pos_payment_recover', args=[payload['checkout_key']]))
        self.assertEqual(response.json()['sale_id'], sale.pk)
        self.assertTrue(response.json()['finalized'])


class PublicPaymentChannelTests(PaymentFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.billing = Billing.objects.create(client=self.customer, total_amount=150)
        self.installment = Installment.objects.create(billing=self.billing, amount=150, installment_number=1, due_date=date.today())
        self.url = reverse('public_billing_page', args=[self.billing.public_token])
        self.generate = reverse('public_billing_generate_charge', args=[self.billing.public_token])

    def test_public_page_only_offers_allowed_boleto(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Boleto híbrido')
        self.assertNotContains(response, 'PIX no caixa')
        self.assertFalse(response.context['pix_available'])
        self.assertTrue(response.context['boleto_available'])

    @patch('pagamentos.gateways.asaas.AsaasGateway.create_charge')
    def test_public_endpoint_rejects_pix_even_with_manipulated_method_id(self, create):
        response = self.client.post(self.generate, {'installment_id': self.installment.pk, 'method': 'BOLETO', 'payment_method_id': self.pix.pk})
        self.assertContains(response, 'não disponível neste link')
        create.assert_not_called()

    @patch('pagamentos.gateways.asaas.AsaasGateway.create_charge')
    def test_generated_boleto_keeps_selected_method(self, create):
        create.return_value = ChargeResult(external_id='boleto1', status='PENDING', method='BOLETO', amount=Decimal('150'), due_date=date.today())
        response = self.client.post(self.generate, {'installment_id': self.installment.pk, 'method': 'BOLETO', 'payment_method_id': self.boleto.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(GatewayCharge.objects.get().payment_method, self.boleto)

    @patch('pagamentos.gateways.asaas.AsaasGateway.create_charge')
    def test_legacy_request_requires_unique_eligible_method(self, create):
        PaymentMethod.objects.create(descricao='Outro boleto', tipo_provedor='BOLETO', codigo_sefaz='15', integra_gateway=True, public_billing_enabled=True)
        response = self.client.post(self.generate, {'installment_id': self.installment.pk, 'method': 'BOLETO'})
        self.assertContains(response, 'não disponível neste link')
        create.assert_not_called()

    def test_existing_pix_remains_visible(self):
        GatewayCharge.objects.create(installment=self.installment, config=self.config, external_id='old_pix', method='PIX', amount=150,
                                     due_date=date.today(), pix_copy_paste='existing-pix-code')
        self.assertContains(self.client.get(self.url), 'existing-pix-code')

    def test_legacy_discounted_settlement_keeps_paid_billing_status(self):
        charge = GatewayCharge.objects.create(
            installment=self.installment, payment_method=self.boleto, config=self.config,
            external_id='discounted', method='BOLETO', amount=140, due_date=date.today(),
        )
        apply_charge_status(charge.pk, 'RECEIVED', '137.50')
        self.billing.refresh_from_db()
        self.assertEqual(self.billing.status, 'PAGO')

    def test_disabled_static_pix_does_not_leak_through_fallback(self):
        self.boleto.public_billing_enabled = False
        self.boleto.save()
        method = PaymentMethod.objects.create(descricao='Chave privada', tipo_provedor='PIX', codigo_sefaz='17', pix_type='STATIC', pix_key='private-key')
        self.installment.payment_method = method
        self.installment.save()
        self.assertNotContains(self.client.get(self.url), 'private-key')

    def test_public_cannot_generate_alternative_charge_for_pending_pos(self):
        sale = self.start()
        inst = sale.billing.installments.get(pos_payment_behavior='WAIT_GATEWAY')
        response = self.client.post(reverse('public_billing_generate_charge', args=[sale.billing.public_token]), {
            'installment_id': inst.pk, 'method': 'BOLETO', 'payment_method_id': self.boleto.pk,
        })
        self.assertContains(response, 'atendido no caixa')
        self.assertEqual(GatewayCharge.objects.count(), 1)
