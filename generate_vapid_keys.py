#!/usr/bin/env python
"""
Script para gerar chaves VAPID para Push Notifications
Execute: python generate_vapid_keys.py
"""

try:
    from py_vapid import Vapid
    from cryptography.hazmat.primitives import serialization
    import base64
    
    print("=" * 60)
    print("🔐 GERANDO CHAVES VAPID PARA PUSH NOTIFICATIONS")
    print("=" * 60)
    print()
    
    # Gerar chaves VAPID
    vapid = Vapid()
    vapid.generate_keys()
    
    # Exportar chave pública (formato raw para base64 URL-safe)
    public_key_raw = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    public_key_b64 = base64.urlsafe_b64encode(public_key_raw).decode('utf-8').rstrip('=')
    
    # Exportar chave privada (formato raw para base64 URL-safe)
    private_key_raw = vapid.private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    private_key_b64 = base64.urlsafe_b64encode(private_key_raw).decode('utf-8').rstrip('=')
    
    print("✅ Chaves geradas com sucesso!")
    print()
    print("📋 Adicione estas linhas no seu core/settings.py:")
    print()
    print("-" * 60)
    print(f"VAPID_PUBLIC_KEY = '{public_key_b64}'")
    print(f"VAPID_PRIVATE_KEY = '{private_key_b64}'")
    print(f"VAPID_ADMIN_EMAIL = 'admin@douradoscalhas.com.br'")
    print("-" * 60)
    print()
    print("⚠️  IMPORTANTE:")
    print("   - Mantenha a PRIVATE_KEY em segredo!")
    print("   - Não commite a PRIVATE_KEY no Git!")
    print("   - Use variáveis de ambiente em produção")
    print()
    
    # Salvar em arquivo para backup (opcional)
    try:
        with open('vapid_keys.txt', 'w') as f:
            f.write(f"VAPID_PUBLIC_KEY = '{public_key_b64}'\n")
            f.write(f"VAPID_PRIVATE_KEY = '{private_key_b64}'\n")
            f.write(f"VAPID_ADMIN_EMAIL = 'admin@douradoscalhas.com.br'\n")
        print("💾 Chaves salvas em 'vapid_keys.txt'")
        print()
    except Exception as e:
        print(f"⚠️  Não foi possível salvar em arquivo: {e}")
        print()
    
except ImportError as e:
    print("❌ Dependências não estão instaladas!")
    print(f"   Erro: {e}")
    print()
    print("   Execute: pip install pywebpush")
    print("   Ou: pip install -r requirements.txt")
except Exception as e:
    print(f"❌ Erro ao gerar chaves: {e}")
    print(f"   Tipo do erro: {type(e).__name__}")
    print()
    print("Alternativa: Gere as chaves online")
    print("1. Acesse: https://web-push-codelab.glitch.me/")
    print("2. Clique em 'Generate Keys'")
    print("3. Copie as chaves geradas")



