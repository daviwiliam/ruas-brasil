import os
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from portal.models import Artista, Categoria, Material

from .utils import MidiaTemporariaTestCase, criar_editor


class RestricoesDeEstadoTests(MidiaTemporariaTestCase):
    def assertViola(self, **campos):
        material = self.criar_material()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Material.objects.filter(pk=material.pk).update(**campos)

    def test_status_desconhecido(self):
        self.assertViola(status="publicado")

    def test_pendente_nao_pode_ter_avaliacao(self):
        self.assertViola(avaliado_em=timezone.now())
        self.assertViola(avaliado_por=self.editor)
        self.assertViola(publicado_em=timezone.now())

    def test_aprovado_exige_avaliacao_publicacao_e_responsavel(self):
        agora = timezone.now()
        self.assertViola(status="aprovado")
        self.assertViola(status="aprovado", avaliado_em=agora, avaliado_por=self.editor)
        self.assertViola(status="aprovado", avaliado_em=agora, publicado_em=agora)

    def test_rejeitado_nao_pode_ter_publicacao(self):
        agora = timezone.now()
        self.assertViola(status="rejeitado", avaliado_em=agora, avaliado_por=self.editor, publicado_em=agora)
        self.assertViola(status="rejeitado", avaliado_por=self.editor)

    def test_datas_nao_podem_ser_anteriores_ao_envio(self):
        antes = timezone.now() - timedelta(days=10)
        self.assertViola(status="rejeitado", avaliado_em=antes, avaliado_por=self.editor)
        self.assertViola(status="aprovado", avaliado_em=timezone.now() + timedelta(seconds=1),
                         publicado_em=antes, avaliado_por=self.editor)

    def test_estado_coerente_e_aceito(self):
        material = self.criar_material()
        agora = timezone.now() + timedelta(seconds=1)
        Material.objects.filter(pk=material.pk).update(
            status="aprovado", avaliado_em=agora, publicado_em=agora, avaliado_por=self.editor
        )

    def test_uf_invalida_no_banco(self):
        with self.assertRaises(IntegrityError):
            Artista.objects.create(nome_artistico="X", email_contato="x@example.com", cidade="Y", uf="ZZ")


class ProtecaoDeRelacoesTests(MidiaTemporariaTestCase):
    def test_categoria_com_materiais_nao_pode_ser_excluida(self):
        self.criar_material()
        with self.assertRaises(ProtectedError):
            self.musica.delete()

    def test_artista_com_materiais_nao_pode_ser_excluido(self):
        material = self.criar_material()
        with self.assertRaises(ProtectedError):
            material.artista.delete()

    def test_avaliador_nao_pode_ser_excluido(self):
        avaliador = criar_editor("avaliador2")
        from portal import services
        services.aprovar_material(self.criar_material().pk, avaliador)
        with self.assertRaises(ProtectedError):
            avaliador.delete()

    def test_categoria_unica(self):
        with self.assertRaises(IntegrityError):
            Categoria.objects.create(nome="Música", slug="outro-slug")

    def test_protocolos_unicos_e_nao_sequenciais(self):
        a, b = self.criar_material(), self.criar_material()
        self.assertNotEqual(a.protocolo, b.protocolo)
        self.assertRegex(a.protocolo, r"^RB-[A-Z2-9]{5}-[A-Z2-9]{5}$")

    def test_excluir_material_remove_arquivos(self):
        material = self.criar_material()
        storage, nomes = material.imagem.storage, [material.imagem.name, material.miniatura.name]
        self.assertTrue(all(storage.exists(n) for n in nomes))
        material.delete()
        self.assertFalse(any(storage.exists(n) for n in nomes))

    def test_str(self):
        material = self.criar_material()
        self.assertEqual(str(material), "Vozes do Bairro — Lua Norte")
        self.assertEqual(str(material.artista), "Lua Norte (Piraquara/PR)")
        self.assertEqual(str(self.musica), "Música")


class ComandosTests(MidiaTemporariaTestCase):
    def test_carregar_categorias_idempotente(self):
        call_command("carregar_categorias", stdout=StringIO())
        call_command("carregar_categorias", stdout=StringIO())
        self.assertEqual(Categoria.objects.count(), 6)  # Música e Moda já existiam

    def test_popular_demo_cria_lua_norte_pendente_sem_criar_usuarios(self):
        usuarios_antes = get_user_model().objects.count()
        call_command("popular_demo", stdout=StringIO())
        material = Material.objects.get(titulo="Vozes do Bairro")
        self.assertEqual(material.status, Material.Status.PENDENTE)
        self.assertEqual(material.artista.nome_artistico, "Lua Norte")
        self.assertEqual(material.artista.email_contato, "lua.norte@example.com")
        self.assertTrue(material.link_obra.startswith("https://example.com/"))
        self.assertEqual(get_user_model().objects.count(), usuarios_antes)
        call_command("popular_demo", stdout=StringIO())  # idempotente
        self.assertEqual(Material.objects.filter(titulo="Vozes do Bairro").count(), 1)

    def test_popular_demo_com_aprovacao_e_quantidade(self):
        call_command("popular_demo", "--quantidade", "3", "--aprovar-como", "editora", stdout=StringIO())
        self.assertEqual(Material.objects.filter(status="aprovado").count(), 4)
        self.assertFalse(Artista.objects.exclude(email_contato__endswith="@example.com").exists())

    def test_popular_demo_exige_avaliador_valido(self):
        with self.assertRaises(CommandError):
            call_command("popular_demo", "--aprovar-como", "fantasma", stdout=StringIO())
        criar_editor("semperm", com_permissao=False)
        with self.assertRaises(CommandError):
            call_command("popular_demo", "--aprovar-como", "semperm", stdout=StringIO())

    def test_nenhum_usuario_com_senha_padrao_no_repositorio(self):
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        comandos = os.path.join(raiz, "portal", "management", "commands")
        for nome in os.listdir(comandos):
            if nome.endswith(".py"):
                with open(os.path.join(comandos, nome), encoding="utf-8") as f:
                    codigo = f.read()
                self.assertNotIn("create_superuser(", codigo, nome)
