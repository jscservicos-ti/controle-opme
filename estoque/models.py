from django.db import models
from django.db.models import Sum
from django.contrib.auth.models import AbstractUser

class Empresa(models.Model):
    nome = models.CharField(max_length=200)
    cnpj = models.CharField(max_length=18, unique=True)
    ativo = models.BooleanField(default=True, verbose_name="Ativo?")
    def __str__(self): return self.nome

class Usuario(AbstractUser):
    nome = models.CharField(max_length=200)
    cpf = models.CharField(max_length=14, unique=True)
    is_ti = models.BooleanField(default=False, verbose_name="Perfil TI?")
    primeiro_acesso = models.BooleanField(default=True)
    empresas = models.ManyToManyField(Empresa, blank=True, related_name='usuarios')

    def __str__(self):
        return f"{self.nome} ({self.username})"

class Especie(models.Model):
    nome = models.CharField(max_length=100)
    ativo = models.BooleanField(default=True, verbose_name="Ativo?")
    def __str__(self): return f"[{self.id}] {self.nome}"

class Marca(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    ativo = models.BooleanField(default=True, verbose_name="Ativo?")
    def __str__(self): return self.nome

class Fornecedor(models.Model):
    nome = models.CharField(max_length=200)
    cnpj = models.CharField(max_length=18, blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    ativo = models.BooleanField(default=True, verbose_name="Ativo?")
    def __str__(self): return f"[{self.id}] {self.nome}"

class Produto(models.Model):
    nome = models.CharField(max_length=200)
    especie = models.ForeignKey(Especie, on_delete=models.PROTECT)
    marca = models.ForeignKey(Marca, on_delete=models.PROTECT, null=True, blank=True)
    controla_lote = models.BooleanField(default=False, verbose_name="Controla Lote?")
    controla_validade = models.BooleanField(default=False, verbose_name="Controla Validade?")
    descricao = models.TextField(blank=True, null=True)
    ativo = models.BooleanField(default=True, verbose_name="Ativo?")

    def __str__(self): return f"[{self.id}] {self.nome}"

    def atualizar_estoque(self, empresa):
        t_in = ItemEntrada.objects.filter(produto=self, entrada__empresa=empresa).aggregate(t=Sum('quantidade'))['t'] or 0
        t_out = ItemSaida.objects.filter(produto=self, saida__empresa=empresa).aggregate(t=Sum('quantidade'))['t'] or 0
        t_loss = ItemBaixa.objects.filter(produto=self, baixa__empresa=empresa).aggregate(t=Sum('quantidade'))['t'] or 0
        
        t_manutencao = Manutencao.objects.filter(
            produto=self, 
            empresa=empresa, 
            status__in=['PENDENTE', 'DESCARTADO']
        ).aggregate(t=Sum('quantidade'))['t'] or 0
        
        saldo = t_in - t_out - t_loss - t_manutencao
        
        estoque_obj, created = Estoque.objects.get_or_create(produto=self, empresa=empresa)
        estoque_obj.quantidade = saldo
        estoque_obj.save()

class Estoque(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='estoques')
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='estoques')
    quantidade = models.IntegerField(default=0)
    class Meta:
        unique_together = ('produto', 'empresa')

class Entrada(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.PROTECT)
    nota_fiscal = models.CharField(max_length=50, blank=True, null=True)
    data_entrada = models.DateTimeField(auto_now_add=True)
    usuario_registro = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='entradas_criadas')

class ItemEntrada(models.Model):
    entrada = models.ForeignKey(Entrada, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT)
    quantidade = models.IntegerField()
    lote = models.CharField(max_length=50, blank=True, null=True)
    validade = models.DateField(blank=True, null=True)

class HistoricoEntrada(models.Model):
    entrada = models.ForeignKey(Entrada, on_delete=models.CASCADE, related_name='historico')
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    data_alteracao = models.DateTimeField(auto_now_add=True)
    detalhes = models.TextField()

class Saida(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)
    paciente = models.CharField(max_length=200)
    atendimento = models.CharField(max_length=50)
    aviso_cirurgia = models.CharField(max_length=50)
    data_saida = models.DateTimeField(auto_now_add=True)
    usuario_registro = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='saidas_criadas')

class ItemSaida(models.Model):
    saida = models.ForeignKey(Saida, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT)
    quantidade = models.IntegerField()
    lote = models.CharField(max_length=50, blank=True, null=True)

class HistoricoSaida(models.Model):
    saida = models.ForeignKey(Saida, on_delete=models.CASCADE, related_name='historico')
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    data_alteracao = models.DateTimeField(auto_now_add=True)
    detalhes = models.TextField()

class MotivoBaixa(models.Model):
    nome = models.CharField(max_length=100)
    ativo = models.BooleanField(default=True, verbose_name="Ativo?")
    def __str__(self): return self.nome

class Baixa(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)
    motivo = models.ForeignKey(MotivoBaixa, on_delete=models.PROTECT)
    data_baixa = models.DateTimeField(auto_now_add=True)
    usuario_registro = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='baixas_criadas')

class ItemBaixa(models.Model):
    baixa = models.ForeignKey(Baixa, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT)
    quantidade = models.IntegerField()
    lote = models.CharField(max_length=50, blank=True, null=True)

class HistoricoBaixa(models.Model):
    baixa = models.ForeignKey(Baixa, on_delete=models.CASCADE, related_name='historico')
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    data_alteracao = models.DateTimeField(auto_now_add=True)
    detalhes = models.TextField()

class AuditoriaExclusao(models.Model):
    TIPO_CHOICES = [
        ('ENTRADA', 'Entrada (NF)'), 
        ('SAIDA', 'Saída (Paciente)'), 
        ('BAIXA', 'Baixa (Descarte)'),
        ('MANUTENCAO', 'Manutenção') # <-- Adicionado aqui
    ]
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)
    tipo_movimento = models.CharField(max_length=15, choices=TIPO_CHOICES)
    identificador = models.CharField(max_length=255)
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    data_exclusao = models.DateTimeField(auto_now_add=True)

class ItemAuditoriaExclusao(models.Model):
    auditoria = models.ForeignKey(AuditoriaExclusao, on_delete=models.CASCADE, related_name='itens')
    produto_nome = models.CharField(max_length=200)
    quantidade = models.IntegerField()
    lote = models.CharField(max_length=50, blank=True, null=True)
    validade = models.CharField(max_length=50, blank=True, null=True)

class Defeito(models.Model):
    nome = models.CharField(max_length=150, unique=True)
    ativo = models.BooleanField(default=True)
    def __str__(self): return self.nome

class Especialidade(models.Model):
    nome = models.CharField(max_length=150, unique=True)
    ativo = models.BooleanField(default=True)
    def __str__(self): return self.nome

class Manutencao(models.Model):
    STATUS_CHOICES = (
        ('PENDENTE', 'Pendente (Em Manutenção)'),
        ('REPARADO', 'Concluído (Retornou ao Estoque)'),
        ('DESCARTADO', 'Concluído (Não Reparado / Descartado)'),
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT)
    quantidade = models.PositiveIntegerField(default=1)
    lote = models.CharField(max_length=50, blank=True, null=True)
    
    defeito = models.ForeignKey(Defeito, on_delete=models.PROTECT)
    especialidade = models.ForeignKey(Especialidade, on_delete=models.PROTECT)
    prontuario = models.CharField(max_length=50, blank=True, null=True)
    
    data_registro = models.DateTimeField(auto_now_add=True)
    data_envio = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE')
    
    foto_defeito = models.ImageField(upload_to='manutencao/defeitos/')
    foto_reparo = models.ImageField(upload_to='manutencao/reparos/', blank=True, null=True)
    justificativa_descarte = models.TextField(blank=True, null=True)
    
    usuario_registro = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='manutencoes_enviadas')
    usuario_conclusao = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='manutencoes_concluidas', blank=True, null=True)
    data_conclusao = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Manutenção #{self.id} - {self.produto.nome} ({self.status})"