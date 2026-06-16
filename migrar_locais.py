import os
import django

# Configura o Django para rodar scripts externos
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

from estoque.models import Empresa, LocalEstoque, Estoque, Entrada, Saida, Baixa, Manutencao

print("Iniciando migração de dados...")

for emp in Empresa.objects.all():
    # 1. Cria o Almoxarifado Central
    local_central, created = LocalEstoque.objects.get_or_create(
        empresa=emp, 
        nome="Almoxarifado Central",
        defaults={'tipo': 'ARMAZENAMENTO'}
    )
    
    # 2. Transfere histórico
    Entrada.objects.filter(empresa=emp, local__isnull=True).update(local=local_central)
    Saida.objects.filter(empresa=emp, local__isnull=True).update(local=local_central)
    Baixa.objects.filter(empresa=emp, local__isnull=True).update(local=local_central)
    Manutencao.objects.filter(empresa=emp, local__isnull=True).update(local=local_central)
    
    # 3. Transfere os saldos físicos
    Estoque.objects.filter(empresa=emp, local__isnull=True).update(local=local_central)
    
    print(f"✅ Migração concluída para a empresa: {emp.nome}")

print("Tudo pronto! Seu banco de dados está atualizado.")