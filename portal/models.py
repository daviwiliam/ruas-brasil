import secrets

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.urls import reverse

UFS = [
    ("AC", "Acre"), ("AL", "Alagoas"), ("AP", "Amapá"), ("AM", "Amazonas"),
    ("BA", "Bahia"), ("CE", "Ceará"), ("DF", "Distrito Federal"),
    ("ES", "Espírito Santo"), ("GO", "Goiás"), ("MA", "Maranhão"),
    ("MT", "Mato Grosso"), ("MS", "Mato Grosso do Sul"), ("MG", "Minas Gerais"),
    ("PA", "Pará"), ("PB", "Paraíba"), ("PR", "Paraná"), ("PE", "Pernambuco"),
    ("PI", "Piauí"), ("RJ", "Rio de Janeiro"), ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"), ("RO", "Rondônia"), ("RR", "Roraima"),
    ("SC", "Santa Catarina"), ("SP", "São Paulo"), ("SE", "Sergipe"),
    ("TO", "Tocantins"),
]


def gerar_protocolo() -> str:
    """Protocolo legível e não sequencial (não revela volume nem permite adivinhação)."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    corpo = "".join(secrets.choice(alfabeto) for _ in range(10))
    return f"RB-{corpo[:5]}-{corpo[5:]}"


class Artista(models.Model):
    """Identidade informada no envio. Não há conta de artista no MVP: cada envio
    cria um registro novo; duplicidades são consolidadas manualmente no painel."""

    nome_artistico = models.CharField("nome artístico", max_length=120)
    email_contato = models.EmailField("e-mail de contato", max_length=254)
    cidade = models.CharField(max_length=100)
    uf = models.CharField("UF", max_length=2, choices=UFS)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "artista"
        verbose_name_plural = "artistas"
        ordering = ["nome_artistico", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(uf__in=[sigla for sigla, _ in UFS]), name="artista_uf_valida"
            ),
        ]

    def __str__(self):
        return f"{self.nome_artistico} ({self.cidade}/{self.uf})"


class Categoria(models.Model):
    nome = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return reverse("portal:categoria", args=[self.slug])


class MaterialQuerySet(models.QuerySet):
    def publicados(self):
        return (
            self.filter(status=Material.Status.APROVADO)
            .select_related("artista", "categoria")
            .order_by("-publicado_em", "-id")
        )


def caminho_imagem(instancia, nome):
    return f"materiais/{nome}"


class Material(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        APROVADO = "aprovado", "Aprovado"
        REJEITADO = "rejeitado", "Rejeitado"

    protocolo = models.CharField(max_length=20, unique=True, default=gerar_protocolo, editable=False)
    artista = models.ForeignKey(Artista, on_delete=models.PROTECT, related_name="materiais")
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="materiais")
    titulo = models.CharField("título", max_length=150)
    descricao = models.TextField("descrição", max_length=5000)
    imagem = models.ImageField(upload_to=caminho_imagem, width_field="imagem_largura", height_field="imagem_altura")
    imagem_largura = models.PositiveIntegerField(editable=False, default=0)
    imagem_altura = models.PositiveIntegerField(editable=False, default=0)
    miniatura = models.ImageField(upload_to=caminho_imagem, editable=False)
    texto_alternativo = models.CharField("texto alternativo da imagem", max_length=250)
    link_obra = models.URLField("link da obra", max_length=500, blank=True)
    link_canal = models.URLField("link do canal do artista", max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDENTE, db_index=True)
    enviado_em = models.DateTimeField("enviado em", auto_now_add=True)
    avaliado_em = models.DateTimeField("avaliado em", null=True, blank=True, editable=False)
    publicado_em = models.DateTimeField("publicado em", null=True, blank=True, editable=False)
    avaliado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="materiais_avaliados",
        verbose_name="avaliado por",
    )
    # Contadores agregados (sem dados pessoais).
    visualizacoes = models.PositiveIntegerField("visualizações", default=0, editable=False)
    cliques = models.PositiveIntegerField("cliques em links", default=0, editable=False)

    objects = MaterialQuerySet.as_manager()

    class Meta:
        verbose_name = "material"
        verbose_name_plural = "materiais"
        ordering = ["-enviado_em"]
        permissions = [("avaliar_material", "Pode aprovar ou rejeitar materiais")]
        indexes = [models.Index(fields=["status", "-publicado_em"], name="material_publicados_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["pendente", "aprovado", "rejeitado"]),
                name="material_status_valido",
            ),
            models.CheckConstraint(
                condition=Q(
                    status="pendente",
                    avaliado_em__isnull=True,
                    publicado_em__isnull=True,
                    avaliado_por__isnull=True,
                )
                | Q(
                    status="aprovado",
                    avaliado_em__isnull=False,
                    publicado_em__isnull=False,
                    avaliado_por__isnull=False,
                )
                | Q(
                    status="rejeitado",
                    avaliado_em__isnull=False,
                    publicado_em__isnull=True,
                    avaliado_por__isnull=False,
                ),
                name="material_estado_coerente",
            ),
            models.CheckConstraint(
                condition=Q(avaliado_em__isnull=True) | Q(avaliado_em__gte=F("enviado_em")),
                name="material_avaliacao_apos_envio",
            ),
            models.CheckConstraint(
                condition=Q(publicado_em__isnull=True) | Q(publicado_em__gte=F("enviado_em")),
                name="material_publicacao_apos_envio",
            ),
        ]

    def __str__(self):
        return f"{self.titulo} — {self.artista.nome_artistico}"

    @property
    def publicado(self) -> bool:
        return self.status == self.Status.APROVADO

    def get_absolute_url(self):
        return reverse("portal:materia", args=[self.pk])


class ControleLogin(models.Model):
    """Contador de falhas de login por conta ou IP (ver portal/login_limiter.py)."""

    class Tipo(models.TextChoices):
        CONTA = "conta", "Conta"
        IP = "ip", "IP"

    tipo = models.CharField(max_length=5, choices=Tipo.choices)
    chave = models.CharField(max_length=150)
    falhas = models.PositiveSmallIntegerField(default=0)
    janela_inicio = models.DateTimeField(null=True, blank=True)
    bloqueado_ate = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "controle de login"
        verbose_name_plural = "controles de login"
        constraints = [models.UniqueConstraint(fields=["tipo", "chave"], name="controle_login_unico")]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.chave}"
