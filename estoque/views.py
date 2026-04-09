import json
import openpyxl
from datetime import date, datetime
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import ProtectedError, Sum, Q
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.utils.timezone import make_aware
from django.utils import timezone # Adicionado para registrar a data exata da conclusão

# --- Importações Atualizadas ---
from .models import (
    Produto, Especie, Fornecedor, Entrada, ItemEntrada, MotivoBaixa, 
    Saida, ItemSaida, Baixa, ItemBaixa, Usuario, HistoricoEntrada, 
    HistoricoSaida, HistoricoBaixa, AuditoriaExclusao, ItemAuditoriaExclusao, 
    Empresa, Estoque, Defeito, Especialidade, Manutencao, Marca
)
from .forms import (
    ProdutoForm, EspecieForm, FornecedorForm, EntradaForm, ItemEntradaFormSet, 
    MotivoBaixaForm, SaidaForm, ItemSaidaFormSet, BaixaForm, ItemBaixaFormSet, 
    UsuarioForm, MudarSenhaForm, EmpresaForm, DefeitoForm, EspecialidadeForm, 
    ManutencaoEnvioForm, ManutencaoConclusaoForm, MarcaForm
)

def ti_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not (getattr(request.user, 'is_ti', False) or getattr(request.user, 'is_superuser', False)):
            messages.error(request, 'ACESSO BLOQUEADO: Você não tem permissão para realizar esta ação.')
            return redirect('index')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def gerar_detalhes_edicao(form, formset):
    detalhes = []
    if form.has_changed():
        for field in form.changed_data: detalhes.append(f"Capa [{field.upper()}] alterada")
    for f in formset.forms:
        if not f.cleaned_data: continue
        is_delete = f.cleaned_data.get('DELETE', False)
        if is_delete:
            prod_id, qtd = f.initial.get('produto'), f.initial.get('quantidade')
            if prod_id:
                try: detalhes.append(f"Removido: {Produto.objects.get(pk=prod_id).nome} (Qtd: {qtd})")
                except: pass
            continue
        produto = f.cleaned_data.get('produto')
        if not produto: continue
        if f in formset.extra_forms and f.has_changed():
            detalhes.append(f"Adicionado: {produto.nome} (Qtd: {f.cleaned_data.get('quantidade')})")
        elif f in formset.initial_forms and f.has_changed():
            mudancas = []
            if 'quantidade' in f.changed_data: mudancas.append(f"Qtd de {f.initial.get('quantidade', 0)} para {f.cleaned_data.get('quantidade', 0)}")
            if 'lote' in f.changed_data: mudancas.append(f"Lote de '{f.initial.get('lote') or 'Vazio'}' para '{f.cleaned_data.get('lote') or 'Vazio'}'")
            if mudancas: detalhes.append(f"{produto.nome} -> {', '.join(mudancas)}")
    return " | ".join(detalhes) if detalhes else "Edição salva sem mudanças nos dados."

# --- SELEÇÃO DE EMPRESA ---
@login_required
def selecionar_empresa(request):
    is_ti_ou_admin = getattr(request.user, 'is_ti', False) or getattr(request.user, 'is_superuser', False)
    empresas = request.user.empresas.filter(ativo=True)
    if not empresas.exists() and not is_ti_ou_admin:
        return render(request, 'estoque/erro_permissao.html', {'msg': 'Seu usuário não possui vínculo com nenhuma empresa ativa. Contate o TI.'})
    if request.method == 'POST':
        empresa_id = request.POST.get('empresa_id')
        if empresa_id:
            empresa = get_object_or_404(Empresa, id=empresa_id)
            if is_ti_ou_admin or empresa in empresas:
                request.session['empresa_id'] = empresa.id
                request.session['empresa_nome'] = empresa.nome
                messages.success(request, f'Bem-vindo(a) ao sistema da empresa {empresa.nome}!')
                return redirect('index')
    if is_ti_ou_admin: empresas = Empresa.objects.filter(ativo=True)
    return render(request, 'estoque/selecionar_empresa.html', {'empresas': empresas})

# --- EMPRESAS (Apenas TI) ---
@ti_required
def empresa_list(request): return render(request, 'estoque/empresa_list.html', {'empresas': Empresa.objects.all()})

@ti_required
def empresa_form_view(request, id=None):
    empresa = get_object_or_404(Empresa, id=id) if id else None
    if request.method == 'POST':
        form = EmpresaForm(request.POST, instance=empresa)
        if form.is_valid(): 
            form.save()
            messages.success(request, 'Empresa salva com sucesso!')
            return redirect('empresa_list')
    else: form = EmpresaForm(instance=empresa)
    return render(request, 'estoque/empresa_form.html', {'form': form, 'empresa': empresa})

# --- USUÁRIOS E SENHAS ---
@login_required
def mudar_senha(request):
    if request.method == 'POST':
        form = MudarSenhaForm(request.POST)
        if form.is_valid():
            user = request.user
            user.set_password(form.cleaned_data['nova_senha'])
            user.primeiro_acesso = False
            user.save()
            update_session_auth_hash(request, user)
            return redirect('selecionar_empresa')
    else: form = MudarSenhaForm()
    return render(request, 'estoque/mudar_senha.html', {'form': form})

@ti_required
def usuario_list(request): return render(request, 'estoque/usuario_list.html', {'usuarios': Usuario.objects.all().order_by('nome')})

@ti_required
def usuario_form_view(request, id=None):
    usuario = get_object_or_404(Usuario, id=id) if id else None
    if request.method == 'POST':
        form = UsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            user = form.save(commit=False)
            if not id:
                user.set_password(user.username)
                user.primeiro_acesso = True
            user.save()
            form.save_m2m()
            messages.success(request, 'Usuário salvo com sucesso!')
            return redirect('usuario_list')
    else: form = UsuarioForm(instance=usuario)
    return render(request, 'estoque/usuario_form.html', {'form': form, 'usuario': usuario})

@ti_required
def usuario_reset_senha(request, id):
    user = get_object_or_404(Usuario, id=id)
    if request.method == 'POST':
        user.set_password(user.username)
        user.primeiro_acesso = True
        user.save()
        messages.success(request, f'Senha resetada.')
        return redirect('usuario_list')
    return render(request, 'estoque/confirmar_exclusao.html', {'item': f'o RESET de senha do usuário {user.username}', 'url_cancelar': 'usuario_list'})

# --- DASHBOARD ---
# --- DASHBOARD ---
@login_required
def index(request):
    empresa_id = request.session.get('empresa_id')
    zerados = Estoque.objects.filter(empresa_id=empresa_id, quantidade__lte=0).count()
    zerados += Produto.objects.filter(ativo=True).exclude(estoques__empresa_id=empresa_id).count()
    
    # Conta a quantidade total de itens físicos (peças) que estão atualmente na manutenção
    itens_em_manutencao = Manutencao.objects.filter(empresa_id=empresa_id, status='PENDENTE').aggregate(total=Sum('quantidade'))['total'] or 0
    
    context = {
        'total_produtos': Produto.objects.filter(ativo=True).count(),
        'produtos_zerados': zerados,
        'total_fornecedores': Fornecedor.objects.filter(ativo=True).count(),
        'itens_em_manutencao': itens_em_manutencao, # Nova variável para as caixas do topo
        'ultimas_entradas': Entrada.objects.filter(empresa_id=empresa_id).order_by('-data_entrada')[:5],
        'ultimas_saidas': Saida.objects.filter(empresa_id=empresa_id).order_by('-data_saida')[:5],
        'ultimas_baixas': Baixa.objects.filter(empresa_id=empresa_id).order_by('-data_baixa')[:5],
        'ultimas_manutencoes': Manutencao.objects.filter(empresa_id=empresa_id).order_by('-data_registro')[:5], # Nova variável para a lista
    }
    return render(request, 'estoque/index.html', context)

@ti_required
def auditoria_list(request):
    empresa_id = request.session.get('empresa_id')
    auditorias = AuditoriaExclusao.objects.filter(empresa_id=empresa_id).order_by('-data_exclusao')
    return render(request, 'estoque/auditoria_list.html', {'auditorias': auditorias})

@ti_required
def auditoria_detail(request, id):
    return render(request, 'estoque/auditoria_detail.html', {'auditoria': get_object_or_404(AuditoriaExclusao, id=id, empresa_id=request.session.get('empresa_id'))})

# --- PRODUTOS ---
@login_required
def produto_list(request):
    empresa_id = request.session.get('empresa_id')
    produtos = Produto.objects.all()
    q = request.GET.get('q', '')
    if q:
        if q.isdigit(): produtos = produtos.filter(Q(id=q) | Q(nome__icontains=q))
        else: produtos = produtos.filter(nome__icontains=q)
    status = request.GET.get('status', '')
    if status == 'ativo': produtos = produtos.filter(ativo=True)
    elif status == 'inativo': produtos = produtos.filter(ativo=False)
    especie_id = request.GET.get('especie', '')
    if especie_id: produtos = produtos.filter(especie_id=especie_id)
    sort = request.GET.get('sort', 'id')
    if sort in ['id', '-id', 'nome', '-nome']: produtos = produtos.order_by(sort)

    for p in produtos:
        estoque = Estoque.objects.filter(produto=p, empresa_id=empresa_id).first()
        p.saldo_empresa = estoque.quantidade if estoque else 0

    return render(request, 'estoque/produto_list.html', {'produtos': produtos, 'especies': Especie.objects.all(), 'q': q, 'status': status, 'especie_id': especie_id, 'sort': sort})

@login_required
def produto_export(request):
    empresa_id = request.session.get('empresa_id')
    tipo = request.GET.get('tipo', 'sintetica')
    formato = request.GET.get('formato', 'excel')
    produtos = Produto.objects.all().order_by('nome')
    
    for p in produtos:
        estoque = Estoque.objects.filter(produto=p, empresa_id=empresa_id).first()
        p.saldo_empresa = estoque.quantidade if estoque else 0
        
    if tipo == 'sintetica' and request.GET.get('zerados', '0') == '0': 
        produtos = [p for p in produtos if p.saldo_empresa > 0]
        
    dados_analiticos = []
    if tipo == 'analitica':
        for p in produtos:
            entradas = ItemEntrada.objects.filter(produto=p, entrada__empresa_id=empresa_id).values('lote', 'validade').annotate(total_in=Sum('quantidade'))
            lotes_produto = []
            for e in entradas:
                lote = e['lote']
                saidas = ItemSaida.objects.filter(produto=p, lote=lote, saida__empresa_id=empresa_id).aggregate(t=Sum('quantidade'))['t'] or 0
                baixas = ItemBaixa.objects.filter(produto=p, lote=lote, baixa__empresa_id=empresa_id).aggregate(t=Sum('quantidade'))['t'] or 0
                saldo = e['total_in'] - saidas - baixas
                if saldo > 0: lotes_produto.append({'lote': lote or 'Sem Lote', 'validade': e['validade'], 'saldo': saldo})
            if lotes_produto: dados_analiticos.append({'produto': p, 'lotes': lotes_produto})

    if formato == 'excel':
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename=estoque_{tipo}.xlsx'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "OPME"
        if tipo == 'sintetica':
            ws.append(['Código', 'Nome do Produto', 'Espécie', 'Status', 'Estoque Empresa Atual'])
            for p in produtos: ws.append([p.id, p.nome, p.especie.nome, 'Ativo' if p.ativo else 'Inativo', p.saldo_empresa])
        else:
            ws.append(['Código', 'Nome do Produto', 'Espécie', 'Lote', 'Validade', 'Quantidade Disponível'])
            for item in dados_analiticos:
                for l in item['lotes']:
                    val = l['validade'].strftime('%d/%m/%Y') if l['validade'] else '-'
                    ws.append([item['produto'].id, item['produto'].nome, item['produto'].especie.nome, l['lote'], val, l['saldo']])
        wb.save(response)
        return response
        
    # Se for PDF (Impressão em Tela), manda para o HTML
    return render(request, 'estoque/relatorio_imprimir.html', { 'tipo': tipo, 'produtos': produtos, 'dados_analiticos': dados_analiticos })

@login_required
def produto_detail(request, id):
    empresa_id = request.session.get('empresa_id')
    produto = get_object_or_404(Produto, id=id)
    entradas = ItemEntrada.objects.filter(produto=produto, entrada__empresa_id=empresa_id).values('lote', 'validade').annotate(total_entrada=Sum('quantidade'))
    estoque_por_lote = []
    for e in entradas:
        lote = e['lote']
        validade = e['validade'] # Captura a validade original da entrada
        saidas = ItemSaida.objects.filter(produto=produto, lote=lote, saida__empresa_id=empresa_id).aggregate(t=Sum('quantidade'))['t'] or 0
        baixas = ItemBaixa.objects.filter(produto=produto, lote=lote, baixa__empresa_id=empresa_id).aggregate(t=Sum('quantidade'))['t'] or 0
        saldo = e['total_entrada'] - saidas - baixas
        if saldo > 0: estoque_por_lote.append({ 'lote': lote if lote else 'Sem Lote', 'validade': validade, 'saldo': saldo })
    
    # Busca o saldo geral do produto na empresa logada
    estoque = Estoque.objects.filter(produto=produto, empresa_id=empresa_id).first()
    saldo_total = estoque.quantidade if estoque else 0
        
    return render(request, 'estoque/produto_detail.html', {'produto': produto, 'estoque_por_lote': estoque_por_lote, 'saldo_total': saldo_total})

@ti_required
def produto_form_view(request, id=None):
    produto = get_object_or_404(Produto, id=id) if id else None
    if request.method == 'POST':
        form = ProdutoForm(request.POST, instance=produto)
        if form.is_valid(): form.save(); return redirect('produto_list')
    else: form = ProdutoForm(instance=produto)
    return render(request, 'estoque/produto_form.html', {'form': form})

@ti_required
def produto_delete(request, id):
    produto = get_object_or_404(Produto, id=id)
    if request.method == 'POST':
        try: produto.delete()
        except ProtectedError: pass
        return redirect('produto_list')
    return render(request, 'estoque/confirmar_exclusao.html', {'item': produto.nome, 'url_cancelar': 'produto_list'})

# --- CADASTROS GLOBAIS ---
@login_required
def especie_list(request): return render(request, 'estoque/especie_list.html', {'especies': Especie.objects.all()})
@ti_required
def especie_form_view(request, id=None):
    especie = get_object_or_404(Especie, id=id) if id else None
    if request.method == 'POST':
        form = EspecieForm(request.POST, instance=especie)
        if form.is_valid(): form.save(); return redirect('especie_list')
    else: form = EspecieForm(instance=especie)
    return render(request, 'estoque/especie_form.html', {'form': form})
@ti_required
def especie_delete(request, id):
    especie = get_object_or_404(Especie, id=id)
    if request.method == 'POST':
        try: especie.delete()
        except ProtectedError: pass
        return redirect('especie_list')
    return render(request, 'estoque/confirmar_exclusao.html', {'item': especie.nome, 'url_cancelar': 'especie_list'})

# --- MARCAS ---
@login_required
def marca_list(request):
    return render(request, 'estoque/marca_list.html', {'marcas': Marca.objects.all().order_by('nome')})

@ti_required
def marca_form_view(request, id=None):
    marca = get_object_or_404(Marca, id=id) if id else None
    if request.method == 'POST':
        form = MarcaForm(request.POST, instance=marca)
        if form.is_valid(): 
            form.save()
            messages.success(request, 'Marca salva com sucesso!')
            return redirect('marca_list')
    else: 
        form = MarcaForm(instance=marca)
    return render(request, 'estoque/marca_form.html', {'form': form, 'marca': marca})

@login_required
def fornecedor_list(request):
    q = request.GET.get('q', '')
    forn = Fornecedor.objects.all()
    if q: forn = forn.filter(Q(nome__icontains=q) | Q(cnpj__icontains=q))
    return render(request, 'estoque/fornecedor_list.html', {'fornecedores': forn, 'q': q})
@ti_required
def fornecedor_form_view(request, id=None):
    f = get_object_or_404(Fornecedor, id=id) if id else None
    if request.method == 'POST':
        form = FornecedorForm(request.POST, instance=f)
        if form.is_valid(): form.save(); return redirect('fornecedor_list')
    else: form = FornecedorForm(instance=f)
    return render(request, 'estoque/fornecedor_form.html', {'form': form})
@ti_required
def fornecedor_delete(request, id):
    f = get_object_or_404(Fornecedor, id=id)
    if request.method == 'POST':
        try: f.delete()
        except ProtectedError: pass
        return redirect('fornecedor_list')
    return render(request, 'estoque/confirmar_exclusao.html', {'item': f.nome, 'url_cancelar': 'fornecedor_list'})

@login_required
def motivo_list(request): return render(request, 'estoque/motivo_list.html', {'motivos': MotivoBaixa.objects.all()})
@ti_required
def motivo_form_view(request, id=None):
    m = get_object_or_404(MotivoBaixa, id=id) if id else None
    if request.method == 'POST':
        form = MotivoBaixaForm(request.POST, instance=m)
        if form.is_valid(): form.save(); return redirect('motivo_list')
    else: form = MotivoBaixaForm(instance=m)
    return render(request, 'estoque/motivo_form.html', {'form': form})

# --- MOVIMENTAÇÕES ---
def check_movimento_bloqueado(entrada):
    for i in entrada.itens.all():
        if i.lote:
            if ItemSaida.objects.filter(produto=i.produto, lote=i.lote, saida__empresa=entrada.empresa).exists() or ItemBaixa.objects.filter(produto=i.produto, lote=i.lote, baixa__empresa=entrada.empresa).exists(): return False
        else:
            if ItemSaida.objects.filter(produto=i.produto, saida__data_saida__gte=entrada.data_entrada, saida__empresa=entrada.empresa).exists() or ItemBaixa.objects.filter(produto=i.produto, baixa__data_baixa__gte=entrada.data_entrada, baixa__empresa=entrada.empresa).exists(): return False
    return True

@login_required
def entrada_list(request): 
    return render(request, 'estoque/entrada_list.html', {'entradas': Entrada.objects.filter(empresa_id=request.session['empresa_id']).order_by('-data_entrada')})

@login_required
def entrada_detail(request, id): 
    return render(request, 'estoque/entrada_detail.html', {'entrada': get_object_or_404(Entrada, id=id, empresa_id=request.session['empresa_id'])})

@login_required
def entrada_create(request):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    if request.method == 'POST':
        form = EntradaForm(request.POST)
        formset = ItemEntradaFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                entrada = form.save(commit=False)
                entrada.empresa = empresa
                entrada.usuario_registro = request.user
                entrada.save()
                formset.instance = entrada
                itens = formset.save()
                
                # Atualiza estoque considerando os itens salvos e deletados
                afetados = set(i.produto for i in itens)
                for obj in getattr(formset, 'deleted_objects', []): afetados.add(obj.produto)
                for p in afetados: p.atualizar_estoque(empresa)
                
            return redirect('entrada_list')
    else:
        form = EntradaForm()
        formset = ItemEntradaFormSet()
        form.fields['fornecedor'].queryset = Fornecedor.objects.filter(ativo=True)
        for f in formset.forms: f.fields['produto'].queryset = Produto.objects.filter(ativo=True)
    regras = {p.id: {'lote': p.controla_lote, 'validade': p.controla_validade} for p in Produto.objects.filter(ativo=True)}
    return render(request, 'estoque/entrada_form.html', {'form': form, 'formset': formset, 'produtos_regras_json': json.dumps(regras)})

@login_required
def entrada_edit(request, id):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    entrada = get_object_or_404(Entrada, id=id, empresa=empresa)
    if not check_movimento_bloqueado(entrada): messages.error(request, 'Bloqueado'); return redirect('entrada_list')
    
    # Guarda o estado original dos produtos ANTES do POST para garantir que estoques excluídos sejam recalculados
    produtos_originais = list(entrada.itens.all()) 
    
    if request.method == 'POST':
        form = EntradaForm(request.POST, instance=entrada)
        formset = ItemEntradaFormSet(request.POST, instance=entrada)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                detalhes = gerar_detalhes_edicao(form, formset)
                form.save()
                itens_salvos = formset.save()
                HistoricoEntrada.objects.create(entrada=entrada, usuario=request.user, detalhes=detalhes)
                
                # Recalcula o estoque de quem ficou, de quem estava antes, e de quem foi deletado
                afetados = set(i.produto for i in produtos_originais).union(set(i.produto for i in itens_salvos))
                for obj in getattr(formset, 'deleted_objects', []): afetados.add(obj.produto)
                for p in afetados: p.atualizar_estoque(empresa)
                
            return redirect('entrada_list')
    else:
        form = EntradaForm(instance=entrada)
        formset = ItemEntradaFormSet(instance=entrada)
        form.fields['fornecedor'].queryset = Fornecedor.objects.filter(ativo=True)
        for f in formset.forms: f.fields['produto'].queryset = Produto.objects.filter(ativo=True)
    regras = {p.id: {'lote': p.controla_lote, 'validade': p.controla_validade} for p in Produto.objects.filter(ativo=True)}
    return render(request, 'estoque/entrada_form.html', {'form': form, 'formset': formset, 'produtos_regras_json': json.dumps(regras)})

@login_required
def entrada_delete(request, id):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    entrada = get_object_or_404(Entrada, id=id, empresa=empresa)
    if not check_movimento_bloqueado(entrada): return redirect('entrada_list')
    if request.method == 'POST':
        with transaction.atomic():
            audit = AuditoriaExclusao.objects.create(empresa=empresa, tipo_movimento='ENTRADA', identificador=f"NF: {entrada.nota_fiscal}", usuario=request.user)
            afetados = set(i.produto for i in entrada.itens.all())
            for i in entrada.itens.all(): ItemAuditoriaExclusao.objects.create(auditoria=audit, produto_nome=i.produto.nome, quantidade=i.quantidade, lote=i.lote)
            entrada.delete()
            for p in afetados: p.atualizar_estoque(empresa)
        return redirect('entrada_list')
    return render(request, 'estoque/confirmar_exclusao.html', {'item': entrada.nota_fiscal, 'url_cancelar': 'entrada_list'})

@login_required
def saida_list(request): 
    return render(request, 'estoque/saida_list.html', {'saidas': Saida.objects.filter(empresa_id=request.session['empresa_id']).order_by('-data_saida')})

@login_required
def saida_detail(request, id): 
    return render(request, 'estoque/saida_detail.html', {'saida': get_object_or_404(Saida, id=id, empresa_id=request.session['empresa_id'])})

@login_required
def saida_create(request):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    if request.method == 'POST':
        form = SaidaForm(request.POST)
        formset = ItemSaidaFormSet(request.POST)
        formset.empresa_id = empresa.id # Injeta ID para a validação de estoque funcionar
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                saida = form.save(commit=False)
                saida.empresa = empresa
                saida.usuario_registro = request.user
                saida.save()
                formset.instance = saida
                itens = formset.save()
                
                afetados = set(i.produto for i in itens)
                for obj in getattr(formset, 'deleted_objects', []): afetados.add(obj.produto)
                for p in afetados: p.atualizar_estoque(empresa)
                
            return redirect('saida_list')
    else:
        form = SaidaForm()
        formset = ItemSaidaFormSet()
        for f in formset.forms: f.fields['produto'].queryset = Produto.objects.filter(estoques__empresa=empresa, estoques__quantidade__gt=0, ativo=True)
    regras = {p.id: {'lote': p.controla_lote} for p in Produto.objects.filter(ativo=True)}
    return render(request, 'estoque/saida_form.html', {'form': form, 'formset': formset, 'produtos_regras_json': json.dumps(regras)})

@login_required
def saida_edit(request, id):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    saida = get_object_or_404(Saida, id=id, empresa=empresa)
    produtos_originais = list(saida.itens.all())
    
    if request.method == 'POST':
        form = SaidaForm(request.POST, instance=saida)
        formset = ItemSaidaFormSet(request.POST, instance=saida)
        formset.empresa_id = empresa.id
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                detalhes = gerar_detalhes_edicao(form, formset)
                form.save()
                itens_salvos = formset.save()
                HistoricoSaida.objects.create(saida=saida, usuario=request.user, detalhes=detalhes)
                
                afetados = set(i.produto for i in produtos_originais).union(set(i.produto for i in itens_salvos))
                for obj in getattr(formset, 'deleted_objects', []): afetados.add(obj.produto)
                for p in afetados: p.atualizar_estoque(empresa)
                
            return redirect('saida_list')
    else:
        form = SaidaForm(instance=saida)
        formset = ItemSaidaFormSet(instance=saida)
        for f in formset.forms: f.fields['produto'].queryset = Produto.objects.filter(ativo=True)
    regras = {p.id: {'lote': p.controla_lote} for p in Produto.objects.filter(ativo=True)}
    return render(request, 'estoque/saida_form.html', {'form': form, 'formset': formset, 'produtos_regras_json': json.dumps(regras)})

@login_required
def saida_delete(request, id):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    saida = get_object_or_404(Saida, id=id, empresa=empresa)
    if request.method == 'POST':
        with transaction.atomic():
            audit = AuditoriaExclusao.objects.create(empresa=empresa, tipo_movimento='SAIDA', identificador=f"Paciente: {saida.paciente}", usuario=request.user)
            afetados = set(i.produto for i in saida.itens.all())
            for i in saida.itens.all(): ItemAuditoriaExclusao.objects.create(auditoria=audit, produto_nome=i.produto.nome, quantidade=i.quantidade, lote=i.lote)
            saida.delete()
            for p in afetados: p.atualizar_estoque(empresa)
        return redirect('saida_list')
    return render(request, 'estoque/confirmar_exclusao.html', {'item': saida.paciente, 'url_cancelar': 'saida_list'})

@login_required
def baixa_list(request): 
    return render(request, 'estoque/baixa_list.html', {'baixas': Baixa.objects.filter(empresa_id=request.session['empresa_id']).order_by('-data_baixa')})

@login_required
def baixa_detail(request, id): 
    return render(request, 'estoque/baixa_detail.html', {'baixa': get_object_or_404(Baixa, id=id, empresa_id=request.session['empresa_id'])})

@login_required
def baixa_create(request):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    if request.method == 'POST':
        form = BaixaForm(request.POST)
        formset = ItemBaixaFormSet(request.POST)
        formset.empresa_id = empresa.id
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                baixa = form.save(commit=False)
                baixa.empresa = empresa
                baixa.usuario_registro = request.user
                baixa.save()
                formset.instance = baixa
                itens = formset.save()
                
                afetados = set(i.produto for i in itens)
                for obj in getattr(formset, 'deleted_objects', []): afetados.add(obj.produto)
                for p in afetados: p.atualizar_estoque(empresa)
                
            return redirect('baixa_list')
    else:
        form = BaixaForm()
        form.fields['motivo'].queryset = MotivoBaixa.objects.filter(ativo=True)
        formset = ItemBaixaFormSet()
        for f in formset.forms: f.fields['produto'].queryset = Produto.objects.filter(estoques__empresa=empresa, estoques__quantidade__gt=0, ativo=True)
    regras = {p.id: {'lote': p.controla_lote} for p in Produto.objects.filter(ativo=True)}
    return render(request, 'estoque/baixa_form.html', {'form': form, 'formset': formset, 'produtos_regras_json': json.dumps(regras)})

@login_required
def baixa_edit(request, id):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    baixa = get_object_or_404(Baixa, id=id, empresa=empresa)
    produtos_originais = list(baixa.itens.all())
    
    if request.method == 'POST':
        form = BaixaForm(request.POST, instance=baixa)
        formset = ItemBaixaFormSet(request.POST, instance=baixa)
        formset.empresa_id = empresa.id
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                detalhes = gerar_detalhes_edicao(form, formset)
                form.save()
                itens_salvos = formset.save()
                HistoricoBaixa.objects.create(baixa=baixa, usuario=request.user, detalhes=detalhes)
                
                afetados = set(i.produto for i in produtos_originais).union(set(i.produto for i in itens_salvos))
                for obj in getattr(formset, 'deleted_objects', []): afetados.add(obj.produto)
                for p in afetados: p.atualizar_estoque(empresa)
                
            return redirect('baixa_list')
    else:
        form = BaixaForm(instance=baixa)
        form.fields['motivo'].queryset = MotivoBaixa.objects.filter(ativo=True)
        formset = ItemBaixaFormSet(instance=baixa)
        for f in formset.forms: f.fields['produto'].queryset = Produto.objects.filter(ativo=True)
    regras = {p.id: {'lote': p.controla_lote} for p in Produto.objects.filter(ativo=True)}
    return render(request, 'estoque/baixa_form.html', {'form': form, 'formset': formset, 'produtos_regras_json': json.dumps(regras)})

@login_required
def baixa_delete(request, id):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    baixa = get_object_or_404(Baixa, id=id, empresa=empresa)
    if request.method == 'POST':
        with transaction.atomic():
            audit = AuditoriaExclusao.objects.create(empresa=empresa, tipo_movimento='BAIXA', identificador=baixa.motivo.nome, usuario=request.user)
            afetados = set(i.produto for i in baixa.itens.all())
            for i in baixa.itens.all(): ItemAuditoriaExclusao.objects.create(auditoria=audit, produto_nome=i.produto.nome, quantidade=i.quantidade, lote=i.lote)
            baixa.delete()
            for p in afetados: p.atualizar_estoque(empresa)
        return redirect('baixa_list')
    return render(request, 'estoque/confirmar_exclusao.html', {'item': baixa.motivo.nome, 'url_cancelar': 'baixa_list'})

@login_required
def api_lotes_produto(request, id):
    empresa_id = request.session.get('empresa_id')
    acao = request.GET.get('acao', 'saida')
    produto = get_object_or_404(Produto, id=id)
    entradas = ItemEntrada.objects.filter(produto=produto, entrada__empresa_id=empresa_id).values('lote', 'validade').annotate(total_in=Sum('quantidade'))
    
    lotes_disponiveis = []
    hoje = date.today()
    for e in entradas:
        lote = e['lote']
        validade = e['validade']
        if not lote: continue
        if acao == 'saida' and validade and validade < hoje: continue
        
        saidas = ItemSaida.objects.filter(produto=produto, lote=lote, saida__empresa_id=empresa_id).aggregate(t=Sum('quantidade'))['t'] or 0
        baixas = ItemBaixa.objects.filter(produto=produto, lote=lote, baixa__empresa_id=empresa_id).aggregate(t=Sum('quantidade'))['t'] or 0
        saldo = e['total_in'] - saidas - baixas
        
        if saldo > 0: lotes_disponiveis.append({'lote': lote, 'saldo': saldo})
    return JsonResponse({'lotes': lotes_disponiveis})

# --- RELATÓRIOS ---
@login_required
def relatorios_list(request): return render(request, 'estoque/relatorios_list.html')

@login_required
def relatorio_kardex(request):
    empresa_id = request.session.get('empresa_id')
    produtos = Produto.objects.filter(ativo=True).order_by('nome')
    produto_id = request.GET.get('produto')
    
    context = {'produtos': produtos, 'produto_id': int(produto_id) if produto_id else '', 'data_inicial': request.GET.get('data_inicial'), 'data_final': request.GET.get('data_final')}
    
    if produto_id and context['data_inicial'] and context['data_final']:
        produto_selecionado = get_object_or_404(Produto, id=produto_id)
        d_ini = make_aware(datetime.strptime(context['data_inicial'], '%Y-%m-%d'))
        d_fim = make_aware(datetime.strptime(context['data_final'], '%Y-%m-%d').replace(hour=23, minute=59, second=59))
        
        # 1. CÁLCULO DO SALDO ANTERIOR (Tudo que aconteceu antes da Data Inicial)
        in_ant = ItemEntrada.objects.filter(produto=produto_selecionado, entrada__empresa_id=empresa_id, entrada__data_entrada__lt=d_ini).aggregate(t=Sum('quantidade'))['t'] or 0
        out_ant = ItemSaida.objects.filter(produto=produto_selecionado, saida__empresa_id=empresa_id, saida__data_saida__lt=d_ini).aggregate(t=Sum('quantidade'))['t'] or 0
        loss_ant = ItemBaixa.objects.filter(produto=produto_selecionado, baixa__empresa_id=empresa_id, baixa__data_baixa__lt=d_ini).aggregate(t=Sum('quantidade'))['t'] or 0
        
        # Abate as manutenções enviadas antes da data
        manut_envio_ant = Manutencao.objects.filter(produto=produto_selecionado, empresa_id=empresa_id, data_envio__lt=d_ini.date()).aggregate(t=Sum('quantidade'))['t'] or 0
        
        # Conta os retornos de manutenção antes da data (com "rede de segurança" para itens de teste antigos sem data)
        manut_retorno_ant = 0
        manutencoes_reparadas = Manutencao.objects.filter(produto=produto_selecionado, empresa_id=empresa_id, status='REPARADO')
        for m in manutencoes_reparadas:
            dt_base = m.data_conclusao if m.data_conclusao else make_aware(datetime.combine(m.data_envio, datetime.min.time()))
            if dt_base < d_ini:
                manut_retorno_ant += m.quantidade
        
        saldo_anterior_calculado = in_ant - out_ant - loss_ant - manut_envio_ant + manut_retorno_ant
        saldo = saldo_anterior_calculado

        movs = []
        
        # 2. BUSCA AS MOVIMENTAÇÕES NORMAIS NO PERÍODO
        for e in ItemEntrada.objects.filter(produto=produto_selecionado, entrada__empresa_id=empresa_id, entrada__data_entrada__range=(d_ini, d_fim)): 
            movs.append({'data': e.entrada.data_entrada, 'tipo': 'Entrada (NF)', 'documento': f"NF: {e.entrada.nota_fiscal or 'S/N'}", 'lote': e.lote, 'entrada': e.quantidade, 'saida': 0, 'usuario': e.entrada.usuario_registro.username})
            
        for s in ItemSaida.objects.filter(produto=produto_selecionado, saida__empresa_id=empresa_id, saida__data_saida__range=(d_ini, d_fim)): 
            movs.append({'data': s.saida.data_saida, 'tipo': 'Saída Paciente', 'documento': f"Pac: {s.saida.paciente}", 'lote': s.lote, 'entrada': 0, 'saida': s.quantidade, 'usuario': s.saida.usuario_registro.username})
            
        for b in ItemBaixa.objects.filter(produto=produto_selecionado, baixa__empresa_id=empresa_id, baixa__data_baixa__range=(d_ini, d_fim)): 
            movs.append({'data': b.baixa.data_baixa, 'tipo': 'Descarte', 'documento': b.baixa.motivo.nome, 'lote': b.lote, 'entrada': 0, 'saida': b.quantidade, 'usuario': b.baixa.usuario_registro.username})

        # 3. BUSCA AS MANUTENÇÕES NO PERÍODO
        # A) Envios para assistência (Atua como Saída)
        for m in Manutencao.objects.filter(produto=produto_selecionado, empresa_id=empresa_id, data_envio__range=(d_ini.date(), d_fim.date())):
            data_envio_dt = make_aware(datetime.combine(m.data_envio, datetime.min.time()))
            movs.append({'data': data_envio_dt, 'tipo': 'Saída (Envio Manut.)', 'documento': f"Defeito: {m.defeito.nome}", 'lote': m.lote, 'entrada': 0, 'saida': m.quantidade, 'usuario': m.usuario_registro.username})

        # B) Retornos Consertados (Atua como Entrada, usando a rede de segurança da data)
        for m in manutencoes_reparadas:
            dt_base = m.data_conclusao if m.data_conclusao else make_aware(datetime.combine(m.data_envio, datetime.min.time()))
            if d_ini <= dt_base <= d_fim:
                usuario_conclusao = m.usuario_conclusao.username if m.usuario_conclusao else 'Sistema'
                movs.append({'data': dt_base, 'tipo': 'Entrada (Retorno Manut.)', 'documento': "Item Reparado", 'lote': m.lote, 'entrada': m.quantidade, 'saida': 0, 'usuario': usuario_conclusao})

        # 4. ORDENA TUDO POR DATA E CALCULA O SALDO LINHA A LINHA
        movs.sort(key=lambda x: x['data'])
        for m in movs:
            saldo += m['entrada'] - m['saida']
            m['saldo'] = saldo
            
        context.update({
            'movimentacoes': movs, 
            'saldo_anterior': saldo_anterior_calculado, 
            'produto_selecionado': produto_selecionado, 
            'data_inicial_formatada': d_ini.strftime('%d/%m/%Y'), 
            'data_final_formatada': d_fim.strftime('%d/%m/%Y')
        })
        
    return render(request, 'estoque/relatorio_kardex.html', context)

@login_required
def relatorio_entradas(request):
    empresa_id = request.session.get('empresa_id')
    context = {'produtos': Produto.objects.filter(ativo=True).order_by('nome'), 'especies': Especie.objects.filter(ativo=True).order_by('nome'), 'produto_id': request.GET.get('produto', ''), 'especie_id': request.GET.get('especie', ''), 'data_inicial': request.GET.get('data_inicial'), 'data_final': request.GET.get('data_final')}
    if context['data_inicial']:
        d_ini = make_aware(datetime.strptime(context['data_inicial'], '%Y-%m-%d'))
        d_fim = make_aware(datetime.strptime(context['data_final'], '%Y-%m-%d').replace(hour=23, minute=59, second=59))
        q = ItemEntrada.objects.filter(entrada__empresa_id=empresa_id, entrada__data_entrada__range=(d_ini, d_fim)).order_by('entrada__data_entrada')
        if context['especie_id']: q = q.filter(produto__especie_id=context['especie_id'])
        if context['produto_id']: q = q.filter(produto_id=context['produto_id'])
        context.update({'itens': q, 'total_qtd': sum(i.quantidade for i in q), 'data_inicial_formatada': d_ini.strftime('%d/%m/%Y'), 'data_final_formatada': d_fim.strftime('%d/%m/%Y'), 'produto_selecionado': get_object_or_404(Produto, id=context['produto_id']) if context['produto_id'] else None, 'especie_selecionada': get_object_or_404(Especie, id=context['especie_id']) if context['especie_id'] else None})
    return render(request, 'estoque/relatorio_entradas.html', context)

@login_required
def relatorio_saidas(request):
    empresa_id = request.session.get('empresa_id')
    context = {'produtos': Produto.objects.filter(ativo=True).order_by('nome'), 'especies': Especie.objects.filter(ativo=True).order_by('nome'), 'produto_id': request.GET.get('produto', ''), 'especie_id': request.GET.get('especie', ''), 'data_inicial': request.GET.get('data_inicial'), 'data_final': request.GET.get('data_final')}
    if context['data_inicial']:
        d_ini = make_aware(datetime.strptime(context['data_inicial'], '%Y-%m-%d'))
        d_fim = make_aware(datetime.strptime(context['data_final'], '%Y-%m-%d').replace(hour=23, minute=59, second=59))
        q = ItemSaida.objects.filter(saida__empresa_id=empresa_id, saida__data_saida__range=(d_ini, d_fim)).order_by('saida__data_saida')
        if context['especie_id']: q = q.filter(produto__especie_id=context['especie_id'])
        if context['produto_id']: q = q.filter(produto_id=context['produto_id'])
        context.update({'itens': q, 'total_qtd': sum(i.quantidade for i in q), 'data_inicial_formatada': d_ini.strftime('%d/%m/%Y'), 'data_final_formatada': d_fim.strftime('%d/%m/%Y'), 'produto_selecionado': get_object_or_404(Produto, id=context['produto_id']) if context['produto_id'] else None, 'especie_selecionada': get_object_or_404(Especie, id=context['especie_id']) if context['especie_id'] else None})
    return render(request, 'estoque/relatorio_saidas.html', context)

@login_required
def relatorio_baixas(request):
    empresa_id = request.session.get('empresa_id')
    context = {'produtos': Produto.objects.filter(ativo=True).order_by('nome'), 'especies': Especie.objects.filter(ativo=True).order_by('nome'), 'motivos': MotivoBaixa.objects.all(), 'produto_id': request.GET.get('produto', ''), 'especie_id': request.GET.get('especie', ''), 'motivo_id': request.GET.get('motivo', ''), 'data_inicial': request.GET.get('data_inicial'), 'data_final': request.GET.get('data_final')}
    if context['data_inicial']:
        d_ini = make_aware(datetime.strptime(context['data_inicial'], '%Y-%m-%d'))
        d_fim = make_aware(datetime.strptime(context['data_final'], '%Y-%m-%d').replace(hour=23, minute=59, second=59))
        q = ItemBaixa.objects.filter(baixa__empresa_id=empresa_id, baixa__data_baixa__range=(d_ini, d_fim)).order_by('baixa__data_baixa')
        if context['motivo_id']: q = q.filter(baixa__motivo_id=context['motivo_id'])
        if context['especie_id']: q = q.filter(produto__especie_id=context['especie_id'])
        if context['produto_id']: q = q.filter(produto_id=context['produto_id'])
        context.update({'itens': q, 'total_qtd': sum(i.quantidade for i in q), 'data_inicial_formatada': d_ini.strftime('%d/%m/%Y'), 'data_final_formatada': d_fim.strftime('%d/%m/%Y'), 'produto_selecionado': get_object_or_404(Produto, id=context['produto_id']) if context['produto_id'] else None, 'especie_selecionada': get_object_or_404(Especie, id=context['especie_id']) if context['especie_id'] else None, 'motivo_selecionado': get_object_or_404(MotivoBaixa, id=context['motivo_id']) if context['motivo_id'] else None})
    return render(request, 'estoque/relatorio_baixas.html', context) 

@login_required
def relatorio_manutencao(request):
    empresa_id = request.session.get('empresa_id')
    
    context = {
        'data_inicial': request.GET.get('data_inicial'), 
        'data_final': request.GET.get('data_final'),
        'status_filter': request.GET.get('status', '')
    }
    
    if context['data_inicial'] and context['data_final']:
        d_ini = make_aware(datetime.strptime(context['data_inicial'], '%Y-%m-%d'))
        d_fim = make_aware(datetime.strptime(context['data_final'], '%Y-%m-%d').replace(hour=23, minute=59, second=59))
        
        # Filtra pela data de envio físico
        q = Manutencao.objects.filter(empresa_id=empresa_id, data_envio__range=(d_ini.date(), d_fim.date())).order_by('data_envio')
        
        # Aplica o filtro de status se o usuário selecionou um
        if context['status_filter']:
            q = q.filter(status=context['status_filter'])
            
        context.update({
            'itens': q, 
            'total_qtd': sum(i.quantidade for i in q), 
            'data_inicial_formatada': d_ini.strftime('%d/%m/%Y'), 
            'data_final_formatada': d_fim.strftime('%d/%m/%Y')
        })
        
    return render(request, 'estoque/relatorio_manutencao.html', context)

# ==========================================
# NOVAS VIEWS: MANUTENÇÃO E CADASTROS
# ==========================================

@login_required
def defeito_list(request):
    return render(request, 'estoque/defeito_list.html', {'defeitos': Defeito.objects.all()})

@ti_required
def defeito_form_view(request, id=None):
    defeito = get_object_or_404(Defeito, id=id) if id else None
    if request.method == 'POST':
        form = DefeitoForm(request.POST, instance=defeito)
        if form.is_valid(): 
            form.save()
            return redirect('defeito_list')
    else: 
        form = DefeitoForm(instance=defeito)
    return render(request, 'estoque/defeito_form.html', {'form': form})

@login_required
def especialidade_list(request):
    return render(request, 'estoque/especialidade_list.html', {'especialidades': Especialidade.objects.all()})

@ti_required
def especialidade_form_view(request, id=None):
    especialidade = get_object_or_404(Especialidade, id=id) if id else None
    if request.method == 'POST':
        form = EspecialidadeForm(request.POST, instance=especialidade)
        if form.is_valid(): 
            form.save()
            return redirect('especialidade_list')
    else: 
        form = EspecialidadeForm(instance=especialidade)
    return render(request, 'estoque/especialidade_form.html', {'form': form})

# ==========================================
# FLUXO DE MANUTENÇÃO (Substituir esta seção no views.py)
# ==========================================

@login_required
def manutencao_list(request):
    empresa_id = request.session.get('empresa_id')
    manutencoes = Manutencao.objects.filter(empresa_id=empresa_id).order_by('-data_registro')
    
    status_filter = request.GET.get('status', '')
    if status_filter == 'pendente':
        manutencoes = manutencoes.filter(status='PENDENTE')
    elif status_filter == 'concluido':
        manutencoes = manutencoes.filter(status__in=['REPARADO', 'DESCARTADO'])
        
    return render(request, 'estoque/manutencao_list.html', {
        'manutencoes': manutencoes,
        'status_filter': status_filter
    })

@login_required
def manutencao_create(request):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    
    if request.method == 'POST':
        # Passa a empresa no initial para o clean() do form funcionar
        form = ManutencaoEnvioForm(request.POST, request.FILES, initial={'empresa': empresa})
        if form.is_valid():
            with transaction.atomic():
                manutencao = form.save(commit=False)
                manutencao.empresa = empresa
                manutencao.usuario_registro = request.user
                manutencao.status = 'PENDENTE'
                manutencao.save()
                
                manutencao.produto.atualizar_estoque(empresa)
                messages.success(request, 'Item enviado para manutenção com sucesso!')
                return redirect('manutencao_list')
    else:
        form = ManutencaoEnvioForm(initial={'empresa': empresa})
        form.fields['produto'].queryset = Produto.objects.filter(
            estoques__empresa=empresa, estoques__quantidade__gt=0, ativo=True
        )

    regras = {p.id: {'lote': p.controla_lote} for p in Produto.objects.filter(ativo=True)}
    return render(request, 'estoque/manutencao_form.html', {'form': form, 'produtos_regras_json': json.dumps(regras)})

@login_required
def manutencao_edit(request, id):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    manutencao = get_object_or_404(Manutencao, id=id, empresa=empresa, status='PENDENTE')
    
    if request.method == 'POST':
        form = ManutencaoEnvioForm(request.POST, request.FILES, instance=manutencao, initial={'empresa': empresa})
        if form.is_valid():
            with transaction.atomic():
                form.save()
                manutencao.produto.atualizar_estoque(empresa)
                messages.success(request, 'Manutenção editada com sucesso!')
                return redirect('manutencao_list')
    else:
        form = ManutencaoEnvioForm(instance=manutencao, initial={'empresa': empresa})
        # Ao editar, é importante deixar o produto atual disponível mesmo que o estoque dele fora da manutenção seja 0
        form.fields['produto'].queryset = Produto.objects.filter(ativo=True)
        
        # Injeta o lote atual no formulário se existir
        if manutencao.lote:
            form.fields['lote'].choices = [(manutencao.lote, f"{manutencao.lote} (Atual)")]

    regras = {p.id: {'lote': p.controla_lote} for p in Produto.objects.filter(ativo=True)}
    return render(request, 'estoque/manutencao_form.html', {'form': form, 'manutencao': manutencao, 'produtos_regras_json': json.dumps(regras)})

@login_required
def manutencao_delete(request, id):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    manutencao = get_object_or_404(Manutencao, id=id, empresa=empresa, status='PENDENTE')
    
    if request.method == 'POST':
        with transaction.atomic():
            audit = AuditoriaExclusao.objects.create(
                empresa=empresa, 
                tipo_movimento='MANUTENCAO', 
                identificador=f"Canc. Envio #{manutencao.id} - Defeito: {manutencao.defeito.nome}", 
                usuario=request.user
            )
            ItemAuditoriaExclusao.objects.create(
                auditoria=audit, 
                produto_nome=manutencao.produto.nome, 
                quantidade=manutencao.quantidade, 
                lote=manutencao.lote
            )
            
            produto = manutencao.produto
            manutencao.delete()
            produto.atualizar_estoque(empresa)
            messages.success(request, 'Solicitação excluída. O item retornou ao estoque com sucesso.')
        return redirect('manutencao_list')
        
    return render(request, 'estoque/confirmar_exclusao.html', {'item': f'o envio para manutenção do produto {manutencao.produto.nome}', 'url_cancelar': 'manutencao_list'})

@login_required
def manutencao_concluir(request, id):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    manutencao = get_object_or_404(Manutencao, id=id, empresa=empresa, status='PENDENTE')

    if request.method == 'POST':
        form = ManutencaoConclusaoForm(request.POST, request.FILES, instance=manutencao)
        if form.is_valid():
            with transaction.atomic():
                acao = form.cleaned_data['acao']
                if acao == 'reparar':
                    manutencao.status = 'REPARADO'
                    manutencao.justificativa_descarte = '' 
                else:
                    manutencao.status = 'DESCARTADO'
                    if manutencao.foto_reparo: manutencao.foto_reparo.delete()
                
                manutencao.usuario_conclusao = request.user
                manutencao.data_conclusao = timezone.now()
                manutencao.save()

                if acao == 'reparar':
                    manutencao.produto.atualizar_estoque(empresa)
                    
                messages.success(request, 'Manutenção concluída com sucesso!')
                return redirect('manutencao_list')
    else:
        form = ManutencaoConclusaoForm(instance=manutencao)

    return render(request, 'estoque/manutencao_concluir.html', {'form': form, 'manutencao': manutencao})

@login_required
def manutencao_detail(request, id):
    empresa = get_object_or_404(Empresa, id=request.session['empresa_id'])
    manutencao = get_object_or_404(Manutencao, id=id, empresa=empresa)
    return render(request, 'estoque/manutencao_detail.html', {'manutencao': manutencao})