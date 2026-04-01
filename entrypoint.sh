#!/bin/bash

# Falha o script se qualquer comando falhar
set -e

echo "Iniciando Entrypoint..."

# Executa migrações (importante se houver novos modelos como o PushSubscription)
echo "Executando migrações..."
python manage.py migrate --noinput

# Coleta arquivos estáticos (garante que o volume montado seja atualizado)
echo "Coletando arquivos estáticos..."
python manage.py collectstatic --noinput

# Inicia o servidor Gunicorn
echo "Iniciando Gunicorn..."
exec gunicorn core.wsgi:application --bind 0.0.0.0:8001 --workers 3
