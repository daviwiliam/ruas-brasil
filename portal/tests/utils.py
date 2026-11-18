import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from portal import services
from portal.models import Categoria, Material

SENHA_FORTE = "Ruas-Brasil-teste-2026!"


def gerar_imagem(formato="PNG", tamanho=(800, 600), nome=None, cor=(31, 61, 43), modo="RGB", **salvar):
    buffer = io.BytesIO()
    Image.new(modo, tamanho, cor).save(buffer, format=formato, **salvar)
    extensao = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "BMP": "bmp", "TIFF": "tif"}[formato]
    mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(formato, "image/" + extensao)
    return SimpleUploadedFile(nome or f"teste.{extensao}", buffer.getvalue(), content_type=mime)


def dados_validos(categoria, **extra):
    dados = {
        "nome_artistico": "Lua Norte",
        "email_contato": "lua.norte@example.com",
        "cidade": "Piraquara",
        "uf": "PR",
        "titulo": "Vozes do Bairro",
        "descricao": "EP independente com quatro faixas sobre encontros e histórias da cidade.",
        "categoria": categoria.pk,
        "texto_alternativo": "Capa do EP com formas verdes e amarelas.",
        "link_obra": "https://example.com/vozes-do-bairro",
        "link_canal": "https://example.com/lua-norte",
    }
    dados.update(extra)
    return dados


class MidiaTemporariaTestCase(TestCase):
    """Isola os uploads de cada classe de teste em um diretório temporário."""

    @classmethod
    def setUpClass(cls):
        cls._midia = tempfile.mkdtemp(prefix="ruas-testes-")
        cls._override = override_settings(MEDIA_ROOT=cls._midia)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._midia, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.musica = Categoria.objects.create(nome="Música", slug="musica")
        cls.moda = Categoria.objects.create(nome="Moda", slug="moda")
        cls.editor = criar_editor("editora")

    def criar_material(self, status=Material.Status.PENDENTE, categoria=None, **campos):
        dados = {
            "nome_artistico": campos.pop("nome_artistico", "Lua Norte"),
            "email_contato": campos.pop("email_contato", "lua.norte@example.com"),
            "cidade": "Piraquara",
            "uf": "PR",
            "titulo": campos.pop("titulo", "Vozes do Bairro"),
            "descricao": campos.pop("descricao", "Descrição de teste."),
            "categoria": categoria or self.musica,
            "texto_alternativo": campos.pop("texto_alternativo", "Imagem de teste"),
            "link_obra": campos.pop("link_obra", "https://example.com/obra"),
            "link_canal": campos.pop("link_canal", ""),
        }
        material = services.registrar_envio(dados=dados, imagem=gerar_imagem())
        if status == Material.Status.APROVADO:
            material = services.aprovar_material(material.pk, self.editor)
        elif status == Material.Status.REJEITADO:
            material = services.rejeitar_material(material.pk, self.editor)
        return material


def criar_editor(username, com_permissao=True, **extra):
    usuario = get_user_model().objects.create_user(
        username=username, password=SENHA_FORTE, is_staff=True, **extra
    )
    if com_permissao:
        usuario.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="portal",
                codename__in=["view_material", "change_material", "avaliar_material"],
            )
        )
    return get_user_model().objects.get(pk=usuario.pk)  # limpa cache de permissões
