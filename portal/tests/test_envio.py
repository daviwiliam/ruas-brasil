from django.urls import reverse

from portal.models import Artista, Material
from portal.views import SESSAO_ULTIMO_ENVIO

from .utils import MidiaTemporariaTestCase, dados_validos, gerar_imagem


class EnvioValidoTests(MidiaTemporariaTestCase):
    def enviar(self, **extra):
        dados = dados_validos(self.musica, **extra)
        dados["imagem"] = gerar_imagem()
        return self.client.post(reverse("portal:enviar"), dados)

    def test_envio_valido_cria_material_pendente_e_redireciona(self):
        resposta = self.enviar()
        self.assertRedirects(resposta, reverse("portal:recebido"))
        material = Material.objects.get()
        self.assertEqual(material.status, Material.Status.PENDENTE)
        self.assertIsNone(material.avaliado_em)
        self.assertIsNone(material.publicado_em)
        self.assertIsNone(material.avaliado_por)
        self.assertEqual(material.artista.nome_artistico, "Lua Norte")
        self.assertTrue(material.protocolo.startswith("RB-"))

    def test_confirmacao_mostra_protocolo_resumo_e_aviso(self):
        resposta = self.enviar()
        material = Material.objects.get()
        pagina = self.client.get(resposta["Location"])
        self.assertContains(pagina, material.protocolo)
        self.assertContains(pagina, "Aguardando avaliação")
        self.assertContains(pagina, "não significa publicação")
        self.assertContains(pagina, "Vozes do Bairro")
        self.assertContains(pagina, 'role="status"')
        self.assertNotContains(pagina, "lua.norte@example.com")

    def test_envio_nao_publica_automaticamente(self):
        self.enviar()
        material = Material.objects.get()
        self.assertNotContains(self.client.get(reverse("portal:inicio")), "Vozes do Bairro")
        self.assertEqual(self.client.get(material.get_absolute_url()).status_code, 404)

    def test_cada_envio_cria_novo_artista_mesmo_com_nome_e_email_iguais(self):
        self.enviar()
        self.enviar(titulo="Segundo trabalho")
        self.assertEqual(Artista.objects.count(), 2)

    def test_links_opcionais_podem_ficar_vazios(self):
        resposta = self.enviar(link_obra="", link_canal="")
        self.assertEqual(resposta.status_code, 302)

    def test_caracteres_de_controle_sao_removidos(self):
        self.enviar(titulo="Vozes\x1b do\x07 Bairro")
        self.assertEqual(Material.objects.get().titulo, "Vozes do Bairro")

    def test_caractere_nulo_e_recusado(self):
        resposta = self.enviar(titulo="Vozes\x00 do Bairro")
        self.assertIn("titulo", resposta.context["form"].errors)


class EnvioInvalidoTests(MidiaTemporariaTestCase):
    def enviar(self, imagem=True, **extra):
        dados = dados_validos(self.musica, **extra)
        if imagem:
            dados["imagem"] = gerar_imagem()
        return self.client.post(reverse("portal:enviar"), dados)

    def test_campos_obrigatorios_ausentes(self):
        resposta = self.client.post(reverse("portal:enviar"), {})
        self.assertEqual(resposta.status_code, 200)
        form = resposta.context["form"]
        for campo in ["nome_artistico", "email_contato", "cidade", "uf", "titulo",
                      "descricao", "categoria", "imagem", "texto_alternativo"]:
            self.assertIn(campo, form.errors, campo)
        self.assertNotIn("link_obra", form.errors)
        self.assertEqual(Material.objects.count(), 0)

    def test_campos_so_com_espacos_sao_invalidos(self):
        resposta = self.enviar(titulo="    ", descricao="\n\n")
        self.assertIn("titulo", resposta.context["form"].errors)
        self.assertIn("descricao", resposta.context["form"].errors)

    def test_email_invalido(self):
        resposta = self.enviar(email_contato="nao-e-email")
        self.assertIn("email_contato", resposta.context["form"].errors)

    def test_uf_e_categoria_invalidas(self):
        dados = dados_validos(self.musica, uf="XX")
        dados["categoria"] = 99999
        dados["imagem"] = gerar_imagem()
        resposta = self.client.post(reverse("portal:enviar"), dados)
        self.assertIn("uf", resposta.context["form"].errors)
        self.assertIn("categoria", resposta.context["form"].errors)

    def test_links_com_esquema_proibido(self):
        for link in ["javascript:alert(1)", "data:text/html,<b>x</b>", "ftp://example.com/x",
                     "file:///etc/passwd", "vbscript:msgbox(1)"]:
            with self.subTest(link=link):
                resposta = self.enviar(link_obra=link)
                self.assertIn("link_obra", resposta.context["form"].errors)
        self.assertEqual(Material.objects.count(), 0)

    def test_link_invalido_gera_uma_unica_mensagem(self):
        resposta = self.enviar(link_obra="javascript:alert(1)")
        self.assertEqual(len(resposta.context["form"].errors["link_obra"]), 1)
        resposta = self.enviar(link_obra="https://")
        self.assertEqual(len(resposta.context["form"].errors["link_obra"]), 1)

    def test_link_com_credenciais_e_invalido(self):
        resposta = self.enviar(link_canal="https://usuario:senha@example.com/")
        self.assertIn("link_canal", resposta.context["form"].errors)

    def test_link_sem_esquema_assume_https(self):
        self.enviar(link_obra="example.com/obra")
        self.assertEqual(Material.objects.get().link_obra, "https://example.com/obra")

    def test_erros_especificos_associados_aos_campos_e_resumo(self):
        resposta = self.enviar(email_contato="errado")
        self.assertContains(resposta, 'id="resumo-erros"')
        self.assertContains(resposta, 'role="alert"')
        self.assertContains(resposta, 'href="#id_email_contato"')
        self.assertContains(resposta, 'id="id_email_contato-erro"')
        self.assertContains(resposta, 'aria-invalid="true"')
        self.assertContains(resposta, "id_email_contato-erro")

    def test_campos_validos_sao_preservados_e_imagem_deve_ser_reenviada(self):
        resposta = self.enviar(email_contato="errado", titulo="Meu título preservado")
        self.assertContains(resposta, 'value="Meu título preservado"')
        self.assertContains(resposta, 'value="Piraquara"')
        self.assertContains(resposta, "Selecione a imagem novamente")

    def test_get_mostra_formulario_com_rotulos(self):
        resposta = self.client.get(reverse("portal:enviar"))
        self.assertContains(resposta, '<label for="id_nome_artistico">')
        self.assertContains(resposta, "não significa publicar")
        self.assertContains(resposta, "csrfmiddlewaretoken")


class ConfirmacaoProtegidaTests(MidiaTemporariaTestCase):
    def test_sem_envio_na_sessao_redireciona(self):
        resposta = self.client.get(reverse("portal:recebido"))
        self.assertRedirects(resposta, reverse("portal:enviar"))

    def test_outra_sessao_nao_ve_envio_alheio(self):
        dados = dados_validos(self.musica, titulo="Segredo pendente")
        dados["imagem"] = gerar_imagem()
        self.client.post(reverse("portal:enviar"), dados)

        outra = self.client_class()
        resposta = outra.get(reverse("portal:recebido"), follow=True)
        self.assertNotContains(resposta, "Segredo pendente")

    def test_identificador_na_url_e_ignorado(self):
        material = self.criar_material(titulo="Material de outra pessoa")
        for url in [f"{reverse('portal:recebido')}?id={material.pk}",
                    f"{reverse('portal:recebido')}?protocolo={material.protocolo}"]:
            resposta = self.client.get(url, follow=True)
            self.assertNotContains(resposta, "Material de outra pessoa")

    def test_sessao_aponta_apenas_para_o_proprio_envio(self):
        alheio = self.criar_material(titulo="Material alheio")
        dados = dados_validos(self.musica, titulo="Meu material")
        dados["imagem"] = gerar_imagem()
        self.client.post(reverse("portal:enviar"), dados)
        self.assertNotEqual(self.client.session[SESSAO_ULTIMO_ENVIO], alheio.pk)
        resposta = self.client.get(reverse("portal:recebido"))
        self.assertContains(resposta, "Meu material")
        self.assertNotContains(resposta, "Material alheio")
