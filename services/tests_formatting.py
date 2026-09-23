from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase

from core.formatting import decimal_from_display, format_money_br
from integracoes.utils import format_notification_value
from services.models import Installment, Sale


class BrazilianMoneyFormattingTests(SimpleTestCase):
    def test_python_formatter_uses_brazilian_thousands_and_decimals(self):
        self.assertEqual(format_money_br(Decimal('1234567.5')), '1.234.567,50')
        self.assertEqual(format_money_br(Decimal('-1000.5'), include_symbol=True), 'R$ -1.000,50')
        self.assertEqual(format_money_br(0), '0,00')
        self.assertEqual(format_money_br(None), '')

    def test_parser_accepts_canonical_and_brazilian_values(self):
        self.assertEqual(decimal_from_display('1234.50'), Decimal('1234.50'))
        self.assertEqual(decimal_from_display('R$ 1.234,50'), Decimal('1234.50'))

    def test_template_localization_and_filters_group_thousands(self):
        rendered = Template(
            '{{ value|floatformat:2 }}|{{ value|money_br }}|{{ value|brl }}'
        ).render(Context({'value': Decimal('1234.5')}))
        self.assertEqual(rendered, '1.234,50|1.234,50|R$ 1.234,50')

    def test_notification_formats_only_known_monetary_paths(self):
        sale = Sale(total_amount=Decimal('1234.50'))
        installment = Installment(amount=Decimal('1234.50'))

        self.assertEqual(
            format_notification_value(sale, 'total_amount', sale.total_amount),
            '1.234,50',
        )
        self.assertEqual(
            format_notification_value(installment, 'discount_value', Decimal('10.50')),
            '10.50',
        )
