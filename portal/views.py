from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponseRedirect, HttpResponseServerError
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader
from django.template.response import TemplateResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from . import services
from .forms import EnvioMaterialForm
from .models import Categoria, Material

POR_PAGINA = 10
SESSAO_ULTIMO_ENVIO = "ruas_ultimo_envio_id"
TAMANHO_MAX_BUSCA = 100


def _paginar(request, queryset):
    return Paginator(queryset, POR_PAGINA).get_page(request.GET.get("pagina"))


def _ranking():
    return (
        Material.objects.publicados()
        .filter(visualizacoes__gt=0)
        .order_by("-visualizacoes", "-publicado_em")[:5]
    )


@require_GET
def inicio(request):
    pagina = _paginar(request, Material.objects.publicados())
    return render(
        request,
        "portal/lista.html",
        {"pagina": pagina, "ranking": _ranking(), "eh_inicio": True},
    )


@require_GET
def categoria(request, slug):
    cat = get_object_or_404(Categoria, slug=slug)
    pagina = _paginar(request, Material.objects.publicados().filter(categoria=cat))
    return render(request, "portal/lista.html", {"pagina": pagina, "categoria_atual": cat})


@require_GET
def busca(request):
    termo = request.GET.get("q", "").strip()[:TAMANHO_MAX_BUSCA]
    pagina = None
    if termo:
        # icontains: sem diferenciar maiúsculas/minúsculas; consulta parametrizada pelo ORM.
        qs = Material.objects.publicados().filter(
            Q(titulo__icontains=termo) | Q(artista__nome_artistico__icontains=termo)
        )
        pagina = _paginar(request, qs)
    return render(request, "portal/busca.html", {"pagina": pagina, "termo": termo})


@require_GET
def materia(request, pk):
    material = get_object_or_404(Material.objects.publicados(), pk=pk)
    services.registrar_visualizacao(material.pk)
    return render(request, "portal/materia.html", {"material": material})


@require_GET
def sair_para_link(request, pk, tipo):
    """Conta o clique (agregado) e redireciona para o link já validado no envio."""
    material = get_object_or_404(Material.objects.publicados(), pk=pk)
    destino = {"obra": material.link_obra, "canal": material.link_canal}.get(tipo)
    if not destino:
        raise Http404
    services.registrar_clique(material.pk)
    resposta = HttpResponseRedirect(destino)
    resposta["Referrer-Policy"] = "no-referrer"
    return resposta


@never_cache
@require_http_methods(["GET", "POST"])
def enviar(request):
    if request.method == "POST":
        form = EnvioMaterialForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                material = services.registrar_envio(
                    dados=form.cleaned_data, imagem=form.cleaned_data["imagem"]
                )
            except ValidationError as erro:
                form.add_error("imagem", erro)
            else:
                # O id fica só na sessão de quem enviou: a página de confirmação
                # não aceita identificador na URL.
                request.session[SESSAO_ULTIMO_ENVIO] = material.pk
                return redirect("portal:recebido")
        if "imagem" not in form.errors and request.FILES.get("imagem"):
            form.add_error(
                None,
                "Por segurança, o navegador não mantém o arquivo após um erro. "
                "Selecione a imagem novamente.",
            )
    else:
        form = EnvioMaterialForm()
    return render(request, "portal/enviar.html", {"form": form})


@never_cache
@require_GET
def recebido(request):
    material_id = request.session.get(SESSAO_ULTIMO_ENVIO)
    material = (
        Material.objects.select_related("artista", "categoria").filter(pk=material_id).first()
        if material_id
        else None
    )
    if material is None:
        messages.info(request, "Não há envio recente nesta sessão.")
        return redirect("portal:enviar")
    return render(request, "portal/recebido.html", {"material": material})


def _pode_ver_nao_publicado(user) -> bool:
    return bool(
        user.is_authenticated and user.is_active and user.is_staff
        and user.has_perm("portal.view_material")
    )


@require_GET
def imagem(request, pk, variante):
    """Entrega imagens SOMENTE de materiais aprovados, ou para a equipe editorial.

    Uploads ficam fora de pastas públicas; esta é a única forma de acessá-los.
    Não autorizado e inexistente respondem igual (404), sem revelar o estado.
    """
    if variante not in ("imagem", "miniatura"):
        raise Http404
    material = Material.objects.filter(pk=pk).only("status", "imagem", "miniatura").first()
    if material is None:
        raise Http404
    publico = material.status == Material.Status.APROVADO
    if not publico and not _pode_ver_nao_publicado(request.user):
        raise Http404
    arquivo = material.miniatura if variante == "miniatura" else material.imagem
    if not arquivo:
        raise Http404
    try:
        resposta = FileResponse(arquivo.open("rb"), content_type="image/webp")
    except FileNotFoundError:
        raise Http404
    resposta["X-Content-Type-Options"] = "nosniff"
    resposta["Content-Disposition"] = "inline"
    if publico:
        resposta["Cache-Control"] = "private, max-age=600"
    else:
        resposta["Cache-Control"] = "private, no-store"
    return resposta


def erro_404(request, exception):
    return TemplateResponse(request, "404.html", status=404)


def erro_500(request):
    # Sem context processors: não depende do banco e não expõe detalhes.
    return HttpResponseServerError(loader.get_template("500.html").render())
