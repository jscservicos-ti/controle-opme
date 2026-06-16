from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from django.db.models import Sum
from datetime import date
from .models import (
    Produto, Especie, Fornecedor, Entrada, ItemEntrada, MotivoBaixa, 
    Saida, ItemSaida, Baixa, ItemBaixa, Usuario, Empresa,
    Defeito, Especialidade, Manutencao, Marca,
    LocalEstoque, Transferencia, ItemTransferencia # <-- NOVOS MODELOS
)

class MarcaForm(forms.ModelForm):
    class Meta:
        model = Marca
        fields = ['nome', 'ativo']
        widgets = {'nome': forms.TextInput(attrs={'class': 'form-control'}), 'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'})}

class LocalEstoqueForm(forms.ModelForm):
    class Meta:
        model = LocalEstoque
        fields = ['nome', 'tipo', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Farmácia Central, Centro Cirúrgico...'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ['nome', 'cnpj', 'ativo']
        widgets = {'nome': forms.TextInput(attrs={'class': 'form-control'}), 'cnpj': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '00.000.000/0000-00'}), 'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'})}

class UsuarioForm(forms.ModelForm):
    empresas = forms.ModelMultipleChoiceField(queryset=Empresa.objects.all(), widget=forms.CheckboxSelectMultiple, required=False, label="Acesso às Empresas")
    class Meta:
        model = Usuario
        fields = ['nome', 'cpf', 'username', 'is_ti', 'is_active', 'empresas']
        widgets = {'nome': forms.TextInput(attrs={'class': 'form-control', 'required': True}), 'cpf': forms.TextInput(attrs={'class': 'form-control', 'required': True}), 'username': forms.TextInput(attrs={'class': 'form-control', 'required': True}), 'is_ti': forms.CheckboxInput(attrs={'class': 'form-check-input'}), 'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})}

class MudarSenhaForm(forms.Form):
    nova_senha = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), min_length=8, label="Nova Senha")
    confirmar_senha = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), min_length=8, label="Confirmar Nova Senha")
    def clean(self):
        cleaned_data = super().clean()
        n = cleaned_data.get('nova_senha')
        c = cleaned_data.get('confirmar_senha')
        if n and c and n != c: self.add_error('confirmar_senha', 'As senhas não conferem.')
        return cleaned_data

class FornecedorForm(forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = ['nome', 'cnpj', 'telefone', 'ativo']
        widgets = {'nome': forms.TextInput(attrs={'class': 'form-control'}), 'cnpj': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '00.000.000/0000-00'}), 'telefone': forms.TextInput(attrs={'class': 'form-control'}), 'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'})}

class EspecieForm(forms.ModelForm):
    class Meta:
        model = Especie
        fields = ['nome', 'ativo']
        widgets = {'nome': forms.TextInput(attrs={'class': 'form-control'}), 'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'})}

class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = ['nome', 'especie', 'marca', 'controla_lote', 'controla_validade', 'descricao', 'ativo']
        widgets = {'nome': forms.TextInput(attrs={'class': 'form-control'}), 'especie': forms.Select(attrs={'class': 'form-select'}), 'marca': forms.Select(attrs={'class': 'form-select'}), 'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}), 'controla_lote': forms.CheckboxInput(attrs={'class': 'form-check-input'}), 'controla_validade': forms.CheckboxInput(attrs={'class': 'form-check-input'}), 'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'})}
    def __init__(self, *args, **kwargs):
        super(ProdutoForm, self).__init__(*args, **kwargs)
        self.fields['especie'].queryset = Especie.objects.filter(ativo=True)
        self.fields['marca'].queryset = Marca.objects.filter(ativo=True)

class EntradaForm(forms.ModelForm):
    class Meta:
        model = Entrada
        fields = ['local', 'fornecedor', 'nota_fiscal'] # Adicionado o Local
        widgets = {'local': forms.Select(attrs={'class': 'form-select'}), 'fornecedor': forms.Select(attrs={'class': 'form-select'}), 'nota_fiscal': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional'})}

class ItemEntradaForm(forms.ModelForm):
    class Meta:
        model = ItemEntrada
        fields = ['produto', 'quantidade', 'lote', 'validade']
        widgets = {'produto': forms.Select(attrs={'class': 'form-select'}), 'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}), 'lote': forms.TextInput(attrs={'class': 'form-control'}), 'validade': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'})}
    def clean(self):
        cleaned_data = super().clean()
        produto = cleaned_data.get('produto')
        validade = cleaned_data.get('validade')
        if produto:
            if produto.controla_lote and not cleaned_data.get('lote'): self.add_error('lote', 'Exige Lote.')
            if produto.controla_validade and not validade: self.add_error('validade', 'Exige Validade.')
        return cleaned_data

ItemEntradaFormSet = inlineformset_factory(Entrada, ItemEntrada, form=ItemEntradaForm, extra=1, can_delete=True)

# ==========================================
# SUPER VALIDADOR DE ESTOQUE (ATUALIZADO)
# ==========================================
class ValidaEstoqueFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors): return
        
        # Agora o validador confere o saldo baseado no LOCAL, não mais na empresa inteira
        local_id = getattr(self, 'local_id', None)
        if not local_id: return
        
        consumo_tela = {}
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                p = form.cleaned_data.get('produto')
                lote = form.cleaned_data.get('lote')
                qtd = form.cleaned_data.get('quantidade', 0)
                if not p: continue
                chave = f"{p.id}_{lote}" if lote else f"{p.id}_geral"
                if chave in consumo_tela: consumo_tela[chave]['qtd'] += qtd
                else: consumo_tela[chave] = {'produto': p, 'lote': lote, 'qtd': qtd}
                
        for chave, dados in consumo_tela.items():
            p = dados['produto']
            lote = dados['lote']
            qtd_solicitada = dados['qtd']
            
            # Filtra todas as movimentações APENAS neste local específico
            entradas = ItemEntrada.objects.filter(produto=p, entrada__local_id=local_id)
            saidas = ItemSaida.objects.filter(produto=p, saida__local_id=local_id)
            baixas = ItemBaixa.objects.filter(produto=p, baixa__local_id=local_id)
            transf_in = ItemTransferencia.objects.filter(produto=p, transferencia__local_destino_id=local_id)
            transf_out = ItemTransferencia.objects.filter(produto=p, transferencia__local_origem_id=local_id)
            manutencoes = Manutencao.objects.filter(produto=p, local_id=local_id, status__in=['PENDENTE', 'DESCARTADO'])
            
            if p.controla_lote and lote:
                entradas = entradas.filter(lote=lote)
                saidas = saidas.filter(lote=lote)
                baixas = baixas.filter(lote=lote)
                transf_in = transf_in.filter(lote=lote)
                transf_out = transf_out.filter(lote=lote)
                manutencoes = manutencoes.filter(lote=lote)
                
            t_in = entradas.aggregate(t=Sum('quantidade'))['t'] or 0
            t_out = saidas.aggregate(t=Sum('quantidade'))['t'] or 0
            t_loss = baixas.aggregate(t=Sum('quantidade'))['t'] or 0
            t_transf_in = transf_in.aggregate(t=Sum('quantidade'))['t'] or 0
            t_transf_out = transf_out.aggregate(t=Sum('quantidade'))['t'] or 0
            t_manutencao = manutencoes.aggregate(t=Sum('quantidade'))['t'] or 0
            
            # Novo cálculo de saldo do local
            saldo_real = (t_in + t_transf_in) - (t_out + t_loss + t_transf_out + t_manutencao)
            
            # Se for edição, devolve a quantidade atual para não barrar o próprio save
            if self.instance.pk:
                if hasattr(self.instance, 'paciente'): 
                    saldo_real += ItemSaida.objects.filter(saida=self.instance, produto=p, lote=lote).aggregate(t=Sum('quantidade'))['t'] or 0
                elif hasattr(self.instance, 'motivo'): 
                    saldo_real += ItemBaixa.objects.filter(baixa=self.instance, produto=p, lote=lote).aggregate(t=Sum('quantidade'))['t'] or 0
                elif hasattr(self.instance, 'local_origem'): 
                    saldo_real += ItemTransferencia.objects.filter(transferencia=self.instance, produto=p, lote=lote).aggregate(t=Sum('quantidade'))['t'] or 0
                    
            if qtd_solicitada > saldo_real:
                raise forms.ValidationError(f"Estoque insuficiente no local selecionado: {p.nome}. Saldo: {saldo_real}.")

class SaidaForm(forms.ModelForm):
    class Meta:
        model = Saida
        fields = ['local', 'paciente', 'atendimento', 'aviso_cirurgia'] # Adicionado o Local
        widgets = {'local': forms.Select(attrs={'class': 'form-select'}), 'paciente': forms.TextInput(attrs={'class': 'form-control'}), 'atendimento': forms.TextInput(attrs={'class': 'form-control'}), 'aviso_cirurgia': forms.TextInput(attrs={'class': 'form-control'})}

class ItemSaidaForm(forms.ModelForm):
    class Meta:
        model = ItemSaida
        fields = ['produto', 'quantidade', 'lote']
        widgets = {'produto': forms.Select(attrs={'class': 'form-select'}), 'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}), 'lote': forms.TextInput(attrs={'class': 'form-control'})}

ItemSaidaFormSet = inlineformset_factory(Saida, ItemSaida, form=ItemSaidaForm, formset=ValidaEstoqueFormSet, extra=1, can_delete=True)

class MotivoBaixaForm(forms.ModelForm):
    class Meta:
        model = MotivoBaixa
        fields = ['nome', 'ativo']
        widgets = {'nome': forms.TextInput(attrs={'class': 'form-control'}), 'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'})}

class BaixaForm(forms.ModelForm):
    class Meta:
        model = Baixa
        fields = ['local', 'motivo'] # Adicionado o Local
        widgets = {'local': forms.Select(attrs={'class': 'form-select'}), 'motivo': forms.Select(attrs={'class': 'form-select'})}

class ItemBaixaForm(forms.ModelForm):
    class Meta:
        model = ItemBaixa
        fields = ['produto', 'quantidade', 'lote']
        widgets = {'produto': forms.Select(attrs={'class': 'form-select'}), 'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}), 'lote': forms.TextInput(attrs={'class': 'form-control'})}

ItemBaixaFormSet = inlineformset_factory(Baixa, ItemBaixa, form=ItemBaixaForm, formset=ValidaEstoqueFormSet, extra=1, can_delete=True)


# ==========================================
# NOVO: FORMULÁRIOS DE TRANSFERÊNCIA
# ==========================================
class TransferenciaForm(forms.ModelForm):
    class Meta:
        model = Transferencia
        fields = ['local_origem', 'local_destino']
        widgets = {
            'local_origem': forms.Select(attrs={'class': 'form-select'}),
            'local_destino': forms.Select(attrs={'class': 'form-select'})
        }
        labels = {
            'local_origem': 'Retirar de (Origem)',
            'local_destino': 'Enviar para (Destino)'
        }
        
    def clean(self):
        cleaned_data = super().clean()
        origem = cleaned_data.get('local_origem')
        destino = cleaned_data.get('local_destino')
        if origem and destino and origem == destino:
            raise forms.ValidationError("A origem e o destino não podem ser o mesmo local.")
        return cleaned_data

class ItemTransferenciaForm(forms.ModelForm):
    class Meta:
        model = ItemTransferencia
        fields = ['produto', 'quantidade', 'lote']
        widgets = {
            'produto': forms.Select(attrs={'class': 'form-select'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'lote': forms.TextInput(attrs={'class': 'form-control'})
        }

ItemTransferenciaFormSet = inlineformset_factory(
    Transferencia, ItemTransferencia, form=ItemTransferenciaForm, 
    formset=ValidaEstoqueFormSet, extra=1, can_delete=True
)


class DefeitoForm(forms.ModelForm):
    class Meta:
        model = Defeito
        fields = ['nome', 'ativo']
        widgets = {'nome': forms.TextInput(attrs={'class': 'form-control'}), 'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'})}

class EspecialidadeForm(forms.ModelForm):
    class Meta:
        model = Especialidade
        fields = ['nome', 'ativo']
        widgets = {'nome': forms.TextInput(attrs={'class': 'form-control'}), 'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'})}

class ManutencaoEnvioForm(forms.ModelForm):
    class Meta:
        model = Manutencao
        fields = ['local', 'produto', 'quantidade', 'lote', 'defeito', 'especialidade', 'prontuario', 'data_envio', 'foto_defeito'] # Adicionado o Local
        widgets = {
            'local': forms.Select(attrs={'class': 'form-select'}),
            'produto': forms.Select(attrs={'class': 'form-select'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'lote': forms.Select(attrs={'class': 'form-select'}), 
            'defeito': forms.Select(attrs={'class': 'form-select'}),
            'especialidade': forms.Select(attrs={'class': 'form-select'}),
            'prontuario': forms.TextInput(attrs={'class': 'form-control'}),
            'data_envio': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'foto_defeito': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        local = cleaned_data.get('local')
        produto = cleaned_data.get('produto')
        quantidade = cleaned_data.get('quantidade')
        lote = cleaned_data.get('lote')

        if local and produto and quantidade:
            if produto.controla_lote and not lote:
                self.add_error('lote', 'Este produto exige a identificação do lote.')
                return cleaned_data

            entradas = ItemEntrada.objects.filter(produto=produto, entrada__local=local)
            saidas = ItemSaida.objects.filter(produto=produto, saida__local=local)
            baixas = ItemBaixa.objects.filter(produto=produto, baixa__local=local)
            transf_in = ItemTransferencia.objects.filter(produto=produto, transferencia__local_destino=local)
            transf_out = ItemTransferencia.objects.filter(produto=produto, transferencia__local_origem=local)
            manutencoes = Manutencao.objects.filter(produto=produto, local=local, status__in=['PENDENTE', 'DESCARTADO'])

            if produto.controla_lote and lote:
                entradas = entradas.filter(lote=lote)
                saidas = saidas.filter(lote=lote)
                baixas = baixas.filter(lote=lote)
                transf_in = transf_in.filter(lote=lote)
                transf_out = transf_out.filter(lote=lote)
                manutencoes = manutencoes.filter(lote=lote)

            t_in = entradas.aggregate(t=Sum('quantidade'))['t'] or 0
            t_out = saidas.aggregate(t=Sum('quantidade'))['t'] or 0
            t_loss = baixas.aggregate(t=Sum('quantidade'))['t'] or 0
            t_transf_in = transf_in.aggregate(t=Sum('quantidade'))['t'] or 0
            t_transf_out = transf_out.aggregate(t=Sum('quantidade'))['t'] or 0
            t_manut = manutencoes.aggregate(t=Sum('quantidade'))['t'] or 0

            saldo_atual = (t_in + t_transf_in) - (t_out + t_loss + t_transf_out + t_manut)

            if self.instance.pk:
                saldo_atual += self.instance.quantidade

            if quantidade > saldo_atual:
                raise forms.ValidationError(f"Saldo insuficiente no local selecionado! Saldo atual para envio: {saldo_atual}")
        
        return cleaned_data

class ManutencaoConclusaoForm(forms.ModelForm):
    ACAO_CHOICES = [('reparar', 'Devolver ao Estoque'), ('descartar', 'Item Não Reparado')]
    acao = forms.ChoiceField(choices=ACAO_CHOICES, widget=forms.RadioSelect(attrs={'class': 'form-check-input'}))
    class Meta:
        model = Manutencao
        fields = ['foto_reparo', 'justificativa_descarte']
        widgets = {
            'foto_reparo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'justificativa_descarte': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }