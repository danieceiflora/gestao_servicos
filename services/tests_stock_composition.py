"""Caracterização do estoque de produtos compostos (ficha técnica / BOM).

`Product.reduce_stock` consome os componentes de um produto COM_COMPOSICAO.
O estorno só é correto se for simétrico a isso — daí `explode_composition`.
Uma ENTRADA de verdade (nota de compra) não deve explodir a composição.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import (
    Product, ProductComposition, StockMovement, User,
)
from .utils.bom import explode_bom, find_composition_cycle


def make_product(name, **kwargs):
    kwargs.setdefault('current_stock', Decimal('100.0000'))
    kwargs.setdefault('default_unit_price', Decimal('10.00'))
    return Product.objects.create(name=name, **kwargs)


class CompositionStockTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', password='x')
        # Acabado = 2 x Chapa + 3 x Parafuso
        self.chapa = make_product('Chapa', type=Product.Type.MATERIA_PRIMA)
        self.parafuso = make_product('Parafuso', type=Product.Type.MATERIA_PRIMA)
        self.acabado = make_product(
            'Calha Montada',
            type=Product.Type.PRODUTO_ACABADO,
            format=Product.Format.COM_COMPOSICAO,
        )
        ProductComposition.objects.create(parent=self.acabado, component=self.chapa, quantity=Decimal('2'))
        ProductComposition.objects.create(parent=self.acabado, component=self.parafuso, quantity=Decimal('3'))

    def stocks(self):
        return tuple(
            Product.objects.get(pk=p.pk).current_stock
            for p in (self.acabado, self.chapa, self.parafuso)
        )

    def test_reduce_consumes_components(self):
        self.acabado.reduce_stock(Decimal('5'), user=self.user, reason=StockMovement.Reason.VENDA_DIRETA, notes='teste')
        self.assertEqual(self.stocks(), (Decimal('95.0000'), Decimal('90.0000'), Decimal('85.0000')))

    def test_increase_without_flag_does_not_touch_components(self):
        """Entrada de compra: o acabado entra, os insumos não. Comportamento preservado."""
        self.acabado.increase_stock(Decimal('5'), user=self.user, reason=StockMovement.Reason.COMPRA, notes='teste')
        self.assertEqual(self.stocks(), (Decimal('105.0000'), Decimal('100.0000'), Decimal('100.0000')))

    def test_reversal_is_symmetric(self):
        before = self.stocks()
        self.acabado.reduce_stock(Decimal('5'), user=self.user, reason=StockMovement.Reason.VENDA_DIRETA, notes='teste')
        self.acabado.refresh_from_db()
        self.acabado.increase_stock(
            Decimal('5'), user=self.user, reason=StockMovement.Reason.DEVOLUCAO, notes='teste',
            explode_composition=True,
        )
        self.assertEqual(self.stocks(), before)

    def test_reversal_registers_movements_for_components(self):
        self.acabado.reduce_stock(Decimal('1'), user=self.user, reason=StockMovement.Reason.VENDA_DIRETA, notes='teste')
        self.acabado.refresh_from_db()
        self.acabado.increase_stock(
            Decimal('1'), user=self.user, reason=StockMovement.Reason.DEVOLUCAO, notes='teste',
            explode_composition=True,
        )
        entradas = StockMovement.objects.filter(movement_type=StockMovement.MovementType.ENTRADA)
        self.assertEqual(entradas.count(), 3)
        self.assertEqual(
            set(entradas.values_list('product__name', flat=True)),
            {'Calha Montada', 'Chapa', 'Parafuso'},
        )

    def test_nested_composition_multiplies(self):
        """Chapa passa a ser composta de 4 x Bobina: 2 x Chapa por acabado => 8 Bobina."""
        bobina = make_product('Bobina', type=Product.Type.MATERIA_PRIMA)
        self.chapa.format = Product.Format.COM_COMPOSICAO
        self.chapa.save(update_fields=['format'])
        ProductComposition.objects.create(parent=self.chapa, component=bobina, quantity=Decimal('4'))

        self.acabado.reduce_stock(Decimal('1'), user=self.user, reason=StockMovement.Reason.VENDA_DIRETA, notes='teste')
        bobina.refresh_from_db()
        self.assertEqual(bobina.current_stock, Decimal('92.0000'))


class CompositionCycleTests(TestCase):
    """Ciclos não são impedidos pelo banco: unique_together permite parent == component."""

    def setUp(self):
        self.a = make_product('A', format=Product.Format.COM_COMPOSICAO)
        self.b = make_product('B', format=Product.Format.COM_COMPOSICAO)

    def test_self_reference_rejected_by_clean(self):
        comp = ProductComposition(parent=self.a, component=self.a, quantity=Decimal('1'))
        with self.assertRaises(ValidationError):
            comp.full_clean()

    def test_indirect_cycle_rejected_by_clean(self):
        ProductComposition.objects.create(parent=self.a, component=self.b, quantity=Decimal('1'))
        comp = ProductComposition(parent=self.b, component=self.a, quantity=Decimal('1'))
        with self.assertRaises(ValidationError):
            comp.full_clean()
        self.assertIsNotNone(find_composition_cycle(self.b, self.a))

    def test_reduce_stock_survives_existing_cycle(self):
        """Dados legados podem já ter o ciclo gravado — não pode virar RecursionError."""
        ProductComposition.objects.bulk_create([
            ProductComposition(parent=self.a, component=self.b, quantity=Decimal('1')),
            ProductComposition(parent=self.b, component=self.a, quantity=Decimal('1')),
        ])
        self.a.reduce_stock(Decimal('1'), reason=StockMovement.Reason.VENDA_DIRETA, notes='teste')
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.current_stock, Decimal('99.0000'))
        self.assertEqual(self.b.current_stock, Decimal('99.0000'))

    def test_explode_bom_survives_existing_cycle(self):
        ProductComposition.objects.bulk_create([
            ProductComposition(parent=self.a, component=self.b, quantity=Decimal('1')),
            ProductComposition(parent=self.b, component=self.a, quantity=Decimal('1')),
        ])
        rows = explode_bom(self.a, Decimal('1'))
        self.assertEqual([(c.name, q) for c, q in rows], [('B', Decimal('1'))])

    def test_explode_bom_aggregates_shared_component(self):
        shared = make_product('Compartilhado', type=Product.Type.MATERIA_PRIMA)
        ProductComposition.objects.create(parent=self.a, component=self.b, quantity=Decimal('2'))
        ProductComposition.objects.create(parent=self.a, component=shared, quantity=Decimal('1'))
        ProductComposition.objects.create(parent=self.b, component=shared, quantity=Decimal('3'))
        rows = dict((c.name, q) for c, q in explode_bom(self.a, Decimal('1')))
        # 1 direto + (2 x B) x 3 = 7
        self.assertEqual(rows['Compartilhado'], Decimal('7'))
        self.assertEqual(rows['B'], Decimal('2'))

    def test_explode_bom_ignores_simple_product(self):
        simples = make_product('Simples')
        self.assertEqual(explode_bom(simples, Decimal('3')), [])
