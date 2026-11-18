import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from portal.models import Material

from .utils import MidiaTemporariaTestCase, dados_validos, gerar_imagem


class ValidacaoImagemTests(MidiaTemporariaTestCase):
    def enviar_com(self, arquivo):
        dados = dados_validos(self.musica)
        dados["imagem"] = arquivo
        return self.client.post(reverse("portal:enviar"), dados)

    def assertImagemRecusada(self, arquivo, trecho):
        resposta = self.enviar_com(arquivo)
        self.assertEqual(resposta.status_code, 200)
        erros = " ".join(resposta.context["form"].errors.get("imagem", []))
        self.assertIn(trecho, erros)
        self.assertEqual(Material.objects.count(), 0)

    def test_arquivo_de_texto_com_extensao_jpg(self):
        falso = SimpleUploadedFile("foto.jpg", b"isto nao e uma imagem" * 50, content_type="image/jpeg")
        self.assertImagemRecusada(falso, "não é uma imagem válida")

    def test_html_disfarcado_de_png(self):
        falso = SimpleUploadedFile("x.png", b"<html><script>alert(1)</script></html>", content_type="image/png")
        self.assertImagemRecusada(falso, "não é uma imagem válida")

    def test_formatos_proibidos_mesmo_com_extensao_permitida(self):
        for formato in ["GIF", "BMP", "TIFF"]:
            with self.subTest(formato=formato):
                arquivo = gerar_imagem(formato, nome="disfarce.jpg")
                arquivo.content_type = "image/jpeg"
                self.assertImagemRecusada(arquivo, "Formato não aceito")

    def test_imagem_truncada(self):
        original = gerar_imagem("PNG", (300, 300)).read()
        truncada = SimpleUploadedFile("t.png", original[: len(original) // 2], content_type="image/png")
        resposta = self.enviar_com(truncada)
        self.assertIn("imagem", resposta.context["form"].errors)

    def test_arquivo_maior_que_5_mb(self):
        grande = SimpleUploadedFile("g.png", b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024), content_type="image/png")
        self.assertImagemRecusada(grande, "O limite é 5 MB")

    def test_dimensoes_excessivas(self):
        for tamanho in [(4097, 10), (10, 4097), (5000, 5000)]:
            with self.subTest(tamanho=tamanho):
                arquivo = gerar_imagem("PNG", tamanho, modo="L", cor=0)
                self.assertImagemRecusada(arquivo, "O máximo é 4096 × 4096")

    def test_limite_exato_de_4096_e_aceito(self):
        arquivo = gerar_imagem("PNG", (4096, 64), modo="L", cor=0)
        resposta = self.enviar_com(arquivo)
        self.assertEqual(resposta.status_code, 302)

    @override_settings(IMAGEM_MAX_BYTES=1000)
    def test_limite_de_tamanho_vem_da_configuracao(self):
        self.assertImagemRecusada(gerar_imagem("PNG", (400, 400), cor=(1, 2, 3)), "O limite é 5 MB")

    def test_formatos_aceitos(self):
        for formato in ["JPEG", "PNG", "WEBP"]:
            with self.subTest(formato=formato):
                resposta = self.enviar_com(gerar_imagem(formato))
                self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Material.objects.count(), 3)


class ProcessamentoImagemTests(MidiaTemporariaTestCase):
    def test_metadados_exif_sao_removidos_e_formato_reencodado(self):
        img = Image.new("RGB", (2400, 1200), (200, 100, 50))
        exif = Image.Exif()
        exif[0x010F] = "CameraSecreta"   # Make
        exif[0x8825] = {2: (25.0, 26.0, 0.0)}  # GPSInfo
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", exif=exif.tobytes())
        self.assertIn(b"CameraSecreta", buffer.getvalue())

        dados = dados_validos(self.musica)
        dados["imagem"] = SimpleUploadedFile("foto.jpg", buffer.getvalue(), content_type="image/jpeg")
        self.client.post(reverse("portal:enviar"), dados)
        material = Material.objects.get()

        with material.imagem.open("rb") as f:
            conteudo = f.read()
        self.assertNotIn(b"CameraSecreta", conteudo)
        with Image.open(io.BytesIO(conteudo)) as salva:
            self.assertEqual(salva.format, "WEBP")
            self.assertEqual(len(salva.getexif()), 0)
            self.assertLessEqual(max(salva.size), 1600)
            self.assertEqual(salva.size, (1600, 800))
        self.assertEqual((material.imagem_largura, material.imagem_altura), (1600, 800))

    def test_miniatura_tem_tamanho_fixo(self):
        material = self.criar_material()
        with Image.open(material.miniatura.open("rb")) as mini:
            self.assertEqual(mini.size, (640, 480))
            self.assertEqual(mini.format, "WEBP")
        material.miniatura.close()

    def test_nome_original_do_arquivo_nao_e_usado(self):
        dados = dados_validos(self.musica)
        dados["imagem"] = gerar_imagem(nome="../../etc/passwd.png")
        self.client.post(reverse("portal:enviar"), dados)
        material = Material.objects.get()
        self.assertNotIn("passwd", material.imagem.name)
        self.assertTrue(material.imagem.name.startswith("materiais/"))
        self.assertTrue(material.imagem.name.endswith(".webp"))

    def test_png_com_transparencia_e_paleta(self):
        for modo, cor in [("RGBA", (10, 20, 30, 0)), ("P", 3), ("LA", (5, 100))]:
            with self.subTest(modo=modo):
                dados = dados_validos(self.musica, titulo=f"Modo {modo}")
                dados["imagem"] = gerar_imagem("PNG", (300, 200), modo=modo, cor=cor)
                resposta = self.client.post(reverse("portal:enviar"), dados)
                self.assertEqual(resposta.status_code, 302)
