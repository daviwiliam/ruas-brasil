from urllib.parse import urlsplit

from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from . import login_limiter
from .imagens import validar_imagem
from .models import UFS, Categoria, Material


def validar_link_http(valor: str) -> None:
    """Somente http:// ou https:// com domínio. Bloqueia javascript:, data:, etc."""
    if not valor:
        return
    partes = urlsplit(valor)
    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise ValidationError(
            "Use um endereço que comece com http:// ou https://.", code="esquema"
        )
    if partes.username or partes.password:
        raise ValidationError("O link não pode conter usuário ou senha.", code="credenciais")
    URLValidator(schemes=["http", "https"], message="Informe um endereço válido, como https://example.com.")(valor)


def _sem_controle(valor: str) -> str:
    """Remove caracteres de controle invisíveis (mantém quebras de linha)."""
    return "".join(c for c in valor if c in "\n\t" or ord(c) >= 32).replace("\r", "")


class LinkField(forms.URLField):
    default_validators = [validar_link_http]

    def __init__(self, **kwargs):
        kwargs.setdefault("assume_scheme", "https")
        kwargs.setdefault("max_length", 500)
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)


class EnvioMaterialForm(forms.Form):
    nome_artistico = forms.CharField(
        label="Nome artístico", max_length=120,
        widget=forms.TextInput(attrs={"autocomplete": "nickname"}),
    )
    email_contato = forms.EmailField(
        label="E-mail de contato", max_length=254,
        help_text="Usado só pela equipe editorial. Nunca aparece no portal.",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    cidade = forms.CharField(
        label="Cidade", max_length=100,
        widget=forms.TextInput(attrs={"autocomplete": "address-level2"}),
    )
    uf = forms.ChoiceField(label="UF", choices=[("", "Selecione")] + UFS, initial="PR")
    titulo = forms.CharField(label="Título do trabalho", max_length=150)
    descricao = forms.CharField(
        label="Descrição",
        max_length=5000,
        help_text="Texto simples, até 5.000 caracteres. Conte sobre o trabalho e o processo.",
        widget=forms.Textarea(attrs={"rows": 7}),
    )
    categoria = forms.ModelChoiceField(
        label="Categoria", queryset=Categoria.objects.all(), empty_label="Selecione"
    )
    imagem = forms.FileField(
        label="Imagem",
        help_text="JPEG, PNG ou WebP. Até 5 MB e 4096 × 4096 pixels.",
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )
    texto_alternativo = forms.CharField(
        label="Texto alternativo da imagem",
        max_length=250,
        help_text="Descreva o que aparece na imagem para quem usa leitor de tela.",
    )
    link_obra = LinkField(label="Link da obra (opcional)", help_text="Ex.: https://example.com/minha-obra")
    link_canal = LinkField(label="Link do canal do artista (opcional)")

    def clean_imagem(self):
        arquivo = self.cleaned_data["imagem"]
        validar_imagem(arquivo)
        return arquivo

    def _limpar_texto(self, campo):
        valor = _sem_controle(self.cleaned_data[campo]).strip()
        if not valor:
            raise ValidationError("Este campo é obrigatório.", code="required")
        return valor

    def clean_nome_artistico(self):
        return self._limpar_texto("nome_artistico")

    def clean_cidade(self):
        return self._limpar_texto("cidade")

    def clean_titulo(self):
        return self._limpar_texto("titulo")

    def clean_descricao(self):
        return self._limpar_texto("descricao")

    def clean_texto_alternativo(self):
        return self._limpar_texto("texto_alternativo")


class MaterialAdminForm(forms.ModelForm):
    """Edição editorial da apresentação. Status e datas não são editáveis aqui."""

    link_obra = LinkField(label="Link da obra")
    link_canal = LinkField(label="Link do canal do artista")

    class Meta:
        model = Material
        fields = [
            "titulo", "descricao", "categoria", "artista",
            "texto_alternativo", "link_obra", "link_canal",
        ]


class AdminLoginLimitadoForm(AdminAuthenticationForm):
    """Login do painel com limitação de tentativas por conta e por IP."""

    error_messages = {
        **AdminAuthenticationForm.error_messages,
        "bloqueado": (
            "Muitas tentativas sem sucesso. Por segurança, o acesso foi bloqueado "
            "temporariamente. Tente novamente em 15 minutos."
        ),
    }

    def clean(self):
        username = self.cleaned_data.get("username") or ""
        ip = login_limiter.obter_ip(self.request) if self.request else "desconhecido"
        if login_limiter.esta_bloqueado(username, ip):
            raise ValidationError(self.error_messages["bloqueado"], code="bloqueado")
        try:
            dados = super().clean()
        except ValidationError:
            login_limiter.registrar_falha(username, ip)
            raise
        login_limiter.registrar_sucesso(username)
        return dados
