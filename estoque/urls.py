from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='estoque/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('mudar-senha/', views.mudar_senha, name='mudar_senha'),
    path('selecionar-empresa/', views.selecionar_empresa, name='selecionar_empresa'),

    path('empresas/', views.empresa_list, name='empresa_list'),
    path('empresas/nova/', views.empresa_form_view, name='empresa_create'),
    path('empresas/<int:id>/editar/', views.empresa_form_view, name='empresa_edit'),

    path('usuarios/', views.usuario_list, name='usuario_list'),
    path('usuarios/novo/', views.usuario_form_view, name='usuario_create'),
    path('usuarios/<int:id>/editar/', views.usuario_form_view, name='usuario_edit'),
    path('usuarios/<int:id>/reset/', views.usuario_reset_senha, name='usuario_reset_senha'),

    path('auditoria/', views.auditoria_list, name='auditoria_list'),
    path('auditoria/<int:id>/', views.auditoria_detail, name='auditoria_detail'),

    path('relatorios/', views.relatorios_list, name='relatorios_list'),
    path('relatorios/kardex/', views.relatorio_kardex, name='relatorio_kardex'),
    path('relatorios/entradas/', views.relatorio_entradas, name='relatorio_entradas'),
    path('relatorios/saidas/', views.relatorio_saidas, name='relatorio_saidas'),
    path('relatorios/baixas/', views.relatorio_baixas, name='relatorio_baixas'),

    path('', views.index, name='index'),
    path('produtos/', views.produto_list, name='produto_list'),
    path('produtos/exportar/', views.produto_export, name='produto_export'),
    path('produtos/novo/', views.produto_form_view, name='produto_create'),
    path('produtos/<int:id>/detalhes/', views.produto_detail, name='produto_detail'),
    path('produtos/<int:id>/editar/', views.produto_form_view, name='produto_edit'),
    path('produtos/<int:id>/excluir/', views.produto_delete, name='produto_delete'),
    
    path('especies/', views.especie_list, name='especie_list'),
    path('especies/nova/', views.especie_form_view, name='especie_create'),
    path('especies/<int:id>/editar/', views.especie_form_view, name='especie_edit'),
    path('especies/<int:id>/excluir/', views.especie_delete, name='especie_delete'),

    path('fornecedores/', views.fornecedor_list, name='fornecedor_list'),
    path('fornecedores/novo/', views.fornecedor_form_view, name='fornecedor_create'),
    path('fornecedores/<int:id>/editar/', views.fornecedor_form_view, name='fornecedor_edit'),
    path('fornecedores/<int:id>/excluir/', views.fornecedor_delete, name='fornecedor_delete'),

    path('entradas/', views.entrada_list, name='entrada_list'),
    path('entradas/nova/', views.entrada_create, name='entrada_create'),
    path('entradas/<int:id>/', views.entrada_detail, name='entrada_detail'),
    path('entradas/<int:id>/editar/', views.entrada_edit, name='entrada_edit'),
    path('entradas/<int:id>/excluir/', views.entrada_delete, name='entrada_delete'),

    path('motivos/', views.motivo_list, name='motivo_list'),
    path('motivos/novo/', views.motivo_form_view, name='motivo_create'),
    path('motivos/<int:id>/editar/', views.motivo_form_view, name='motivo_edit'),
    
    path('saidas/', views.saida_list, name='saida_list'),
    path('saidas/nova/', views.saida_create, name='saida_create'),
    path('saidas/<int:id>/', views.saida_detail, name='saida_detail'),
    path('saidas/<int:id>/editar/', views.saida_edit, name='saida_edit'),
    path('saidas/<int:id>/excluir/', views.saida_delete, name='saida_delete'),

    path('baixas/', views.baixa_list, name='baixa_list'),
    path('baixas/nova/', views.baixa_create, name='baixa_create'),
    path('baixas/<int:id>/', views.baixa_detail, name='baixa_detail'),
    path('baixas/<int:id>/editar/', views.baixa_edit, name='baixa_edit'),
    path('baixas/<int:id>/excluir/', views.baixa_delete, name='baixa_delete'),

    path('api/lotes/<int:id>/', views.api_lotes_produto, name='api_lotes_produto'),
]