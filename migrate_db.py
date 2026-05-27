import os
import subprocess
import sys

def run_command(command, env=None, input_str=None):
    print(f"Executando: {command}")
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            env=env, 
            input=input_str,
            capture_output=True, 
            text=True
        )
        if result.returncode != 0:
            print(f"Erro ao executar comando: {result.stderr}")
            return False, result.stderr
        return True, result.stdout
    except Exception as e:
        print(f"Exceção ao executar comando: {e}")
        return False, str(e)

def migrate():
    # Caminho do banco SQLite
    sqlite_db = "db_v2.sqlite3"
    
    if not os.path.exists(sqlite_db):
        print(f"ERRO: Arquivo {sqlite_db} não encontrado!")
        return

    print("--- PASSO 1: Exportando dados do SQLite ---")
    # Garante que estamos usando SQLite para o dump (removendo DATABASE_URL do env temporariamente)
    dump_env = os.environ.copy()
    if "DATABASE_URL" in dump_env:
        del dump_env["DATABASE_URL"]
    
    # Exporta os dados excluindo tabelas de sistema do Django que são recriadas no migrate
    success, output = run_command(
        "python manage.py dumpdata --exclude contenttypes --exclude auth.permission --indent 2", 
        env=dump_env
    )
    
    if not success:
        print("Falha ao exportar dados.")
        return

    with open("data_dump.json", "w", encoding="utf-8") as f:
        f.write(output)
    print("Dados exportados para data_dump.json")

    print("\n--- PASSO 2: Preparando o banco PostgreSQL ---")
    # Aqui assumimos que o DATABASE_URL está configurado no ambiente ou passamos manualmente
    # Para o script funcionar, o Postgres deve estar acessível.
    pg_url = os.environ.get("DATABASE_URL")
    if not pg_url:
        print("AVISO: DATABASE_URL não definida no ambiente.")
        pg_url = input("Digite a URL do Postgres (ex: postgres://user:pass@localhost:5432/dbname) ou ENTER para pular: ")
        if not pg_url:
            print("Abortando migração para Postgres.")
            return
    
    pg_env = os.environ.copy()
    pg_env["DATABASE_URL"] = pg_url

    print("Executando migrations no PostgreSQL...")
    success, output = run_command("python manage.py migrate", env=pg_env)
    if not success:
        print("Falha ao executar migrate no PostgreSQL.")
        return
    print(output)

    print("\n--- PASSO 3: Importando dados para o PostgreSQL ---")
    # Carrega os dados exportados
    success, output = run_command("python manage.py loaddata data_dump.json", env=pg_env)
    if not success:
        print("Falha ao importar dados no PostgreSQL.")
        # Se falhar aqui, pode ser útil olhar o erro específico
        return
    print(output)

    print("\n============================================")
    print("MIGRAÇÃO CONCLUÍDA COM SUCESSO!")
    print("SQLite -> PostgreSQL")
    print("============================================")

if __name__ == "__main__":
    migrate()
