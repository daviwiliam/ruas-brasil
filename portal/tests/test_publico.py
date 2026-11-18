from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from portal.models import Material

from .utils import MidiaTemporariaTestCase, criar_editor


class ListagemTests(MidiaTemporariaTestCase):
    def test_inicio_lista_apenas_aprovados(self):
        self.criar_material(Material.Status.APROVADO, titulo="Publicado A")
        self.criar_material(Material.Status.PENDENTE, titulo="Pendente B")
        self.criar_material(Material.Status.REJEITADO, titulo="Rejeitado C")
        resposta = self.client.get(reverse("portal:inicio"))
        self.assertContains(resposta, "Publicado A")
        self.assertNotContains(resposta, "Pendente B")
        self.assertNotContains(resposta, "Rejeitado C")
        self.assertContains(resposta, "Envie seu trabalho")

    def test_ordenacao_por_data_de_publicacao_e_paginacao(self):
        criados = [self.criar_material(Material.Status.APROVADO, titulo=f"Item {i:02d}") for i in range(12)]
        base = timezone.now() + timedelta(days=1)
        # Publicação em ordem inversa à de criação, para provar que a ordem vem de publicado_em.
        for i, m in enumerate(criados):
            Material.objects.filter(pk=m.pk).update(publicado_em=base + timedelta(minutes=i))
        pagina1 = self.client.get(reverse("portal:inicio"))
        itens = list(pagina1.context["pagina"].object_list)
        self.assertEqual(len(itens), 10)
        self.assertEqual(itens[0].titulo, "Item 11")
        self.assertEqual(itens[-1].titulo, "Item 02")
        pagina2 = self.client.get(reverse("portal:inicio") + "?pagina=2")
        self.assertEqual([m.titulo for m in pagina2.context["pagina"].object_list], ["Item 01", "Item 00"])
        self.assertContains(pagina1, "Página 1 de 2")

    def test_pagina_invalida_nao_quebra(self):
        for valor in ["abc", "-1", "9999"]:
            self.assertEqual(self.client.get(reverse("portal:inicio") + f"?pagina={valor}").status_code, 200)

    def test_inicio_sem_consultas_n_mais_1(self):
        for i in range(3):
            self.criar_material(Material.Status.APROVADO, titulo=f"A{i}")
        with self.assertNumQueries(4) as ctx:  # noqa: F841
            self.client.get(reverse("portal:inicio"))
        for i in range(10):
            self.criar_material(Material.Status.APROVADO, titulo=f"B{i}")
        with self.assertNumQueries(4):
            self.client.get(reverse("portal:inicio"))

    def test_filtro_por_categoria(self):
        self.criar_material(Material.Status.APROVADO, titulo="Som da Serra", categoria=self.musica)
        self.criar_material(Material.Status.APROVADO, titulo="Costura Urbana", categoria=self.moda)
        self.criar_material(Material.Status.PENDENTE, titulo="Moda pendente", categoria=self.moda)
        resposta = self.client.get(reverse("portal:categoria", args=["moda"]))
        self.assertContains(resposta, "Costura Urbana")
        self.assertNotContains(resposta, "Som da Serra")
        self.assertNotContains(resposta, "Moda pendente")
        self.assertContains(resposta, 'aria-current="page"')

    def test_categoria_inexistente_404(self):
        self.assertEqual(self.client.get(reverse("portal:categoria", args=["nao-existe"])).status_code, 404)


class MateriaTests(MidiaTemporariaTestCase):
    def test_materia_aprovada_exibe_dados(self):
        m = self.criar_material(Material.Status.APROVADO, link_canal="https://example.com/canal")
        resposta = self.client.get(m.get_absolute_url())
        self.assertContains(resposta, "<h1>Vozes do Bairro</h1>", html=True)
        self.assertContains(resposta, "Lua Norte")
        self.assertContains(resposta, "Música")
        self.assertContains(resposta, "Descrição de teste.")
        self.assertContains(resposta, reverse("portal:imagem", args=[m.pk, "imagem"]))
        self.assertContains(resposta, 'alt="Imagem de teste"')
        self.assertContains(resposta, reverse("portal:sair", args=[m.pk, "obra"]))
        self.assertContains(resposta, reverse("portal:sair", args=[m.pk, "canal"]))

    def test_pendente_e_rejeitado_nao_acessiveis_por_url_direta(self):
        for status in [Material.Status.PENDENTE, Material.Status.REJEITADO]:
            with self.subTest(status=status):
                m = self.criar_material(status)
                self.assertEqual(self.client.get(m.get_absolute_url()).status_code, 404)
                self.assertEqual(self.client.get(reverse("portal:sair", args=[m.pk, "obra"])).status_code, 404)

    def test_material_despublicado_some(self):
        m = self.criar_material(Material.Status.APROVADO)
        from portal import services
        services.rejeitar_material(m.pk, self.editor)
        self.assertEqual(self.client.get(m.get_absolute_url()).status_code, 404)

    def test_pagina_404_amigavel_sem_detalhes(self):
        resposta = self.client.get("/materia/999999/")
        self.assertEqual(resposta.status_code, 404)
        self.assertContains(resposta, "Página não encontrada", status_code=404)
        self.assertNotContains(resposta, "Traceback", status_code=404)


class ImagensProtegidasTests(MidiaTemporariaTestCase):
    def url(self, m, variante="imagem"):
        return reverse("portal:imagem", args=[m.pk, variante])

    def test_imagem_aprovada_e_servida(self):
        m = self.criar_material(Material.Status.APROVADO)
        for variante in ["imagem", "miniatura"]:
            resposta = self.client.get(self.url(m, variante))
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta["Content-Type"], "image/webp")
            self.assertEqual(resposta["X-Content-Type-Options"], "nosniff")
            b"".join(resposta.streaming_content)

    def test_imagens_pendentes_e_rejeitadas_bloqueadas(self):
        for status in [Material.Status.PENDENTE, Material.Status.REJEITADO]:
            m = self.criar_material(status)
            for variante in ["imagem", "miniatura"]:
                with self.subTest(status=status, variante=variante):
                    self.assertEqual(self.client.get(self.url(m, variante)).status_code, 404)

    def test_staff_sem_permissao_de_visualizar_nao_ve_pendente(self):
        m = self.criar_material()
        self.client.force_login(criar_editor("curioso", com_permissao=False))
        self.assertEqual(self.client.get(self.url(m)).status_code, 404)

    def test_editor_ve_imagem_pendente_sem_cache_publico(self):
        m = self.criar_material()
        self.client.force_login(self.editor)
        resposta = self.client.get(self.url(m, "miniatura"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("no-store", resposta["Cache-Control"])
        b"".join(resposta.streaming_content)

    def test_uploads_nao_tem_rota_publica(self):
        m = self.criar_material(Material.Status.PENDENTE)
        for caminho in [f"/media/{m.imagem.name}", f"/private_media/{m.imagem.name}",
                        f"/nao-servido/{m.imagem.name}", f"/static/{m.imagem.name}"]:
            self.assertEqual(self.client.get(caminho).status_code, 404, caminho)

    def test_variante_desconhecida_e_id_inexistente(self):
        m = self.criar_material(Material.Status.APROVADO)
        self.assertEqual(self.client.get(self.url(m, "original")).status_code, 404)
        self.assertEqual(self.client.get(reverse("portal:imagem", args=[999999, "imagem"])).status_code, 404)


class BuscaTests(MidiaTemporariaTestCase):
    def setUp(self):
        self.criar_material(Material.Status.APROVADO, titulo="Vozes do Bairro", nome_artistico="Lua Norte")
        self.criar_material(Material.Status.APROVADO, titulo="Muros que Falam", nome_artistico="Ana Grafite")
        self.criar_material(Material.Status.PENDENTE, titulo="Vozes Secretas", nome_artistico="Oculto")
        self.criar_material(Material.Status.REJEITADO, titulo="Vozes Rejeitadas", nome_artistico="Lua Rejeitada")

    def buscar(self, termo):
        return self.client.get(reverse("portal:busca"), {"q": termo})

    def titulos(self, resposta):
        return {m.titulo for m in resposta.context["pagina"].object_list}

    def test_busca_por_titulo_sem_diferenciar_maiusculas(self):
        for termo in ["vozes", "VOZES", "VoZeS do bAIRRO"]:
            self.assertEqual(self.titulos(self.buscar(termo)), {"Vozes do Bairro"})

    def test_busca_por_nome_artistico(self):
        self.assertEqual(self.titulos(self.buscar("ana grafite")), {"Muros que Falam"})
        self.assertEqual(self.titulos(self.buscar("LUA")), {"Vozes do Bairro"})

    def test_busca_nao_retorna_pendentes_nem_rejeitados(self):
        resposta = self.buscar("Secretas")
        self.assertEqual(self.titulos(resposta), set())
        self.assertContains(resposta, "0 resultados")
        self.assertNotContains(self.buscar("Rejeitad"), "Vozes Rejeitadas")

    def test_busca_vazia_e_termos_especiais(self):
        self.assertIsNone(self.buscar("").context["pagina"])
        for termo in ["%", "_", "' OR 1=1 --", "\\"]:
            self.assertEqual(self.buscar(termo).status_code, 200)
        self.assertEqual(self.titulos(self.buscar("%")), set())


class PrivacidadeEEscapeTests(MidiaTemporariaTestCase):
    def test_email_nunca_aparece_no_portal(self):
        m = self.criar_material(Material.Status.APROVADO, email_contato="segredo.artista@example.com")
        for url in [reverse("portal:inicio"), m.get_absolute_url(), reverse("portal:busca") + "?q=Vozes",
                    reverse("portal:categoria", args=["musica"])]:
            resposta = self.client.get(url)
            self.assertNotContains(resposta, "segredo.artista")

    def test_conteudo_malicioso_e_escapado(self):
        m = self.criar_material(
            Material.Status.APROVADO,
            titulo='<script>alert("t")</script>',
            nome_artistico="<img src=x onerror=alert(1)>",
            descricao='<b>negrito</b>\n<a href="javascript:alert(2)">clique</a>',
            texto_alternativo='" onload="alert(3)',
        )
        for url in [m.get_absolute_url(), reverse("portal:inicio"), reverse("portal:busca") + "?q=script"]:
            resposta = self.client.get(url)
            conteudo = resposta.content.decode()
            self.assertNotIn('<script>alert("t")</script>', conteudo)
            self.assertNotIn("<img src=x onerror", conteudo)
            self.assertNotIn('onload="alert(3)', conteudo)
            self.assertIn("&lt;script&gt;", conteudo)
        materia = self.client.get(m.get_absolute_url()).content.decode()
        self.assertNotIn("<b>negrito</b>", materia)
        self.assertNotIn('href="javascript:', materia)
        self.assertIn("&lt;b&gt;negrito&lt;/b&gt;", materia)

    def test_termo_de_busca_e_escapado(self):
        resposta = self.client.get(reverse("portal:busca"), {"q": "<svg onload=alert(1)>"})
        self.assertNotContains(resposta, "<svg onload")
        self.assertContains(resposta, "&lt;svg onload=alert(1)&gt;")


class ContadoresTests(MidiaTemporariaTestCase):
    def test_visualizacoes_cliques_e_ranking(self):
        a = self.criar_material(Material.Status.APROVADO, titulo="Mais vista")
        b = self.criar_material(Material.Status.APROVADO, titulo="Menos vista")
        for _ in range(3):
            self.client.get(a.get_absolute_url())
        self.client.get(b.get_absolute_url())
        resposta = self.client.get(reverse("portal:sair", args=[a.pk, "obra"]))
        self.assertRedirects(resposta, "https://example.com/obra", fetch_redirect_response=False)
        a.refresh_from_db()
        self.assertEqual((a.visualizacoes, a.cliques), (3, 1))
        ranking = list(self.client.get(reverse("portal:inicio")).context["ranking"])
        self.assertEqual([m.titulo for m in ranking], ["Mais vista", "Menos vista"])

    def test_link_ausente_ou_tipo_invalido_404(self):
        m = self.criar_material(Material.Status.APROVADO, link_canal="")
        self.assertEqual(self.client.get(reverse("portal:sair", args=[m.pk, "canal"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("portal:sair", args=[m.pk, "outro"])).status_code, 404)

    def test_pendente_nao_conta(self):
        m = self.criar_material()
        self.client.get(m.get_absolute_url())
        m.refresh_from_db()
        self.assertEqual(m.visualizacoes, 0)
