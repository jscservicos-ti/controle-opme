from django.shortcuts import redirect
from django.urls import reverse

class AcessoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.path.startswith('/admin/'):
            # 1. Trava de primeiro acesso
            if getattr(request.user, 'primeiro_acesso', False) and request.path not in [reverse('mudar_senha'), reverse('logout')]:
                return redirect('mudar_senha')
            
            # 2. Trava de Seleção de Empresa
            empresa_id = request.session.get('empresa_id')
            caminhos_livres = [reverse('selecionar_empresa'), reverse('logout'), reverse('mudar_senha')]
            
            # A chave mestra: O Superusuário ou TI pode furar o bloqueio para acessar a tela de empresas
            is_ti_ou_admin = getattr(request.user, 'is_ti', False) or getattr(request.user, 'is_superuser', False)
            if is_ti_ou_admin:
                caminhos_livres.extend([reverse('empresa_list'), reverse('empresa_create')])
            
            # Se o caminho atual não estiver na lista de livres e não for uma edição de empresa (que também é livre pro TI)
            if not empresa_id and request.path not in caminhos_livres and not (is_ti_ou_admin and request.path.startswith('/empresas/')):
                return redirect('selecionar_empresa')
                
        return self.get_response(request)