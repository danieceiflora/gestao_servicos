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
    ffmpeg \
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

# Dá permissão de execução para o script de entrada
RUN chmod +x /app/entrypoint.sh

# Expõe a porta para o Gunicorn
EXPOSE 8001

# Usa o script de entrada para rodar migrações, collectstatic e iniciar o server
ENTRYPOINT ["/app/entrypoint.sh"]
