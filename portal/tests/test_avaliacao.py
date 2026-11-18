from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from portal import services
from portal.models import Material

from .utils import SENHA_FORTE, MidiaTemporariaTestCase, criar_editor


class ServicoAvaliacaoTests(MidiaTemporariaTestCase):
    def test_aprovar_registra_responsavel_e_datas(self):
        material = self.criar_material()
        aprovado = services.aprovar_material(material.pk, self.editor)
        self.assertEqual(aprovado.status, Material.Status.APROVADO)
        self.assertEqual(aprovado.avaliado_por, self.editor)
        self.assertIsNotNone(aprovado.avaliado_em)
        self.assertEqual(aprovado.publicado_em, aprovado.avaliado_em)
        self.assertGreaterEqual(aprovado.avaliado_em, aprovado.enviado_em)

    def test_rejeitar_registra_responsavel_e_nao_publica(self):
        material = self.criar_material()
        rejeitado = services.rejeitar_material(material.pk, self.editor)
        self.assertEqual(rejeitado.status, Material.Status.REJEITADO)
        self.assertEqual(rejeitado.avaliado_por, self.editor)
        self.assertIsNotNone(rejeitado.avaliado_em)
        self.assertIsNone(rejeitado.publicado_em)

    def test_rejeitar_material_aprovado_remove_publicacao(self):
        material = self.criar_material(Material.Status.APROVADO)
        rejeitado = services.rejeitar_material(material.pk, self.editor)
        self.assertIsNone(rejeitado.publicado_em)

    def test_transicoes_repetidas_sao_invalidas(self):
        material = self.criar_material(Material.Status.APROVADO)
        with self.assertRaises(services.TransicaoInvalida):
            services.aprovar_material(material.pk, self.editor)
        services.rejeitar_material(material.pk, self.editor)
        with self.assertRaises(services.TransicaoInvalida):
            services.rejeitar_material(material.pk, self.editor)

    def test_sem_permissao_o_servico_recusa(self):
        material = self.criar_material()
        sem_perm = criar_editor("semperm", com_permissao=False)
        inativo = criar_editor("inativo", is_active=False)
        comum = get_user_model().objects.create_user("comum", password=SENHA_FORTE)
        for usuario in [sem_perm, inativo, comum, AnonymousUser(), None]:
            with self.subTest(usuario=usuario):
                with self.assertRaises(PermissionDenied):
                    services.aprovar_material(material.pk, usuario)
                with self.assertRaises(PermissionDenied):
                    services.rejeitar_material(material.pk, usuario)
        material.refresh_from_db()
        self.assertEqual(material.status, Material.Status.PENDENTE)


class PainelAvaliacaoTests(MidiaTemporariaTestCase):
    def setUp(self):
        self.material = self.criar_material()
        self.url_aprovar = reverse("admin:portal_material_aprovar", args=[self.material.pk])
        self.url_rejeitar = reverse("admin:portal_material_rejeitar", args=[self.material.pk])
        self.url_editar = reverse("admin:portal_material_change", args=[self.material.pk])

    def status(self):
        self.material.refresh_from_db()
        return self.material.status

    def test_editor_aprova_por_post(self):
        self.client.force_login(self.editor)
        resposta = self.client.post(self.url_aprovar)
        self.assertRedirects(resposta, self.url_editar)
        self.assertEqual(self.status(), Material.Status.APROVADO)
        self.assertEqual(self.material.avaliado_por, self.editor)
        self.assertContains(self.client.get(reverse("portal:inicio")), "Vozes do Bairro")

    def test_editor_rejeita_por_post(self):
        self.client.force_login(self.editor)
        self.client.post(self.url_rejeitar)
        self.assertEqual(self.status(), Material.Status.REJEITADO)

    def test_get_nao_altera_estado(self):
        self.client.force_login(self.editor)
        for url in [self.url_aprovar, self.url_rejeitar]:
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 405)
        self.assertEqual(self.status(), Material.Status.PENDENTE)

    def test_post_sem_csrf_e_recusado(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.editor)
        resposta = cliente.post(self.url_aprovar)
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(self.status(), Material.Status.PENDENTE)

    def test_staff_sem_permissao_recebe_403(self):
        self.client.force_login(criar_editor("visitante", com_permissao=False))
        for url in [self.url_aprovar, self.url_rejeitar]:
            self.assertEqual(self.client.post(url).status_code, 403)
        self.assertEqual(self.status(), Material.Status.PENDENTE)

    def test_staff_que_so_edita_nao_pode_avaliar(self):
        from django.contrib.auth.models import Permission

        editor_texto = criar_editor("revisor", com_permissao=False)
        editor_texto.user_permissions.add(*Permission.objects.filter(
            codename__in=["view_material", "change_material"]))
        self.client.force_login(get_user_model().objects.get(pk=editor_texto.pk))
        self.assertEqual(self.client.post(self.url_aprovar).status_code, 403)
        pagina = self.client.get(self.url_editar)
        self.assertEqual(pagina.status_code, 200)
        self.assertNotContains(pagina, "Aprovar e publicar</button>")

    def test_anonimo_e_enviado_ao_login(self):
        resposta = self.client.post(self.url_aprovar)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("admin:login"), resposta["Location"])
        self.assertEqual(self.status(), Material.Status.PENDENTE)

    def test_usuario_nao_staff_nao_acessa(self):
        comum = get_user_model().objects.create_user("comum", password=SENHA_FORTE)
        self.client.force_login(comum)
        self.client.post(self.url_aprovar)
        self.assertEqual(self.status(), Material.Status.PENDENTE)

    def test_editar_apresentacao_nao_aprova(self):
        self.client.force_login(self.editor)
        pagina = self.client.get(self.url_editar)
        self.assertContains(pagina, "Aprovar e publicar")
        self.assertContains(pagina, 'method="post"')
        dados = {
            "titulo": "Título revisado",
            "descricao": "Descrição revisada pela equipe.",
            "categoria": self.moda.pk,
            "artista": self.material.artista.pk,
            "texto_alternativo": "Alt revisado",
            "link_obra": "https://example.com/novo",
            "link_canal": "",
            # Tentativas de forçar estado pelo formulário devem ser ignoradas:
            "status": "aprovado",
            "publicado_em": "2026-01-01 10:00",
        }
        resposta = self.client.post(self.url_editar, dados)
        self.assertEqual(resposta.status_code, 302)
        self.material.refresh_from_db()
        self.assertEqual(self.material.titulo, "Título revisado")
        self.assertEqual(self.material.categoria, self.moda)
        self.assertEqual(self.material.status, Material.Status.PENDENTE)
        self.assertIsNone(self.material.publicado_em)

    def test_edicao_no_painel_valida_links(self):
        self.client.force_login(self.editor)
        resposta = self.client.post(self.url_editar, {
            "titulo": "X", "descricao": "Y", "categoria": self.musica.pk,
            "artista": self.material.artista.pk, "texto_alternativo": "Z",
            "link_obra": "javascript:alert(1)", "link_canal": "",
        })
        self.assertEqual(resposta.status_code, 200)
        self.material.refresh_from_db()
        self.assertEqual(self.material.link_obra, "https://example.com/obra")

    def test_painel_nao_permite_criar_material(self):
        self.client.force_login(get_user_model().objects.create_superuser("root", password=SENHA_FORTE))
        self.assertEqual(self.client.get(reverse("admin:portal_material_add")).status_code, 403)

    def test_acao_em_lote_aprova_e_respeita_permissao(self):
        outro = self.criar_material(titulo="Outro")
        changelist = reverse("admin:portal_material_changelist")
        dados = {"action": "aprovar_selecionados", "_selected_action": [self.material.pk, outro.pk]}

        self.client.force_login(criar_editor("semperm2", com_permissao=False))
        self.client.post(changelist, dados)
        self.assertEqual(Material.objects.filter(status="aprovado").count(), 0)

        self.client.force_login(self.editor)
        self.client.post(changelist, dados)
        self.assertEqual(Material.objects.filter(status="aprovado").count(), 2)

    def test_lista_do_painel_mostra_status_com_texto_e_simbolo(self):
        self.client.force_login(self.editor)
        resposta = self.client.get(reverse("admin:portal_material_changelist"))
        self.assertContains(resposta, "rb-status--pendente")
        self.assertContains(resposta, "◷</span> Pendente")
