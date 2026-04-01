#!/bin/bash

# Script automatizado para gerar certificado SSL
# Domínio: osonline.douradoscalhas.com.br
# Método: HTTP Challenge (Standalone)

DOMAIN="osonline.douradoscalhas.com.br"
EMAIL="deniolimasantos@gmail.com"  # ALTERE PARA SEU EMAIL REAL

echo "=========================================="
echo "🔐 GERAÇÃO DE CERTIFICADO SSL"
echo "=========================================="
echo "Domínio: $DOMAIN"
echo "Email: $EMAIL"
echo ""
echo "📋 PRÉ-REQUISITOS:"
echo "  ✅ DNS já aponta para este servidor"
echo "  ⚠️  Vamos parar App 1 temporariamente"
echo ""
read -p "Pressione ENTER para continuar ou CTRL+C para cancelar..."

# Criar diretórios necessários
echo ""
echo "📁 Criando diretórios..."
mkdir -p certbot/conf certbot/www

# Gerar certificado
echo ""
echo "🚀 Gerando certificado SSL..."
echo "   Isso pode levar alguns segundos..."
echo ""

docker-compose run --rm certbot certonly \
    --standalone \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    --non-interactive \
    -d $DOMAIN

# Verificar resultado
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
    echo "1️⃣  Atualizar nginx/conf.d/default.conf:"
    echo "   - Substituir 'seu-dominio.com' por '$DOMAIN'"
    echo ""
    echo "2️⃣  Subir App 2 com SSL:"
    echo "   docker-compose up -d"
    echo ""
    echo "3️⃣  Subir App 1 novamente:"
    echo "   cd /caminho/app1 && docker-compose up -d"
    echo ""
    echo "=========================================="
    
    # Mostrar informações do certificado
    echo ""
    echo "📋 Informações do certificado:"
    docker-compose run --rm certbot certificates -d $DOMAIN
    
else
    echo ""
    echo "=========================================="
    echo "❌ ERRO AO GERAR CERTIFICADO"
    echo "=========================================="
    echo ""
    echo "Possíveis causas:"
    echo "  - App 1 ainda está usando a porta 80"
    echo "  - Firewall bloqueando porta 80"
    echo "  - DNS não aponta para este servidor"
    echo ""
    echo "Verificar com:"
    echo "  ping $DOMAIN"
    echo "  curl -I http://$DOMAIN"
    echo ""
fi


