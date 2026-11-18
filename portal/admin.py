from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from . import services
from .forms import AdminLoginLimitadoForm, MaterialAdminForm
from .models import Artista, Categoria, ControleLogin, Material

admin.site.login_form = AdminLoginLimitadoForm

ROTULOS_STATUS = {
    Material.Status.PENDENTE: ("◷", "Pendente", "pendente"),
    Material.Status.APROVADO: ("✓", "Aprovado", "aprovado"),
    Material.Status.REJEITADO: ("✕", "Rejeitado", "rejeitado"),
}


def rotulo_status(status):
    simbolo, texto, classe = ROTULOS_STATUS[status]
    return format_html(
        '<span class="rb-status rb-status--{}"><span aria-hidden="true">{}</span> {}</span>',
        classe, simbolo, texto,
    )


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nome", "slug"]
    prepopulated_fields = {"slug": ["nome"]}
    search_fields = ["nome"]


@admin.register(Artista)
class ArtistaAdmin(admin.ModelAdmin):
    list_display = ["nome_artistico", "cidade", "uf", "email_contato", "total_materiais", "criado_em"]
    list_filter = ["uf"]
    search_fields = ["nome_artistico", "email_contato", "cidade"]
    readonly_fields = ["criado_em"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_total=Count("materiais"))

    @admin.display(description="materiais", ordering="_total")
    def total_materiais(self, obj):
        return obj._total


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    form = MaterialAdminForm
    list_display = ["titulo", "nome_artista", "categoria", "status_exibicao", "enviado_em", "avaliado_por"]
    list_filter = ["status", "categoria"]
    search_fields = ["titulo", "artista__nome_artistico", "protocolo"]
    list_select_related = ["artista", "categoria", "avaliado_por"]
    autocomplete_fields = ["artista"]
    date_hierarchy = "enviado_em"
    actions = ["aprovar_selecionados", "rejeitar_selecionados"]
    readonly_fields = [
        "protocolo", "status_exibicao", "previa_imagem", "contato_artista",
        "enviado_em", "avaliado_em", "publicado_em", "avaliado_por",
        "visualizacoes", "cliques",
    ]
    fieldsets = [
        ("Situação", {"fields": ["protocolo", "status_exibicao", "enviado_em", "avaliado_em",
                                 "publicado_em", "avaliado_por"]}),
        ("Apresentação", {"fields": ["titulo", "categoria", "descricao", "previa_imagem",
                                     "texto_alternativo", "link_obra", "link_canal"]}),
        ("Artista", {"fields": ["artista", "contato_artista"],
                     "description": "Para consolidar duplicidades, escolha aqui o cadastro "
                                    "de artista correto e depois exclua o registro sem materiais."}),
        ("Métricas agregadas", {"fields": ["visualizacoes", "cliques"]}),
    ]

    # Materiais entram apenas pelo formulário público.
    def has_add_permission(self, request):
        return False

    def has_avaliar_permission(self, request):
        return services.pode_avaliar(request.user)

    @admin.display(description="artista", ordering="artista__nome_artistico")
    def nome_artista(self, obj):
        return obj.artista.nome_artistico

    @admin.display(description="status", ordering="status")
    def status_exibicao(self, obj):
        return rotulo_status(obj.status)

    @admin.display(description="contato (privado)")
    def contato_artista(self, obj):
        a = obj.artista
        return f"{a.email_contato} — {a.cidade}/{a.uf}"

    @admin.display(description="imagem")
    def previa_imagem(self, obj):
        if not obj.pk:
            return "—"
        url = reverse("portal:imagem", args=[obj.pk, "miniatura"])
        return format_html(
            '<img src="{}" alt="{}" width="320" height="240" class="rb-previa">',
            url, obj.texto_alternativo,
        )

    # ------------------------------------------------------------------
    # Aprovar / rejeitar: somente POST, CSRF e permissão "avaliar_material".
    # ------------------------------------------------------------------
    def get_urls(self):
        extras = [
            path("<int:object_id>/aprovar/", self.admin_site.admin_view(self.aprovar_view),
                 name="portal_material_aprovar"),
            path("<int:object_id>/rejeitar/", self.admin_site.admin_view(self.rejeitar_view),
                 name="portal_material_rejeitar"),
        ]
        return extras + super().get_urls()

    def _avaliar(self, request, object_id, funcao, sucesso):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self.has_avaliar_permission(request):
            raise PermissionDenied
        material = get_object_or_404(Material, pk=object_id)
        try:
            funcao(material.pk, request.user)
        except ValidationError as erro:
            self.message_user(request, " ".join(erro.messages), messages.WARNING)
        else:
            self.message_user(request, sucesso.format(titulo=material.titulo), messages.SUCCESS)
        return HttpResponseRedirect(reverse("admin:portal_material_change", args=[material.pk]))

    def aprovar_view(self, request, object_id):
        return self._avaliar(request, object_id, services.aprovar_material,
                             "✓ “{titulo}” foi aprovado e publicado.")

    def rejeitar_view(self, request, object_id):
        return self._avaliar(request, object_id, services.rejeitar_material,
                             "✕ “{titulo}” foi rejeitado e não aparece no portal.")

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["pode_avaliar"] = self.has_avaliar_permission(request)
        return super().change_view(request, object_id, form_url, extra_context)

    def _avaliar_lote(self, request, queryset, funcao, verbo):
        feitos, ignorados = 0, 0
        for pk in queryset.values_list("pk", flat=True):
            try:
                funcao(pk, request.user)
                feitos += 1
            except ValidationError:
                ignorados += 1
        self.message_user(request, f"{feitos} material(is) {verbo}; {ignorados} já estavam nesse estado.")

    @admin.action(description="Aprovar e publicar selecionados", permissions=["avaliar"])
    def aprovar_selecionados(self, request, queryset):
        self._avaliar_lote(request, queryset, services.aprovar_material, "aprovado(s)")

    @admin.action(description="Rejeitar selecionados", permissions=["avaliar"])
    def rejeitar_selecionados(self, request, queryset):
        self._avaliar_lote(request, queryset, services.rejeitar_material, "rejeitado(s)")


@admin.register(ControleLogin)
class ControleLoginAdmin(admin.ModelAdmin):
    """Permite consultar e, excluindo o registro, desbloquear uma conta ou IP."""

    list_display = ["tipo", "chave", "falhas", "janela_inicio", "bloqueado_ate"]
    list_filter = ["tipo"]
    search_fields = ["chave"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
