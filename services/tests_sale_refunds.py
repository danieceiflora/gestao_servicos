from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.tz_utils import local_today
from pagamentos.models import GatewayCharge
from services.models import (
    Billing, Installment, Sale, SaleItem, SalePayment, SaleRefund, SaleRefundAttachment,
    SaleReturn, SaleReturnItem,
)
from services.sale_refunds import approve_return, record_refund_payment
from services.tests_pos_payments import PaymentFixtures


class SaleRefundTests(PaymentFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.sale = Sale.objects.create(client=self.customer, user=self.user, status='RASCUNHO', total_amount=150, stock_reduced=True)
        Sale.objects.filter(pk=self.sale.pk).update(status='FINALIZADA')
        self.sale.refresh_from_db()
        self.item = SaleItem.objects.create(sale=self.sale, product=self.product, quantity=1, unit_price=150)
        self.billing = Billing.objects.create(sale=self.sale, client=self.customer, total_amount=150)
        self.inst = Installment.objects.create(billing=self.billing, amount=150, due_date=date.today(), installment_number=1, payment_method=self.cash)

    def test_partial_return_reduces_receivable_and_creates_refund_only_for_excess(self):
        SalePayment.objects.create(venda=self.sale, installment=self.inst, metodo_pagamento=self.cash,
                                   valor_bruto=50, valor_tarifa=0, valor_liquido=50, data_previsao=date.today())
        ret = SaleReturn.objects.create(sale=self.sale, user=self.user, reason='Defeito', total_refund=150)
        SaleReturnItem.objects.create(sale_return=ret, sale_item=self.item, quantity=1, refund_amount=150, restock=True)
        refund = approve_return(ret.pk, self.user)
        self.inst.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.inst.amount, 50)
        self.assertEqual(refund.balance_reduction, 100)
        self.assertEqual(refund.due_amount, 50)
        self.assertEqual(self.product.current_stock, 11)
        with self.assertRaises(ValueError):
            approve_return(ret.pk, self.user)

    def test_payments_are_bounded_and_declaration_requires_payment(self):
        refund = SaleRefund.objects.create(sale=self.sale, kind=SaleRefund.Kind.CANCELLATION, due_amount=50, created_by=self.user)
        self.assertEqual(self.client.get(reverse('sale_refund_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('sale_refund_detail', args=[refund.pk])).status_code, 200)
        declaration = reverse('sale_refund_declaration', args=[refund.pk])
        self.assertEqual(self.client.get(declaration).status_code, 302)
        record_refund_payment(refund.pk, amount=Decimal('20'), method='PIX', paid_at=date.today(), reference='pix-1', notes='', user=self.user)
        self.assertEqual(refund.status, 'PARCIAL')
        self.assertContains(self.client.get(declaration), 'R$ 20,00')
        with self.assertRaises(ValueError):
            record_refund_payment(refund.pk, amount=Decimal('31'), method='PIX', paid_at=date.today(), reference='', notes='', user=self.user)
        record_refund_payment(refund.pk, amount=Decimal('30'), method='DINHEIRO', paid_at=date.today(), reference='', notes='', user=self.user)
        self.assertEqual(refund.status, 'REALIZADO')

    def test_brazilian_currency_input_is_accepted_by_refund_form(self):
        refund = SaleRefund.objects.create(sale=self.sale, kind=SaleRefund.Kind.CANCELLATION,
                                           due_amount=Decimal('2000.00'), created_by=self.user)
        page = self.client.get(reverse('sale_refund_detail', args=[refund.pk]))
        self.assertContains(page, 'data-currency-br')
        response = self.client.post(reverse('sale_refund_pay', args=[refund.pk]), {
            'amount': '1.234,56', 'method': 'PIX', 'paid_at': date.today().isoformat(),
            'reference': 'pix-123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(refund.payments.get().amount, Decimal('1234.56'))

    def test_payment_date_is_displayed_and_accepted_in_brazilian_format(self):
        refund = SaleRefund.objects.create(sale=self.sale, kind=SaleRefund.Kind.CANCELLATION,
                                           due_amount=50, created_by=self.user)
        url = reverse('sale_refund_pay', args=[refund.pk])
        page = self.client.get(reverse('sale_refund_detail', args=[refund.pk]))
        self.assertContains(page, f'value="{local_today():%d/%m/%Y}"')
        self.assertContains(page, 'placeholder="dd/mm/aaaa"')
        response = self.client.post(url, {
            'amount': '20,00', 'method': 'PIX', 'paid_at': local_today().strftime('%d/%m/%Y'),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(refund.payments.get().paid_at, local_today())
        self.client.post(url, {
            'amount': '10,00', 'method': 'PIX', 'paid_at': '31/02/2026',
        })
        self.assertEqual(refund.payments.count(), 1)

    def test_attachment_card_precedes_payment_form_and_uses_portuguese_labels(self):
        refund = SaleRefund.objects.create(sale=self.sale, kind=SaleRefund.Kind.CANCELLATION,
                                           due_amount=50, created_by=self.user)
        content = self.client.get(reverse('sale_refund_detail', args=[refund.pk])).content.decode()
        self.assertLess(content.index('>Anexos</h2>'), content.index('>Registrar pagamento</h2>'))
        self.assertIn('Selecionar arquivos', content)
        self.assertIn('Nenhum arquivo selecionado', content)
        self.assertIn('Enviar arquivos', content)

    def test_attachment_delete_requires_post_and_removes_stored_file(self):
        refund = SaleRefund.objects.create(sale=self.sale, kind=SaleRefund.Kind.CANCELLATION,
                                           due_amount=50, created_by=self.user)
        attachment = SaleRefundAttachment.objects.create(
            refund=refund, file='sale_refunds/comprovante.pdf', original_name='comprovante.pdf',
            uploaded_by=self.user,
        )
        url = reverse('sale_refund_attachment_delete', args=[attachment.pk])
        page = self.client.get(reverse('sale_refund_detail', args=[refund.pk]))
        self.assertContains(page, url)
        self.assertContains(page, 'Excluir este arquivo anexado?')
        self.assertEqual(self.client.get(url).status_code, 405)
        with patch.object(attachment.file.storage, 'delete') as delete_file:
            response = self.client.post(url)
        self.assertRedirects(response, reverse('sale_refund_detail', args=[refund.pk]))
        delete_file.assert_called_once_with('sale_refunds/comprovante.pdf')
        self.assertFalse(SaleRefundAttachment.objects.filter(pk=attachment.pk).exists())

    def test_historical_review_accepts_brazilian_currency(self):
        ret = SaleReturn.objects.create(sale=self.sale, user=self.user, reason='Antiga',
                                        status=SaleReturn.Status.APROVADA, total_refund=150)
        refund = SaleRefund.objects.create(sale=self.sale, sale_return=ret, kind=SaleRefund.Kind.RETURN,
                                           due_amount=150, review_required=True, created_by=self.user)
        response = self.client.post(reverse('sale_refund_review', args=[refund.pk]), {'due_amount': '120,50'})
        self.assertEqual(response.status_code, 302)
        refund.refresh_from_db()
        self.assertEqual(refund.due_amount, Decimal('120.50'))
        self.assertFalse(refund.review_required)

    def test_cancellation_after_approved_return_does_not_double_restock_or_refund(self):
        SalePayment.objects.create(venda=self.sale, installment=self.inst, metodo_pagamento=self.cash,
                                   valor_bruto=150, valor_tarifa=0, valor_liquido=150, data_previsao=date.today())
        ret = SaleReturn.objects.create(sale=self.sale, user=self.user, reason='Defeito', total_refund=150)
        SaleReturnItem.objects.create(sale_return=ret, sale_item=self.item, quantity=1, refund_amount=150, restock=True)
        approve_return(ret.pk, self.user)
        from services.sale_cancellation import cancel_sale
        with patch('services.sale_cancellation.AsaasGateway'):
            self.assertTrue(cancel_sale(self.sale.pk, self.user).success)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, 11)
        self.assertEqual(SaleRefund.objects.filter(sale=self.sale).count(), 1)

    def test_return_cancels_gateway_charge_before_reducing_receivable(self):
        charge = GatewayCharge.objects.create(
            installment=self.inst, config=self.config, payment_method=self.pix,
            external_id='pay_return', status='PENDING', method='PIX', amount=150, due_date=date.today(),
        )
        ret = SaleReturn.objects.create(sale=self.sale, user=self.user, reason='Desistência', total_refund=150)
        SaleReturnItem.objects.create(sale_return=ret, sale_item=self.item, quantity=1, refund_amount=150)
        with patch('services.sale_refunds.AsaasGateway') as gateway_type:
            gateway = gateway_type.return_value
            gateway.get_charge.return_value = self.result(amount=150, external_id='pay_return')
            gateway.cancel_charge.return_value = True
            refund = approve_return(ret.pk, self.user)
        charge.refresh_from_db()
        self.inst.refresh_from_db()
        self.assertEqual(charge.status, 'CANCELLED')
        self.assertEqual(self.inst.status, 'CANCELADO')
        self.assertEqual(refund.due_amount, 0)

    def test_return_gateway_failure_keeps_return_pending(self):
        GatewayCharge.objects.create(
            installment=self.inst, config=self.config, payment_method=self.pix,
            external_id='pay_return', status='PENDING', method='PIX', amount=150, due_date=date.today(),
        )
        ret = SaleReturn.objects.create(sale=self.sale, user=self.user, reason='Desistência', total_refund=150)
        SaleReturnItem.objects.create(sale_return=ret, sale_item=self.item, quantity=1, refund_amount=150)
        with patch('services.sale_refunds.AsaasGateway') as gateway_type:
            gateway = gateway_type.return_value
            gateway.get_charge.return_value = self.result(amount=150, external_id='pay_return')
            gateway.cancel_charge.return_value = False
            with self.assertRaises(ValueError):
                approve_return(ret.pk, self.user)
        ret.refresh_from_db()
        self.inst.refresh_from_db()
        self.assertEqual(ret.status, 'PENDENTE')
        self.assertEqual(self.inst.amount, 150)

    def test_return_value_includes_sale_level_discount(self):
        self.sale.discount = 50
        self.sale.total_amount = 100
        self.sale.save(update_fields=['discount', 'total_amount'])
        response = self.client.post(reverse('sale_return_create', args=[self.sale.number]), {
            'reason': 'Defeito', 'item_id[]': [str(self.item.pk)],
            'quantity[]': ['1'], 'restock[]': [str(self.item.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SaleReturn.objects.get(sale=self.sale).total_refund, 100)
