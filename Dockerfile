# Estágio 1: Build do Tailwind CSS com Node.js
FROM node:20-alpine AS node-build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Estágio 2: Imagem final com Python e Django
FROM python:3.11-slim
WORKDIR /app

# Configurações do Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências do Python
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install gunicorn

# Copia o código fonte do projeto
COPY . .

# Copia o CSS gerado através do build do Tailwind (estágio anterior)
COPY --from=node-build /app/static/dist/output.css ./static/dist/output.css

# Coleta os arquivos estáticos (o db_v2.sqlite3 de produção não precisa estar aqui, usaremos o volume)
RUN python manage.py collectstatic --noinput

# Expõe a porta para o Gunicorn
EXPOSE 8000

# Comando para iniciar o Gunicorn
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
