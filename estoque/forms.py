from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from django.db.models import Q, Sum
from datetime import date
from .models import Produto, Especie, Fornecedor, Entrada, ItemEntrada, MotivoBaixa, Saida, ItemSaida, Baixa, ItemBaixa, Usuario, Empresa

class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ['nome', 'cnpj', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'cnpj': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '00.000.000/0000-00'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class UsuarioForm(forms.ModelForm):
    empresas = forms.ModelMultipleChoiceField(
        queryset=Empresa.objects.all(), 
        widget=forms.CheckboxSelectMultiple, 
        required=False, 
        label="Acesso às Empresas"
    )
    class Meta:
        model = Usuario
        fields = ['nome', 'cpf', 'username', 'is_ti', 'is_active', 'empresas']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'required': True}),
            'cpf': forms.TextInput(attrs={'class': 'form-control', 'required': True}),
            'username': forms.TextInput(attrs={'class': 'form-control', 'required': True}),
            'is_ti': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

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
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'cnpj': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '00.000.000/0000-00'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class EspecieForm(forms.ModelForm):
    class Meta:
        model = Especie
        fields = ['nome', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = ['nome', 'especie', 'controla_lote', 'controla_validade', 'descricao', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'especie': forms.Select(attrs={'class': 'form-select'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'controla_lote': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'controla_validade': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    def __init__(self, *args, **kwargs):
        super(ProdutoForm, self).__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.especie and not self.instance.especie.ativo:
            self.fields['especie'].queryset = Especie.objects.filter(Q(ativo=True) | Q(id=self.instance.especie.id))
        else: self.fields['especie'].queryset = Especie.objects.filter(ativo=True)

class EntradaForm(forms.ModelForm):
    class Meta:
        model = Entrada
        fields = ['fornecedor', 'nota_fiscal']
        widgets = {
            'fornecedor': forms.Select(attrs={'class': 'form-select'}),
            'nota_fiscal': forms.TextInput(attrs={'class': 'form-control'}),
        }

class ItemEntradaForm(forms.ModelForm):
    class Meta:
        model = ItemEntrada
        fields = ['produto', 'quantidade', 'lote', 'validade']
        widgets = {
            'produto': forms.Select(attrs={'class': 'form-select'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'lote': forms.TextInput(attrs={'class': 'form-control'}),
            'validade': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
    def clean(self):
        cleaned_data = super().clean()
        produto = cleaned_data.get('produto')
        validade = cleaned_data.get('validade')
        if produto:
            if produto.controla_lote and not cleaned_data.get('lote'): self.add_error('lote', 'Exige Lote.')
            if produto.controla_validade and not validade: self.add_error('validade', 'Exige Validade.')
            if not self.instance.pk:
                if produto.controla_validade and validade and validade < date.today(): 
                    self.add_error('validade', 'Não é permitido registrar entrada de produtos já vencidos.')
        return cleaned_data

ItemEntradaFormSet = inlineformset_factory(Entrada, ItemEntrada, form=ItemEntradaForm, extra=1, can_delete=False)

class ValidaEstoqueFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors): return
        empresa_id = getattr(self, 'empresa_id', None)
        if not empresa_id: return

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
            
            entradas = ItemEntrada.objects.filter(produto=p, entrada__empresa_id=empresa_id)
            saidas = ItemSaida.objects.filter(produto=p, saida__empresa_id=empresa_id)
            baixas = ItemBaixa.objects.filter(produto=p, baixa__empresa_id=empresa_id)
            
            if p.controla_lote and lote:
                entradas = entradas.filter(lote=lote)
                saidas = saidas.filter(lote=lote)
                baixas = baixas.filter(lote=lote)
                
            t_in = entradas.aggregate(t=Sum('quantidade'))['t'] or 0
            t_out = saidas.aggregate(t=Sum('quantidade'))['t'] or 0
            t_loss = baixas.aggregate(t=Sum('quantidade'))['t'] or 0
            saldo_real = t_in - t_out - t_loss
            
            if self.instance.pk:
                if hasattr(self.instance, 'paciente'):
                    old_qs = ItemSaida.objects.filter(saida=self.instance, produto=p, lote=lote).aggregate(t=Sum('quantidade'))['t'] or 0
                    saldo_real += old_qs
                elif hasattr(self.instance, 'motivo'):
                    old_qs = ItemBaixa.objects.filter(baixa=self.instance, produto=p, lote=lote).aggregate(t=Sum('quantidade'))['t'] or 0
                    saldo_real += old_qs

            if qtd_solicitada > saldo_real:
                texto_lote = f" (Lote {lote})" if lote else ""
                raise forms.ValidationError(f"ESTOQUE INSUFICIENTE NESTA EMPRESA: Solicitação: {qtd_solicitada}x do produto {p.nome}{texto_lote}. Saldo: {saldo_real}.")

class SaidaForm(forms.ModelForm):
    class Meta:
        model = Saida
        fields = ['paciente', 'atendimento', 'aviso_cirurgia']
        widgets = {
            'paciente': forms.TextInput(attrs={'class': 'form-control'}),
            'atendimento': forms.TextInput(attrs={'class': 'form-control'}),
            'aviso_cirurgia': forms.TextInput(attrs={'class': 'form-control'}),
        }

class ItemSaidaForm(forms.ModelForm):
    class Meta:
        model = ItemSaida
        fields = ['produto', 'quantidade', 'lote']
        widgets = {
            'produto': forms.Select(attrs={'class': 'form-select'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'lote': forms.TextInput(attrs={'class': 'form-control'}),
        }
    def clean(self):
        cleaned_data = super().clean()
        produto = cleaned_data.get('produto')
        lote = cleaned_data.get('lote')
        if produto and produto.controla_lote and not lote:
            self.add_error('lote', 'É obrigatório selecionar o Lote consumido.')
        return cleaned_data

ItemSaidaFormSet = inlineformset_factory(Saida, ItemSaida, form=ItemSaidaForm, formset=ValidaEstoqueFormSet, extra=1, can_delete=False)

class MotivoBaixaForm(forms.ModelForm):
    class Meta:
        model = MotivoBaixa
        fields = ['nome', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class BaixaForm(forms.ModelForm):
    class Meta:
        model = Baixa
        fields = ['motivo']
        widgets = {
            'motivo': forms.Select(attrs={'class': 'form-select'}),
        }

class ItemBaixaForm(forms.ModelForm):
    class Meta:
        model = ItemBaixa
        fields = ['produto', 'quantidade', 'lote']
        widgets = {
            'produto': forms.Select(attrs={'class': 'form-select'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'lote': forms.TextInput(attrs={'class': 'form-control'}),
        }
    def clean(self):
        cleaned_data = super().clean()
        produto = cleaned_data.get('produto')
        lote = cleaned_data.get('lote')
        if produto and produto.controla_lote and not lote:
            self.add_error('lote', 'É obrigatório selecionar o Lote descartado.')
        return cleaned_data

ItemBaixaFormSet = inlineformset_factory(Baixa, ItemBaixa, form=ItemBaixaForm, formset=ValidaEstoqueFormSet, extra=1, can_delete=False)