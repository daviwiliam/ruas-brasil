"""Regras de negócio do fluxo editorial: envio, aprovação e rejeição.

As views e o painel apenas chamam estas funções; toda transição de estado e
toda checagem de permissão para avaliar passa por aqui.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .imagens import processar_imagem
from .models import Artista, Material

PERMISSAO_AVALIAR = "portal.avaliar_material"


class TransicaoInvalida(ValidationError):
    pass


def registrar_envio(*, dados: dict, imagem) -> Material:
    """Cria artista e material PENDENTE. Nunca publica automaticamente.

    `dados` deve vir de um formulário já validado (inclusive a imagem).
    Cada envio cria um novo Artista: sem conta autenticada, coincidência de nome
    ou e-mail não prova identidade (ver README, seção "Duplicidades").
    """
    imagem_pub, miniatura = processar_imagem(imagem)
    with transaction.atomic():
        artista = Artista.objects.create(
            nome_artistico=dados["nome_artistico"],
            email_contato=dados["email_contato"],
            cidade=dados["cidade"],
            uf=dados["uf"],
        )
        material = Material(
            artista=artista,
            categoria=dados["categoria"],
            titulo=dados["titulo"],
            descricao=dados["descricao"],
            texto_alternativo=dados["texto_alternativo"],
            link_obra=dados.get("link_obra", ""),
            link_canal=dados.get("link_canal", ""),
            status=Material.Status.PENDENTE,
        )
        material.imagem.save(imagem_pub.name, imagem_pub, save=False)
        material.miniatura.save(miniatura.name, miniatura, save=False)
        material.save()
    return material


def pode_avaliar(usuario) -> bool:
    return bool(
        usuario
        and usuario.is_authenticated
        and usuario.is_active
        and usuario.is_staff
        and usuario.has_perm(PERMISSAO_AVALIAR)
    )


def _exigir_permissao(usuario):
    if not pode_avaliar(usuario):
        raise PermissionDenied("Usuário sem permissão para avaliar materiais.")


def aprovar_material(material_id: int, usuario) -> Material:
    """Pendente ou rejeitado -> aprovado. Registra avaliador, avaliação e publicação."""
    _exigir_permissao(usuario)
    with transaction.atomic():
        material = Material.objects.select_for_update().get(pk=material_id)
        if material.status == Material.Status.APROVADO:
            raise TransicaoInvalida("Este material já está aprovado.")
        agora = timezone.now()
        material.status = Material.Status.APROVADO
        material.avaliado_em = agora
        material.publicado_em = agora
        material.avaliado_por = usuario
        material.save(update_fields=["status", "avaliado_em", "publicado_em", "avaliado_por"])
    return material


def rejeitar_material(material_id: int, usuario) -> Material:
    """Pendente ou aprovado -> rejeitado. Remove a publicação."""
    _exigir_permissao(usuario)
    with transaction.atomic():
        material = Material.objects.select_for_update().get(pk=material_id)
        if material.status == Material.Status.REJEITADO:
            raise TransicaoInvalida("Este material já está rejeitado.")
        material.status = Material.Status.REJEITADO
        material.avaliado_em = timezone.now()
        material.publicado_em = None
        material.avaliado_por = usuario
        material.save(update_fields=["status", "avaliado_em", "publicado_em", "avaliado_por"])
    return material


def registrar_visualizacao(material_id: int) -> None:
    Material.objects.filter(pk=material_id, status=Material.Status.APROVADO).update(
        visualizacoes=F("visualizacoes") + 1
    )


def registrar_clique(material_id: int) -> None:
    Material.objects.filter(pk=material_id, status=Material.Status.APROVADO).update(
        cliques=F("cliques") + 1
    )
