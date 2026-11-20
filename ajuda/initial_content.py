"""Guias oficiais versionados, revisados no código em 14/11/2026.

Fontes: CLAUDE.md; core/services/producao/fiscal/integracoes urls;
services/views*.py; fiscal/views.py; templates/services, templates/producao;
static/js/offline-app.js e offline-db.js. Revisão de código, não homologação
operacional nem aconselhamento fiscal. Não há mídia demonstrativa inventada.
Alterações aqui só chegam ao banco pelo comando explícito sync_help_content.
"""

import json
from pathlib import Path

REVIEWED_AT = "2026-11-14"
CONTENT_VERSION = 2

CATEGORIES = [
    {"slug": "primeiros-passos", "name": "Primeiros passos", "description": "Prepare os cadastros e conheça o fluxo de trabalho.", "icon": "compass", "module": "geral", "sort_order": 10},
    {"slug": "clientes", "name": "Clientes e imóveis", "description": "Identificação, contatos e locais de atendimento.", "icon": "users", "module": "clientes", "sort_order": 20},
    {"slug": "ordens-de-servico", "name": "Ordens de serviço", "description": "Agendamento, orçamento, etapas e acompanhamento da OS.", "icon": "clipboard-list", "module": "os", "sort_order": 30},
    {"slug": "app-tecnico", "name": "App do técnico", "description": "Agenda, execução, evidências e sincronização em campo.", "icon": "smartphone", "module": "tecnico", "sort_order": 40},
    {"slug": "vendas", "name": "Vendas", "description": "Itens, rascunhos e conferência de vendas.", "icon": "shopping-bag", "module": "vendas", "sort_order": 50},
    {"slug": "pdv", "name": "Frente de caixa", "description": "Sessões de caixa, recebimentos e fechamento.", "icon": "store", "module": "pdv", "sort_order": 60},
    {"slug": "estoque", "name": "Estoque", "description": "Produtos, entradas e rastreabilidade das movimentações.", "icon": "package", "module": "estoque", "sort_order": 70},
    {"slug": "financeiro", "name": "Financeiro", "description": "Cobranças, parcelas, recebimentos e despesas.", "icon": "wallet", "module": "financeiro", "sort_order": 80},
    {"slug": "producao", "name": "Produção e expedição", "description": "Preparação de itens, falta de material e saída.", "icon": "factory", "module": "producao", "sort_order": 90},
    {"slug": "manutencao", "name": "Manutenção", "description": "Equipamentos, contratos recorrentes e visitas.", "icon": "wrench", "module": "manutencao", "sort_order": 100},
    {"slug": "relatorios", "name": "Relatórios", "description": "Indicadores operacionais, produtividade e manutenção.", "icon": "chart-column", "module": "relatorios", "sort_order": 110},
    {"slug": "fiscal", "name": "Fiscal", "description": "Preparação e acompanhamento dos documentos fiscais.", "icon": "file-text", "module": "fiscal", "sort_order": 120},
    {"slug": "configuracoes", "name": "Configurações", "description": "Parâmetros por módulo e regras de mensagens.", "icon": "settings", "module": "configuracoes", "sort_order": 130},
]

ARTICLES = [
    {
        "category": "primeiros-passos", "slug": "preparar-primeiro-atendimento",
        "title": "Prepare o primeiro atendimento", "featured": True, "sort_order": 10,
        "summary": "Organize cliente, imóvel, equipe e itens antes de agendar uma OS.",
        "objective": "Começar com os cadastros necessários e saber onde acompanhar o serviço.",
        "prerequisites": "Acesso autenticado e permissões para os módulos utilizados. Para cadastrar equipe e produtos, peça apoio ao gestor quando necessário.",
        "content": "Uma OS reúne o atendimento de um imóvel; as etapas registram cada visita ou fase. Cliente, imóvel e equipe precisam corresponder ao trabalho real. O app do técnico apresenta as tarefas disponibilizadas para o profissional, não substitui a gestão dos cadastros.",
        "steps": [
            {"title": "Confira o cliente e o local", "content": "Em Clientes, procure o cadastro antes de criar outro. Confira telefone e o imóvel em que o atendimento ocorrerá."},
            {"title": "Prepare a equipe e o catálogo", "content": "Confira os profissionais ativos e os produtos ou serviços necessários. Verifique com o gestor as permissões e os métodos de pagamento disponíveis."},
            {"title": "Agende e acompanhe", "content": "Use Novo Agendamento no início ou no calendário. Depois de salvar, abra o detalhe da OS para conferir etapas e equipe. Oriente o técnico a carregar o app com internet antes de sair."},
        ],
        "expected_result": "OS identificável, vinculada ao imóvel correto e com a etapa planejada para a equipe.",
        "warnings": "Menus e ações dependem das permissões. Criar o atendimento não significa receber pagamento nem emitir documento fiscal.",
        "screens": ["home", "service_order_calendar"],
    },
    {
        "category": "primeiros-passos", "slug": "usar-central-de-ajuda",
        "title": "Encontre instruções na Central de Ajuda", "sort_order": 20,
        "summary": "Busque uma tarefa, explore os módulos e abra os tutoriais da tela em que você está.",
        "objective": "Encontrar uma orientação sem depender de assistir a um vídeo ou sair do atendimento em campo.",
        "prerequisites": "Estar conectado ao sistema e ter acesso à internet. O conteúdo disponível depende do seu perfil e dos módulos autorizados.",
        "content": "Ajuda e Tutoriais reúne instruções em texto e passos numerados. Um artigo pode ter imagens e um vídeo quando publicados pelo responsável. A explicação em texto continua disponível mesmo quando não há gravação. No app do técnico, os links de ajuda abrem em nova aba para manter o aplicativo aberto.",
        "steps": [
            {"title": "Abra a central ou a ajuda da tela", "content": "Use Ajuda e Tutoriais no menu do sistema ou no acesso do app do técnico. Nas telas que possuem guias vinculados, abra Como usar esta tela? e aguarde a consulta online dos assuntos. Sem conexão, o painel orienta a conectar-se; os títulos dos guias não ficam guardados no aplicativo offline."},
            {"title": "Pesquise a tarefa", "content": "Digite uma ação ou dúvida em Buscar tutoriais e use Buscar. Você pode escolher uma categoria ou abrir seus artigos diretamente. Para voltar à lista completa, use Limpar filtros."},
            {"title": "Leia o passo a passo", "content": "Abra Ler tutorial, confira Antes de começar, siga os passos e compare o Resultado esperado. Leia os avisos antes de realizar ações que afetem estoque, pagamentos ou documentos."},
            {"title": "Use vídeos quando disponíveis", "content": "Marque Somente com vídeo para localizar artigos com uma gravação publicada. Se nenhum tutorial for encontrado, remova o filtro e consulte as instruções em texto. Vídeos externos exigem internet."},
        ],
        "expected_result": "Orientação localizada e procedimento compreendido; os guias relacionados ajudam a continuar a jornada.",
        "warnings": "A ajuda desta versão não funciona offline. Se a consulta falhar, confira a conexão e sua sessão e feche e abra o painel para tentar novamente. Um módulo ou artigo ausente pode depender de permissão ou de publicação pelo responsável. Não compartilhe dados reais de clientes ao pedir suporte.",
        "screens": [],
    },
    {
        "category": "clientes", "slug": "cadastrar-cliente-e-imovel",
        "title": "Cadastre o cliente e o imóvel do atendimento", "sort_order": 10,
        "summary": "Separe os dados da pessoa ou empresa dos dados de cada imóvel.",
        "objective": "Evitar duplicidade e vincular a OS ao endereço correto.",
        "prerequisites": "Nome, tipo de cliente, contatos e endereço do local. Permissão de cadastro de clientes.",
        "content": "O cadastro distingue Pessoa Física e Pessoa Jurídica. Telefones, e-mails e imóveis fazem parte do formulário. Um mesmo cliente pode ter mais de um imóvel, portanto a identificação do cliente sozinha não define onde a equipe deve ir.",
        "steps": [
            {"title": "Procure antes de cadastrar", "content": "Abra Clientes e confira se a pessoa ou empresa já existe. Se existir, edite os dados ou cadastre o imóvel adicional em vez de duplicar o cliente."},
            {"title": "Preencha a identificação e os contatos", "content": "No novo cadastro, selecione Pessoa Física ou Pessoa Jurídica. Preencha os campos correspondentes e revise os telefones e e-mails; use + ADICIONAR quando houver outro contato."},
            {"title": "Revise os imóveis", "content": "Preencha os dados do imóvel e confira endereço, número e complemento. Salve o cadastro e confirme o imóvel na lista antes de usá-lo no agendamento."},
        ],
        "expected_result": "Cliente e imóvel disponíveis para seleção em um novo atendimento.",
        "warnings": "Telefone incorreto prejudica comunicações. Não reutilize o imóvel de outro cliente apenas para conseguir salvar uma OS.",
        "screens": ["client_list", "client_create", "client_edit", "property_create"],
    },
    {
        "category": "ordens-de-servico", "slug": "agendar-os-com-etapas",
        "title": "Agende uma OS e distribua a equipe por etapa", "featured": True, "sort_order": 10,
        "summary": "Escolha imóvel, tipo de etapa, horário e profissionais e trate os avisos de agenda.",
        "objective": "Registrar o compromisso certo para a equipe certa.",
        "prerequisites": "Cliente e imóvel cadastrados, profissionais ativos e acesso ao agendamento.",
        "content": "O formulário Nova OS / Agendamento permite cadastrar etapas e equipe. A disponibilidade é validada para os profissionais selecionados. OS e etapa não são a mesma coisa: uma OS pode reunir orçamento, execução e outros atendimentos previstos no formulário.",
        "steps": [
            {"title": "Abra o agendamento", "content": "No início ou calendário, selecione Novo Agendamento. Confira cliente, imóvel e informações do atendimento."},
            {"title": "Planeje as etapas", "content": "Escolha o tipo de cada etapa e informe os horários de início e fim quando definidos. Associe os profissionais e suas funções à etapa correspondente."},
            {"title": "Trate os conflitos", "content": "Ao salvar, leia as mensagens de disponibilidade. Ajuste horário ou equipe se houver conflito. Avisos de fora do horário de trabalho têm confirmação específica; só prossiga se o horário tiver sido combinado."},
            {"title": "Confira o resultado", "content": "Abra a OS salva e confira o imóvel, cada etapa, seu horário e a equipe. No calendário, verifique o compromisso agendado."},
        ],
        "expected_result": "Etapas e equipe registradas na OS, com agendamento coerente com a disponibilidade informada.",
        "warnings": "Não ignore conflito de agenda. Uma etapa sem data exige planejamento posterior; salvar não garante que o técnico já tenha sincronizado o app.",
        "screens": ["service_order_scheduling", "service_order_calendar", "service_order_edit"],
    },
    {
        "category": "ordens-de-servico", "slug": "orcamento-envio-e-aprovacao",
        "title": "Confira e envie o orçamento da OS", "featured": True, "sort_order": 20,
        "summary": "Revise os itens e acompanhe o envio e a resposta sem confundir orçamento com execução.",
        "objective": "Entregar ao destinatário um orçamento conferido e acompanhar sua aprovação.",
        "prerequisites": "OS cadastrada, itens revisados e integração de mensagens configurada para envio pelo sistema.",
        "content": "No detalhe da OS, os itens e etapas permitem conferir o que foi levantado. A ação Enviar Orçamento pode se chamar Reenviar Orçamento após um envio. O envio depende de contato e integração; a mensagem de sucesso ou erro deve ser conferida. Enviar não equivale a aprovar nem a executar.",
        "steps": [
            {"title": "Revise o orçamento", "content": "Abra a OS e confira descrição, quantidades, preços e os itens associados à etapa de orçamento. Confira o documento pelo PDF da OS antes de enviar."},
            {"title": "Confira o destinatário", "content": "Revise o telefone do cliente. Se houver configuração de mensagem com número fixo, confirme com o gestor quem receberá o orçamento."},
            {"title": "Envie e leia a resposta", "content": "Use Enviar Orçamento ou Reenviar Orçamento e confira a mensagem retornada. Em caso de falha, corrija o contato ou peça revisão da integração antes de repetir."},
            {"title": "Acompanhe o próximo passo", "content": "Confira a situação e a resposta do cliente no detalhe da OS. Depois da aprovação, revise a etapa de execução, seus itens, data e equipe; não trate o envio como autorização para executar."},
        ],
        "expected_result": "Envio confirmado pelo sistema e orçamento pronto para acompanhamento da resposta do cliente.",
        "warnings": "Reenviar gera nova comunicação. Não prometa entrega no WhatsApp apenas por ter clicado: confirme o resultado. O destinatário pode ser fixo conforme a configuração.",
        "screens": ["service_order_detail", "service_order_send_budget"],
    },
    {
        "category": "ordens-de-servico", "slug": "adicionar-execucao-e-conferir-itens",
        "title": "Adicione a execução e confira os itens copiados", "sort_order": 30,
        "summary": "Revise a primeira execução para não duplicar produtos e valores do orçamento.",
        "objective": "Levar os itens corretos do levantamento para a etapa que será executada.",
        "prerequisites": "OS existente e escopo autorizado pelo cliente; permissão de alteração da OS.",
        "content": "Ao adicionar a primeira etapa de execução, o sistema pode copiar itens do orçamento, inclusive itens gerais elegíveis. Os itens do orçamento permanecem como histórico. Quando há execução ou garantia, o total da OS e a baixa automática consideram essas etapas conforme as regras do sistema, evitando somar novamente os itens do orçamento.",
        "steps": [
            {"title": "Abra a nova etapa", "content": "A partir da OS, abra o formulário de adicionar etapa. Selecione Execução, confira aprovação, agendamento e equipe nos campos disponíveis."},
            {"title": "Revise a seleção do orçamento", "content": "Na primeira execução, revise a seção de itens do orçamento disponíveis para cópia. Atenção: a ausência de seleção é tratada pelo fluxo atual como copiar todos os itens elegíveis, não como copiar nenhum."},
            {"title": "Confira após salvar", "content": "Volte ao detalhe da OS e confira os itens da execução, quantidades e valores. Não adicione outra vez um produto que já foi copiado."},
            {"title": "Associe novos itens à etapa correta", "content": "Se precisar acrescentar material ou serviço, confira a etapa de destino. Após a criação da execução, não deixe itens novos apenas no orçamento geral esperando que componham o total executado."},
        ],
        "expected_result": "Execução com os itens necessários, equipe e agenda revisadas, mantendo o orçamento como histórico.",
        "warnings": "A cópia automática descrita é da primeira execução. Não faça baixa manual de estoque para repetir uma baixa já realizada pela OS.",
        "screens": ["task_add", "task_edit", "order_item_add"],
    },
    {
        "category": "ordens-de-servico", "slug": "acompanhar-conclusao-e-pendencias-os",
        "title": "Acompanhe conclusão, pendências e cobrança da OS", "sort_order": 40,
        "summary": "Confira o resultado de cada etapa e diferencie conclusão técnica de pagamento.",
        "objective": "Encerrar a conferência operacional sem perder pendências e valores a receber.",
        "prerequisites": "OS com etapas executadas ou em andamento e acesso ao detalhe da OS.",
        "content": "A situação da OS acompanha as etapas e regras do sistema. O técnico pode registrar um serviço incompleto; no servidor esse registro passa a parcialmente executado. Financeiro e documentos fiscais precisam de conferência própria: uma etapa concluída não comprova pagamento nem autorização de nota.",
        "steps": [
            {"title": "Confira as etapas", "content": "No detalhe da OS, leia a situação de cada etapa, horários, relatórios, checklist e mídias disponíveis. Se o técnico ainda estiver offline, aguarde a sincronização antes de considerar o registro ausente."},
            {"title": "Trate ocorrências e retorno", "content": "Leia as ocorrências e observações de impedimento. Combine a solução e revise o planejamento das etapas necessárias com o responsável; não marque o serviço como concluído apenas para retirar uma pendência da lista."},
            {"title": "Confira o financeiro", "content": "Na área financeira da OS, confira cobranças existentes, saldo e parcelas. Quando necessário, gere a cobrança pela ação oferecida e verifique se ela se refere à OS ou à etapa correta."},
        ],
        "expected_result": "Situação operacional entendida, pendências identificadas e cobranças conferidas sem duplicidade.",
        "warnings": "Cancelamentos e conclusão podem afetar estoque. Antes de cancelar, verifique o histórico e combine os efeitos com o gestor. Assinatura ausente, por si só, não prova falha: ela é opcional no app.",
        "screens": ["service_order_list", "occurrence_list", "task_cancel"],
    },
    {
        "category": "app-tecnico", "slug": "preparar-app-tecnico-offline",
        "title": "Prepare a agenda do técnico antes de ficar offline", "featured": True, "sort_order": 10,
        "summary": "Carregue as tarefas com internet e confira a sincronização antes de sair.",
        "objective": "Ter os dados do atendimento disponíveis no mesmo dispositivo usado em campo.",
        "prerequisites": "Usuário autorizado no app e profissional vinculado às tarefas; conexão para a primeira carga.",
        "content": "O app guarda dados localmente no navegador e enfileira alterações feitas em campo. Trabalhar offline exige que a agenda já tenha sido carregada nesse navegador. A presença de uma tarefa no app não garante que todas as alterações locais já tenham chegado à gestão.",
        "steps": [
            {"title": "Carregue o app conectado", "content": "Entre no app do técnico com internet e aguarde Minha Agenda carregar. Confira se os atendimentos esperados aparecem."},
            {"title": "Atualize e confira filtros", "content": "Use o ícone Sincronizar agora. Confira o indicador de conexão, última sincronização e pendências. Se uma tarefa não aparecer, revise Filtrar por status e Esconder OS concluídas antes de avisar o gestor."},
            {"title": "Revise o atendimento", "content": "Abra a tarefa e confira cliente, endereço e instruções em Info. Para OS, revise também Itens e Checklist. Faça isso antes de perder a conexão."},
        ],
        "expected_result": "Agenda e dados do atendimento disponíveis localmente e pendências de sincronização conhecidas.",
        "warnings": "Não limpe dados do site, desinstale o navegador ou troque de dispositivo com alterações pendentes. A primeira carga e o recebimento de novas tarefas dependem de internet.",
        "screens": ["equipe_offline_app", "equipe_dashboard", "equipe_task_list"],
    },
    {
        "category": "app-tecnico", "slug": "iniciar-tarefa-checklist-e-anexos",
        "title": "Inicie a tarefa, preencha o checklist e anexe evidências", "sort_order": 20,
        "summary": "Use as abas do atendimento para registrar execução e evidências no contexto certo.",
        "objective": "Manter o registro técnico organizado e preparar a finalização.",
        "prerequisites": "Tarefa carregada no app e acesso aos arquivos ou câmera quando utilizados.",
        "content": "O detalhe da tarefa de OS possui as abas Info, Itens, Checklist, Anexos, Ocorrências, Concluir e Histórico. As visitas de manutenção não apresentam todas essas abas. Use os controles de evidência realmente disponíveis; em Anexos, identifique no relatório o assunto de cada arquivo.",
        "steps": [
            {"title": "Inicie em Info", "content": "Abra a tarefa e confira o atendimento. Em Info, use INICIAR SERVIÇO AGORA quando começar o trabalho. Se a tarefa ainda estiver agendada, inicie antes de abrir Concluir."},
            {"title": "Preencha o checklist", "content": "Abra Checklist e marque OK apenas depois de realizar cada verificação. Revise os itens obrigatórios. Após sincronizar, peça conferência das marcações na gestão se houver divergência."},
            {"title": "Registre as evidências", "content": "Abra Anexos e use o controle de foto ou vídeo disponível. Relacione os arquivos ao serviço no relatório. Se um item exigir evidência e não apresentar o controle esperado, avise o gestor; não marque a verificação como realizada apenas para continuar."},
            {"title": "Confira a sincronização depois", "content": "Ao recuperar internet, sincronize e confira pendências. O envio das mídias é separado dos registros de texto e pode demorar mais."},
        ],
        "expected_result": "Tarefa iniciada, verificações registradas no dispositivo e evidências identificadas para conferência após o envio.",
        "warnings": "Uma marcação ou miniatura local não comprova que o registro chegou ao servidor. Confira o checklist na gestão depois da sincronização; se as marcações não aparecerem, avise o responsável antes de considerar a conferência encerrada. Não registre dados pessoais desnecessários nas fotos. Itens e valores visíveis dependem da configuração e das permissões.",
        "screens": ["equipe_offline_app", "equipe_task_detail"],
    },
    {
        "category": "app-tecnico", "slug": "registrar-impedimento-e-incompleto",
        "title": "Registre um impedimento e informe serviço incompleto", "featured": True, "sort_order": 30,
        "summary": "Documente o motivo da não conclusão e encaminhe a pendência para revisão.",
        "objective": "Não registrar como concluído um trabalho que ainda exige providências.",
        "prerequisites": "Tarefa de OS carregada no app, com descrição do impedimento encontrado.",
        "content": "A aba Ocorrências registra categoria, tipo e descrição. Ocorrências impeditivas geram avisos em Ocorrências e Concluir. O app oferece a opção Incompleto na aba Concluir, exigindo um motivo para esse registro. A gestão deve conferir a pendência após a sincronização.",
        "steps": [
            {"title": "Descreva a ocorrência", "content": "Abra Ocorrências e registre a situação. Escolha a categoria e o tipo correspondentes ao fato, por exemplo falta de material ou cliente ausente. Explique o que impediu o atendimento e o que falta fazer."},
            {"title": "Informe a não conclusão", "content": "Na aba Concluir, selecione Incompleto. Preencha Motivo / Relatório e use REGISTRAR COMO INCOMPLETO. Não use a conclusão normal para esconder o impedimento."},
            {"title": "Encaminhe a revisão", "content": "Sincronize ao ter conexão. Avise o responsável sobre a necessidade de material, contato com o cliente ou novo planejamento e peça conferência da etapa na gestão."},
        ],
        "expected_result": "Ocorrência e motivo registrados; após sincronizar, etapa disponível para revisão como parcialmente executada.",
        "warnings": "Um aviso local não substitui a conferência do envio. Este fluxo descreve tarefas de OS; visitas de manutenção têm tratamento próprio e não devem ser usadas como substitutas de etapas de OS.",
        "screens": ["equipe_offline_app"],
    },
    {
        "category": "app-tecnico", "slug": "finalizar-tarefa-e-sincronizar",
        "title": "Finalize a tarefa e confirme o envio dos registros", "featured": True, "sort_order": 40,
        "summary": "Revise checklist, relatório e eventual recebimento antes de finalizar e sincronizar.",
        "objective": "Concluir o atendimento no app sem confundir salvamento local com confirmação no servidor.",
        "prerequisites": "Tarefa iniciada; checklist obrigatório preenchido quando houver. Conexão para enviar os dados ao servidor.",
        "content": "A finalização fica na aba Concluir. Nome de quem recebeu, relatório, assinatura opcional e eventual recebimento compõem o registro. Os dados são salvos no dispositivo e entram na fila de sincronização. Mídias seguem envio separado e processamento posterior.",
        "steps": [
            {"title": "Revise antes de finalizar", "content": "Confira Checklist, Anexos e Ocorrências. Se o trabalho estiver incompleto, use o fluxo Incompleto em vez da conclusão normal."},
            {"title": "Preencha o encerramento", "content": "Em Concluir, selecione Concluído. Informe o nome de quem recebeu e Relatório / Observações. Colete a assinatura se aplicável; ela é opcional."},
            {"title": "Registre somente o valor recebido", "content": "Se a seção Recebimento aparecer e houve pagamento, selecione o método e confira Valor Recebido. Se não houve pagamento, deixe o método desmarcado. Não registre uma promessa de pagamento como recebimento."},
            {"title": "Finalize e envie", "content": "Use CONFIRMAR E FINALIZAR. Com internet, use Sincronizar agora e confira pendências e avisos. Se houver erro, mantenha os dados locais e comunique o gestor com o número da OS e a mensagem apresentada."},
        ],
        "expected_result": "Tarefa concluída localmente e, após sincronização bem-sucedida, dados disponíveis para conferência na gestão.",
        "warnings": "Não repita um recebimento já registrado. Em manutenção, o envio da finalização usa os dados próprios da visita; não presuma que todos os campos financeiros e de assinatura da OS sejam enviados para o contrato.",
        "screens": ["equipe_offline_app"],
    },
    {
        "category": "vendas", "slug": "registrar-venda-e-revisar-rascunho",
        "title": "Registre uma venda e revise antes de sair do rascunho", "sort_order": 10,
        "summary": "Confira produtos, quantidades, ajustes e cobrança antes de efetivar a venda.",
        "objective": "Salvar a venda no estado correto e evitar baixa de estoque indevida.",
        "prerequisites": "Produtos ativos, permissão de vendas e condições comerciais definidas.",
        "content": "O cadastro de vendas permite itens, desconto, acréscimo e condições de cobrança. Rascunho é um estado de preparação: no fluxo de criação, a baixa dos produtos acontece quando a venda deixa de ser rascunho. Venda administrativa e sessão de caixa do PDV são fluxos diferentes.",
        "steps": [
            {"title": "Preencha a venda", "content": "Abra Vendas e o formulário de nova venda. Confira o cliente quando informado e adicione os produtos, variantes quando houver, quantidades e preços."},
            {"title": "Confira os totais e a cobrança", "content": "Revise desconto, acréscimo, total e parcelas. Escolha o estado de gravação adequado; se os dados ainda não estão confirmados, mantenha como rascunho."},
            {"title": "Revise o resultado", "content": "Após salvar, confira a mensagem de situação e o número efetivamente atribuído. Abra o detalhe para revisar os itens e a cobrança antes de enviar documentos ao cliente."},
        ],
        "expected_result": "Venda salva com itens, totais e situação correspondentes ao combinado.",
        "warnings": "O número previsto pode mudar se outra venda for gravada ao mesmo tempo. Não registre uma segunda venda para corrigir a primeira sem conferir o efeito no estoque e nas cobranças.",
        "screens": ["sale_list", "sale_create", "sale_detail"],
    },
    {
        "category": "pdv", "slug": "operar-pdv-e-fechar-caixa",
        "title": "Abra o caixa, receba a venda e confira o fechamento", "sort_order": 10,
        "summary": "Separe abertura, venda, movimentação avulsa e valores contados da sessão.",
        "objective": "Encerrar a sessão com recebimentos e movimentos identificados.",
        "prerequisites": "Permissão de operação, caixa disponível e métodos de pagamento configurados.",
        "content": "O PDV opera com uma sessão de caixa do operador. Na abertura, informe o caixa e o saldo inicial. A área Operações do caixa oferece suprimentos, sangrias e fechamento. PIX integrado aguarda confirmação: iniciar a cobrança não equivale a receber.",
        "steps": [
            {"title": "Abra a sessão", "content": "Entre no PDV, confira o caixa e o valor de abertura e use Abrir caixa. Confirme que está operando na sessão correta."},
            {"title": "Confira e receba a venda", "content": "Adicione os produtos ao carrinho e confira quantidades e total. No recebimento, revise as formas e valores. Para PIX integrado, acompanhe a confirmação no próprio PDV antes de considerar a venda paga."},
            {"title": "Registre movimentos avulsos", "content": "Em Operações do caixa, registre suprimento para entrada ou sangria para retirada, com valor e identificação do motivo. Não use venda fictícia para movimentar dinheiro."},
            {"title": "Conte e feche", "content": "Resolva vendas em rascunho e recebimentos pendentes antes do fechamento. Conte e informe os valores por forma de pagamento. Confira a sessão na lista de sessões e encaminhe divergências ao gestor."},
        ],
        "expected_result": "Sessão com vendas e movimentos registrados e fechamento submetido para conferência conforme a configuração do caixa.",
        "warnings": "Rascunhos ou vendas aguardando pagamento impedem o fechamento. Não tente dar baixa por outro fluxo em recebimentos que o sistema orienta concluir pelo PDV.",
        "screens": ["pos_home", "pos_sessions"],
    },
    {
        "category": "estoque", "slug": "conferir-estoque-e-registrar-entrada",
        "title": "Confira o estoque e registre entradas sem duplicar baixas", "sort_order": 10,
        "summary": "Use histórico, movimentação manual e nota de entrada com finalidades distintas.",
        "objective": "Manter rastreabilidade do saldo e evitar movimentação duplicada.",
        "prerequisites": "Produto cadastrado; permissão de gestão para movimentações e notas de entrada.",
        "content": "A lista de produtos permite consultar saldos e o histórico de cada produto. Movimentar Estoque registra entradas ou saídas manuais. Notas de entrada possuem um lançamento próprio: importar ou preparar uma nota não deve ser confundido com efetivar sua entrada.",
        "steps": [
            {"title": "Consulte antes de ajustar", "content": "Localize o produto e consulte seu histórico. Confira se a entrada, venda, cancelamento ou OS já gerou o movimento esperado."},
            {"title": "Escolha o documento correto", "content": "Para compra, use Notas de Entrada e confira os itens da nota importada ou manual. Revise antes de Lançar Nota; no formulário manual existe também Salvar e Lançar (dar entrada no estoque)."},
            {"title": "Use ajuste manual com identificação", "content": "Quando o caso exigir movimentação manual, selecione produto, quantidade, tipo e motivo em Movimentar Estoque. Confira o Saldo Após e use Confirmar Movimentação. Depois revise o histórico."},
        ],
        "expected_result": "Movimentação identificável no histórico e saldo conferido após o lançamento.",
        "warnings": "Vendas e OS já têm fluxos de baixa automática; não repita a saída manualmente. Produção não movimenta estoque. Produtos compostos consomem componentes conforme sua ficha técnica.",
        "screens": ["product_list", "product_stock_history", "stock_movement_create", "purchase_invoice_list", "purchase_invoice_detail"],
    },
    {
        "category": "financeiro", "slug": "conferir-cobrancas-e-baixar-recebimentos",
        "title": "Confira cobranças e registre apenas o que foi recebido", "sort_order": 10,
        "summary": "Diferencie origem da cobrança, parcelas, saldo e recebimento parcial.",
        "objective": "Dar baixa na parcela correta sem criar cobrança ou recebimento duplicado.",
        "prerequisites": "Acesso ao financeiro, métodos de pagamento ativos e comprovação do recebimento.",
        "content": "Contas a Receber reúne cobranças e parcelas. A cobrança pode estar relacionada a venda, OS ou etapa. Para OS, a tela de geração mostra a referência utilizada; confira cobranças já existentes antes de gerar outra. A baixa manual aceita métodos e valores de pagamento e pode deixar a parcela parcialmente paga.",
        "steps": [
            {"title": "Identifique a cobrança", "content": "Abra Contas a Receber e o detalhe da cobrança. Confira cliente, origem, total, vencimentos e valores já pagos. Se vier de uma OS, confirme se a cobrança é da OS ou de uma etapa."},
            {"title": "Confira antes de gerar", "content": "Se ainda for necessário gerar uma cobrança, use a ação da OS ou etapa correta. Revise valor de referência e condições no formulário Gerar Cobrança antes de confirmar."},
            {"title": "Registre o recebimento", "content": "Na parcela, informe método, valor e data efetivos. Confira o saldo após salvar. Em recebimento parcial, registre apenas a quantia recebida e acompanhe o restante."},
            {"title": "Leia os avisos de integração", "content": "Depois da baixa, confira mensagens sobre cobranças externas. Se o cancelamento de uma cobrança no gateway falhar, peça conferência antes de cobrar novamente o cliente."},
        ],
        "expected_result": "Parcela e cobrança refletindo o recebimento real, com saldo restante identificado.",
        "warnings": "Não registre novamente um pagamento feito pelo técnico ou confirmado no PDV. Quando o sistema exigir conclusão pelo PDV, volte a esse fluxo. Gerar cobrança não significa pagamento confirmado.",
        "screens": ["billing_list", "billing_detail", "billing_create_for_os", "billing_create_for_task", "finance_dashboard"],
    },
    {
        "category": "financeiro", "slug": "registrar-despesa-e-acompanhar-pagamento",
        "title": "Registre despesas e confira as baixas das parcelas", "sort_order": 20,
        "summary": "Organize contas a pagar e use o fluxo de baixa para refletir pagamentos reais.",
        "objective": "Manter vencimentos e pagamentos de despesas identificados.",
        "prerequisites": "Permissão financeira e dados da despesa, vencimentos e conta bancária quando aplicável.",
        "content": "Contas a Pagar possui cadastro de despesas e acompanhamento de parcelas. A baixa é feita na parcela e permite registrar pagamentos; descontos têm ação própria. Fluxo de Caixa é uma visão de acompanhamento, não substitui a conferência do lançamento original.",
        "steps": [
            {"title": "Cadastre a obrigação", "content": "Abra Contas a Pagar e o formulário de nova despesa. Preencha identificação, valor e condições de vencimento. Confira a prévia das parcelas antes de salvar quando ela for apresentada."},
            {"title": "Confira a parcela e registre a baixa", "content": "Na listagem, confira a parcela e abra o fluxo de baixa. Informe os dados do pagamento real e anexe comprovantes quando disponíveis. Se houver desconto, use a ação correspondente e revise o saldo."},
            {"title": "Acompanhe o período", "content": "Revise pendências na listagem e consulte Fluxo de Caixa. Se um valor divergir, volte à despesa e aos pagamentos da parcela antes de criar novo lançamento."},
        ],
        "expected_result": "Despesa com parcelas e pagamentos conferidos no período correto.",
        "warnings": "Cadastrar uma despesa não comprova que ela foi paga. Antes de excluir uma baixa ou despesa, confira os efeitos com o responsável financeiro.",
        "screens": ["expense_list", "expense_create", "expense_edit", "expense_cashflow"],
    },
    {
        "category": "producao", "slug": "acompanhar-producao-e-registrar-saida",
        "title": "Prepare os itens da produção e registre a saída", "sort_order": 10,
        "summary": "Acompanhe a OP, sinalize falta de material e confirme a entrega física.",
        "objective": "Registrar o andamento físico sem repetir movimentações de estoque.",
        "prerequisites": "Acesso ao painel e permissão de operação; OP gerada por uma origem e gatilho configurados.",
        "content": "A ordem de produção nasce de uma venda ou etapa de OS conforme a configuração. O painel é uma fila de trabalho físico. No detalhe, os itens mostram quantidades, situação e ficha de separação. Falta de material é informada pelo operador; não é uma detecção automática do saldo.",
        "steps": [
            {"title": "Confira a ordem e os itens", "content": "Abra a OP no painel. Confira origem, prazo, modalidade de entrega, quantidades e instruções. Se houver indicação Revisar, confira as alterações da origem com o responsável."},
            {"title": "Registre o andamento", "content": "Use Iniciar e Concluir nos itens conforme o trabalho realizado. Se necessário, use Falta material e descreva a pendência; após resolver, use Material resolvido."},
            {"title": "Registre a saída real", "content": "Quando a OP estiver pronta e a saída ocorrer, use Registrar saída e preencha os dados solicitados para retirada, técnico ou envio. Confira o registro no detalhe."},
        ],
        "expected_result": "Andamento físico registrado e saída identificada para a modalidade correta.",
        "warnings": "Nenhuma ação de produção dá entrada ou baixa em estoque. Não conclua itens apenas porque houve pagamento. Dados de produção não são disponibilizados no app offline do técnico.",
        "screens": ["producao:board", "producao:order_detail", "producao:settings"],
    },
    {
        "category": "manutencao", "slug": "organizar-contratos-e-visitas",
        "title": "Organize o contrato de manutenção e confira suas visitas", "sort_order": 10,
        "summary": "Vincule equipamento e técnico, defina periodicidade e acompanhe as visitas do contrato.",
        "objective": "Manter o atendimento recorrente associado ao equipamento correto.",
        "prerequisites": "Cliente, imóvel, equipamento e técnico cadastrados; permissão de gestão da manutenção.",
        "content": "O contrato de manutenção reúne equipamento, técnico titular, valor mensal, comissão e periodicidade. As visitas são registros do contrato, não etapas comuns de OS. Contratos ativos têm geração de visitas do mês corrente no carregamento dos dados do app do técnico.",
        "steps": [
            {"title": "Confira o equipamento", "content": "Em Equipamentos, confira o bem e o imóvel a que ele pertence. Evite criar um contrato para um equipamento de outro local."},
            {"title": "Defina o contrato", "content": "No novo contrato, selecione Equipamento e Técnico Titular, preencha valores, frequência, dias de visita quando aplicáveis e datas. Salve e confira o detalhe."},
            {"title": "Acompanhe as visitas", "content": "No detalhe do contrato, use os filtros de mês e ano para conferir as visitas. Quando necessário, use o formulário de registrar visita e confira data e executante antes de salvar."},
            {"title": "Confira o retorno do técnico", "content": "Peça ao técnico para sincronizar. Confira a visita no contrato após o atendimento; no app as visitas de manutenção têm menos abas que as tarefas de OS."},
        ],
        "expected_result": "Contrato vinculado ao equipamento correto e visitas disponíveis para planejamento e conferência.",
        "warnings": "Não presuma geração de todos os meses futuros ao salvar o contrato. Verifique as visitas já existentes antes de cadastrar outra para o mesmo atendimento.",
        "screens": ["asset_list", "asset_create", "contract_list", "contract_create", "contract_detail", "visit_create"],
    },
    {
        "category": "relatorios", "slug": "consultar-indicadores-com-periodo-correto",
        "title": "Consulte os indicadores no período correto", "sort_order": 10,
        "summary": "Use as visões operacional, produtividade e manutenção sem misturar períodos e conceitos.",
        "objective": "Interpretar os números com base na visão e no recorte selecionados.",
        "prerequisites": "Permissão de gestão e registros atualizados, inclusive sincronizações dos técnicos.",
        "content": "O sistema oferece Painel Operacional, Produtividade da Equipe e Dashboard de Manutenção. O operacional tem filtro de período; produtividade e manutenção usam mês e ano. No operacional, o conjunto inicial de OS é selecionado pela data de criação dentro do período escolhido.",
        "steps": [
            {"title": "Escolha a pergunta", "content": "Use o Painel Operacional para acompanhar a operação, Produtividade da Equipe para a visão da equipe e Dashboard de Manutenção para os contratos e visitas."},
            {"title": "Defina o recorte", "content": "Confira o período do operacional ou mês e ano nas outras visões. Use o mesmo recorte ao comparar resultados e observe as legendas e títulos dos indicadores."},
            {"title": "Investigue as diferenças", "content": "Se houver divergência, confira a OS, etapa ou visita de origem e a sincronização do técnico. Compare contagens apenas depois de confirmar que representam o mesmo conjunto de registros."},
        ],
        "expected_result": "Indicadores consultados com período e origem compreendidos.",
        "warnings": "Número de OS, número de etapas e quantidade de visitas não são medidas intercambiáveis. Não interprete indicador operacional como confirmação de recebimento bancário.",
        "screens": ["bi_operacional", "bi_produtividade", "bi_manutencao"],
    },
    {
        "category": "fiscal", "slug": "preparar-emissao-e-acompanhar-documento-fiscal",
        "title": "Prepare a emissão e acompanhe o documento fiscal", "sort_order": 10,
        "summary": "Confira integração, destinatário e itens e acompanhe a autorização após solicitar emissão.",
        "objective": "Usar o documento correspondente aos itens e verificar o resultado da integração.",
        "prerequisites": "Gestor autorizado, integração habilitada e cadastros fiscais revisados com o responsável contábil.",
        "content": "Na OS, a emissão é por etapa: NFSe contempla os itens de serviço; NFe e NFCe contemplam os itens de produto. A NFSe usa Asaas e os documentos de produto usam Base ERP no fluxo atual. As ações aparecem conforme configuração e itens disponíveis. Solicitação enviada não significa documento autorizado.",
        "steps": [
            {"title": "Confira a configuração", "content": "Na configuração fiscal, confira dados da empresa, habilitação e informações municipais com o responsável. Confirme qual ambiente está ativo antes de emitir; não compartilhe credenciais em mensagens ou evidências."},
            {"title": "Revise destinatário e itens", "content": "Confira documento e endereço do cliente e os itens da venda ou etapa. Para OS, não misture o valor dos produtos com o dos serviços em uma única emissão esperando que todos os itens sejam incluídos."},
            {"title": "Solicite e acompanhe", "content": "Use a ação de emissão disponível na origem correta. Leia o retorno e confira o status do documento no painel fiscal. Se houver erro, revise a mensagem e os dados antes de uma nova tentativa."},
        ],
        "expected_result": "Solicitação identificada e status do documento conferido após o retorno do provedor.",
        "warnings": "Este guia explica a interface, não determina tributação, alíquotas ou prazos legais. Valide esses dados com o contador. Não emita novamente sem conferir o documento anterior e sua situação.",
        "screens": ["fiscal:nfe_config", "fiscal:sale_nfe_panel"],
    },
    {
        "category": "configuracoes", "slug": "revisar-configuracoes-e-mensagens",
        "title": "Revise parâmetros por módulo e regras de mensagens", "sort_order": 10,
        "summary": "Localize configurações específicas e confira os gatilhos antes de alterar a operação.",
        "objective": "Alterar o parâmetro certo sem presumir automações não configuradas.",
        "prerequisites": "Permissão de gestão da configuração e entendimento do efeito pretendido.",
        "content": "Vendas, PDV, financeiro, produção e app do técnico possuem configurações próprias. Notificações Automáticas e Mensagens Manuais têm cadastros específicos de regras. A existência de uma integração não garante que uma mensagem automática esteja configurada para todo evento.",
        "steps": [
            {"title": "Identifique o módulo", "content": "Abra a configuração específica do módulo cujo comportamento precisa mudar. Confira a descrição dos campos e anote os valores anteriores antes de salvar."},
            {"title": "Confira regras e destinatários", "content": "Em Notificações Automáticas, confira modelo, situação e destinatário da regra. Em Mensagens Manuais, confira a configuração da ação, inclusive se o destino é o cliente ou um número fixo."},
            {"title": "Valide o efeito", "content": "Depois de salvar, confira o parâmetro novamente e valide um caso autorizado. Para produção, revise os gatilhos de entrada na fila; para o técnico, confira as opções de apresentação e acesso com um usuário autorizado."},
        ],
        "expected_result": "Configuração localizada e alteração conferida no módulo correspondente.",
        "warnings": "Não exponha tokens ou senhas em capturas. Não ative envio automático sem confirmar destinatário e conteúdo. Mudanças de padrão podem afetar novos registros; não presuma correção retroativa.",
        "screens": ["sale_settings", "pos_settings", "finance_settings", "technician_app_settings", "integracoes:notification_config_list", "integracoes:manual_message_config_list"],
    },
]

# Defaults editoriais explícitos: estáveis entre execuções, sem mídias artificiais.
for _article in ARTICLES:
    _article.setdefault("reviewed_at", REVIEWED_AT)
    _article.setdefault("status", "PUBLISHED")
    _article.setdefault("audience", "ALL")
    _article.setdefault("featured", False)
    _article.setdefault("video_url", "")
    _article.setdefault("source_key", f"official:{_article['slug']}")
    for _position, _step in enumerate(_article["steps"], start=1):
        _step.setdefault("sort_order", _position * 10)
        _step.setdefault("image_alt", "")
        _step.setdefault("screenshot", "")

# Capturas reais, anotadas e regeneráveis. O manifesto contém somente dados de
# demonstração; nunca sessões, credenciais ou imagens do banco do cliente.
_capture_file = Path(__file__).resolve().parent.parent / 'static/help/screenshots/manifest.json'
_capture_entries = json.loads(_capture_file.read_text(encoding='utf-8'))
_articles_by_slug = {article['slug']: article for article in ARTICLES}
_capture_keys = set()
for _capture in _capture_entries:
    _key = (_capture['article_slug'], _capture['step_order'])
    if _key in _capture_keys:
        raise ValueError(f'Print duplicado para o mesmo passo: {_key}')
    _capture_keys.add(_key)
    _target_article = _articles_by_slug[_capture['article_slug']]
    _target_steps = [step for step in _target_article['steps'] if step['sort_order'] == _capture['step_order']]
    if len(_target_steps) != 1:
        raise ValueError(f'Passo inexistente ou duplicado para print: {_key}')
    _target_steps[0]['screenshot'] = 'help/screenshots/' + _capture['filename']
    _target_steps[0]['image_alt'] = _capture['alt']
    _target_article['featured'] = True

