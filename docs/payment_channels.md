# Métodos de pagamento por canal

Em **Métodos de pagamento**, `Disponível no link público de cobrança` autoriza novas operações pelo cliente. `Comportamento no PDV` controla o caixa. A habilitação no gateway continua sendo uma condição global da integração, sem liberar automaticamente o link público.

As migrações habilitam no link público apenas os boletos já cadastrados com integração. PIX começa desabilitado nesse canal. Métodos PIX dinâmicos disponíveis no PDV passam a aguardar confirmação do gateway. Não são criados métodos automaticamente; se nenhum boleto integrado estiver cadastrado, é necessário cadastrá-lo ou ajustar seu cadastro para oferecer boleto no link.

Cobranças anteriores continuam visíveis. O boleto é emitido como `BOLETO`; a presença do QR Code no documento depende da configuração PIX da conta Asaas emissora. Não é emitida uma segunda cobrança PIX para transformar o boleto em híbrido.

## PIX no PDV

- Selecione um cliente cadastrado com CPF/CNPJ e divida os pagamentos, se necessário.
- Ao iniciar o recebimento, os valores manuais informados são registrados como recebidos. O PIX integrado permanece pendente e mostra QR Code/copia e cola.
- O operador permanece nessa venda. Atualizar a página recupera o recebimento; o fechamento do caixa fica bloqueado enquanto ele estiver pendente.
- A confirmação por webhook ou **Verificar pagamento** registra o PIX, sem duplicar recebimento ou movimento de caixa. A venda é finalizada quando os pagamentos imediatos forem confirmados; partes em conta a receber permanecem em aberto.
- **Trocar forma deste saldo** cancela o PIX pendente antes de substituir sua parcela. Valores recebidos permanecem preservados. Uma venda com recebimentos não pode ser cancelada integralmente por esse fluxo.
- Estoque e comprovante são liberados na finalização, uma única vez. Estornos de valores recebidos não fazem parte desse fluxo.

## Falha na emissão

Cada tentativa é persistida antes da chamada ao Asaas, com referência única. Se a resposta se perder, **Verificar pagamento** procura a cobrança por essa referência. Uma tentativa incerta nunca emite outro PIX automaticamente. Se a cobrança não puder ser localizada, permanece bloqueada para conciliação no gateway; não se deve criar outra cobrança manualmente para contornar a verificação.

## Implantação e testes

Aplicar `python manage.py migrate` antes de disponibilizar o código, executar `python manage.py check` e `npm run build`. Em desenvolvimento, usar o Python do `venv` do projeto e `DEBUG=True`.

Testes de backend: `python manage.py test services.tests_pos_payments services.tests_payment_method_pix services.tests.PosCheckoutTests pagamentos.tests`.

Testes de navegador: `python manage.py test services.browser_payment_checks`. Usam Playwright/Chromium, banco de teste e gateway simulado, sem cobranças reais. Os bloqueios de linha usam `select_for_update` no PostgreSQL; o SQLite de desenvolvimento não reproduz a concorrência de produção.
