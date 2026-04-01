#!/bin/bash

# Script simplificado para gerar certificado SSL
# Execute ANTES de subir os containers

DOMAIN="osonline.douradoscalhas.com.br"
EMAIL="seu-email@exemplo.com"  # ALTERE PARA SEU EMAIL REAL

echo "=========================================="
echo "🔐 GERAÇÃO DE CERTIFICADO SSL"
echo "=========================================="
echo "Domínio: $DOMAIN"
echo "Email: $EMAIL"
echo ""

# Verificar se já existe
if [ -d "./certbot/conf/live/$DOMAIN" ]; then
    echo "✅ Certificado já existe em ./certbot/conf/live/$DOMAIN"
    echo ""
    read -p "Deseja gerar novamente? (s/n): " REGENERATE
    if [ "$REGENERATE" != "s" ]; then
        echo "Abortado. Use o certificado existente."
        exit 0
    fi
fi

echo "⏹️  Parando todos os containers..."
docker-compose down

echo ""
echo "📁 Criando diretórios..."
mkdir -p certbot/conf certbot/www

echo ""
echo "🚀 Gerando certificado SSL..."
echo "   (Certifique-se que a porta 80 está livre!)"
echo ""

# Gerar certificado usando container temporário
docker run --rm \
    -p 80:80 \
    -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/certbot/www:/var/www/certbot" \
    certbot/certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    --no-eff-email \
    -d "$DOMAIN"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ CERTIFICADO GERADO COM SUCESSO!"
    echo "=========================================="
    echo ""
    echo "📂 Certificados salvos em:"
    echo "   ./certbot/conf/live/$DOMAIN/"
    echo ""
    echo "📝 PRÓXIMOS PASSOS:"
    echo ""
    echo "1️⃣  Ativar SSL no Nginx:"
    echo "   cp nginx/conf.d/default.conf.ssl nginx/conf.d/default.conf"
    echo ""
    echo "2️⃣  Subir aplicação:"
    echo "   docker-compose up -d"
    echo ""
else
    echo ""
    echo "=========================================="
    echo "❌ ERRO AO GERAR CERTIFICADO"
    echo "=========================================="
    echo ""
    echo "Verifique:"
    echo "  - Porta 80 está realmente livre?"
    echo "  - DNS aponta para este servidor?"
    echo "  - Firewall permite conexões na porta 80?"
    echo ""
    echo "Testar DNS:"
    echo "  ping $DOMAIN"
    echo ""
fi
