#!/bin/bash

# Script de inicialização SSL
# Gera certificado na primeira execução e configura renovação automática

DOMAIN="osonline.douradoscalhas.com.br"
EMAIL="deniolimasantos@gmail.com"  # ALTERE PARA SEU EMAIL REAL

echo "=========================================="
echo "🔐 INIT SSL - Gestão de Serviços"
echo "=========================================="
echo "Domínio: $DOMAIN"
echo ""

# Criar diretórios necessários
mkdir -p /etc/letsencrypt/live/$DOMAIN
mkdir -p /var/www/certbot

# Verificar se já existe certificado válido
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "✅ Certificado SSL já existe!"
    echo "📅 Verificando validade..."
    
    # Verificar validade do certificado
    CERT_EXPIRY=$(openssl x509 -enddate -noout -in /etc/letsencrypt/live/$DOMAIN/fullchain.pem | cut -d= -f2)
    echo "   Expira em: $CERT_EXPIRY"
    
    # Verificar se precisa renovar (menos de 30 dias)
    if ! certbot certificates -d $DOMAIN 2>&1 | grep -q "VALID"; then
        echo "⚠️  Certificado próximo do vencimento, renovando..."
        certbot renew --quiet
    fi
else
    echo "⚠️  Certificado não encontrado!"
    echo "🚀 Gerando certificado SSL..."
    echo ""
    echo "⚠️  IMPORTANTE:"
    echo "   - Certifique-se que o domínio $DOMAIN aponta para este servidor"
    echo "   - Porta 80 deve estar liberada"
    echo "   - Nenhum outro serviço usando porta 80"
    echo ""
    
    # Aguardar 10 segundos para dar tempo de parar outros serviços
    echo "⏳ Aguardando 10 segundos..."
    sleep 10
    
    # Tentar gerar certificado
    certbot certonly \
        --standalone \
        --non-interactive \
        --agree-tos \
        --email $EMAIL \
        --no-eff-email \
        -d $DOMAIN
    
    if [ $? -eq 0 ]; then
        echo "✅ Certificado gerado com sucesso!"
    else
        echo "❌ Erro ao gerar certificado!"
        echo "⚠️  O Nginx será iniciado SEM SSL"
        echo ""
        echo "Para tentar novamente:"
        echo "  1. Pare outros serviços na porta 80"
        echo "  2. Execute: docker-compose restart certbot-init"
    fi
fi

echo ""
echo "=========================================="
echo "✅ Init SSL Concluído!"
echo "=========================================="
