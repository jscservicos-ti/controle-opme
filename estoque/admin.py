from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Especie, Fornecedor, Produto, Entrada, Saida, Baixa, MotivoBaixa

# Configurando o painel para exibir nossos campos customizados do Usuário
class CustomUserAdmin(UserAdmin):
    fieldsets = (
        *UserAdmin.fieldsets,  # Mantém os campos padrões do Django (login, senha, email)
        (
            'Permissões do Sistema OPME',  # Nossa sessão customizada
            {
                'fields': (
                    'cpf',
                    'is_ti',
                    'primeiro_acesso',
                ),
            },
        ),
    )

# Registrando as tabelas para aparecerem no /admin
admin.site.register(Usuario, CustomUserAdmin)
admin.site.register(Especie)
admin.site.register(Fornecedor)
admin.site.register(Produto)
admin.site.register(Entrada)
admin.site.register(Saida)
admin.site.register(Baixa)
admin.site.register(MotivoBaixa)