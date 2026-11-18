import os
import subprocess
import sys
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management import CommandError, call_command
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from portal import login_limiter
from portal.models import ControleLogin

from .utils import SENHA_FORTE

LOGIN = reverse("admin:login")


class LoginEVLogoutTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            "editora", password=SENHA_FORTE, is_staff=True
        )

    def logar(self, senha=SENHA_FORTE, usuario="editora", cliente=None, **extra):
        return (cliente or self.client).post(
            LOGIN, {"username": usuario, "password": senha, "next": "/painel/"}, **extra
        )

    def test_login_valido(self):
        resposta = self.logar()
        self.assertRedirects(resposta, "/painel/")

    def test_senha_armazenada_com_pbkdf2_sha256(self):
        self.admin.refresh_from_db()
        algoritmo, iteracoes, salt, _ = self.admin.password.split("$")
        self.assertEqual(algoritmo, "pbkdf2_sha256")
        self.assertGreaterEqual(int(iteracoes), 600_000)
        self.assertGreaterEqual(len(salt), 16)
        self.assertNotIn(SENHA_FORTE, self.admin.password)

    def test_logout_por_post_invalida_sessao(self):
        self.logar()
        chave = self.client.session.session_key
        self.assertTrue(Session.objects.filter(session_key=chave).exists())
        resposta = self.client.post(reverse("admin:logout"))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Session.objects.filter(session_key=chave).exists())
        self.assertEqual(self.client.get("/painel/").status_code, 302)

    def test_logout_por_get_nao_e_permitido(self):
        self.logar()
        self.assertEqual(self.client.get(reverse("admin:logout")).status_code, 405)
        self.assertEqual(self.client.get("/painel/").status_code, 200)

    def test_logout_exige_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        self.assertEqual(cliente.post(reverse("admin:logout")).status_code, 403)

    def test_cinco_falhas_bloqueiam_a_conta_mesmo_com_senha_correta(self):
        for _ in range(5):
            resposta = self.logar("senha-errada-123")
            self.assertEqual(resposta.status_code, 200)
        resposta = self.logar()
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Muitas tentativas")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_bloqueio_por_conta_vale_para_outro_ip(self):
        for _ in range(5):
            self.logar("errada", REMOTE_ADDR="10.0.0.1")
        resposta = self.logar(REMOTE_ADDR="10.0.0.2")
        self.assertContains(resposta, "Muitas tentativas")

    def test_bloqueio_por_ip_vale_para_outras_contas(self):
        for i in range(5):
            self.logar("errada", usuario=f"inexistente{i}", REMOTE_ADDR="10.0.0.9")
        resposta = self.logar(REMOTE_ADDR="10.0.0.9")
        self.assertContains(resposta, "Muitas tentativas")
        self.assertRedirects(self.logar(REMOTE_ADDR="10.0.0.10", cliente=Client()), "/painel/")

    def test_quatro_falhas_nao_bloqueiam_e_sucesso_zera_conta(self):
        for _ in range(4):
            self.logar("errada", REMOTE_ADDR="10.1.1.1")
        self.assertRedirects(self.logar(REMOTE_ADDR="10.1.1.2"), "/painel/")
        self.assertFalse(ControleLogin.objects.filter(tipo="conta", chave="editora").exists())

    def test_bloqueio_expira_apos_15_minutos(self):
        for _ in range(5):
            self.logar("errada")
        futuro = timezone.now() + timedelta(minutes=15, seconds=1)
        with mock.patch("portal.login_limiter.timezone.now", return_value=futuro):
            resposta = self.logar(cliente=Client())
        self.assertRedirects(resposta, "/painel/")

    def test_falhas_antigas_fora_da_janela_nao_somam(self):
        inicio = timezone.now()
        with mock.patch("portal.login_limiter.timezone.now", return_value=inicio):
            for _ in range(4):
                self.logar("errada")
        depois = inicio + timedelta(minutes=16)
        with mock.patch("portal.login_limiter.timezone.now", return_value=depois):
            self.logar("errada")
            self.assertRedirects(self.logar(cliente=Client()), "/painel/")

    def test_usuario_normalizado_nao_burla_limite(self):
        for variante in ["editora", "EDITORA", " Editora", "editorA", "EdItOrA"]:
            self.logar("errada", usuario=variante)
        self.assertContains(self.logar(), "Muitas tentativas")


class IpClienteTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_x_forwarded_for_ignorado_sem_proxy_configurado(self):
        req = self.rf.get("/", REMOTE_ADDR="203.0.113.5", HTTP_X_FORWARDED_FOR="1.2.3.4")
        self.assertEqual(login_limiter.obter_ip(req), "203.0.113.5")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_com_um_proxy_confiavel_usa_ultimo_ip_da_cadeia(self):
        req = self.rf.get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="6.6.6.6, 198.51.100.7")
        self.assertEqual(login_limiter.obter_ip(req), "198.51.100.7")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_valor_forjado_invalido_cai_no_remote_addr(self):
        req = self.rf.get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="nao-e-ip")
        self.assertEqual(login_limiter.obter_ip(req), "127.0.0.1")


class ConfiguracaoSegurancaTests(TestCase):
    def test_sessao_expira_apos_30_min_de_inatividade(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")

    def test_validadores_de_senha(self):
        nomes = [v["NAME"].rsplit(".", 1)[1] for v in settings.AUTH_PASSWORD_VALIDATORS]
        self.assertEqual(set(nomes), {"UserAttributeSimilarityValidator", "MinimumLengthValidator",
                                      "CommonPasswordValidator", "NumericPasswordValidator"})
        self.assertEqual(settings.PASSWORD_HASHERS[0], "django.contrib.auth.hashers.PBKDF2PasswordHasher")

    def test_cabecalhos_de_seguranca(self):
        resposta = self.client.get(reverse("portal:inicio"))
        csp = resposta["Content-Security-Policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(resposta["X-Frame-Options"], "DENY")
        self.assertEqual(resposta["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("<script>", resposta.content.decode())

    def test_producao_exige_segredo_e_hosts(self):
        base = Path(settings.BASE_DIR)
        env = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
        env.update({"DJANGO_SETTINGS_MODULE": "config.settings", "DJANGO_DEBUG": "False"})
        codigo = "import django; django.setup()"
        # .env local não deve mascarar o teste: força variáveis vazias.
        env["DJANGO_SECRET_KEY"] = ""
        r = subprocess.run([sys.executable, "-c", codigo], cwd=base, env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", r.stderr)

        env["DJANGO_SECRET_KEY"] = "x" * 60
        env["DJANGO_ALLOWED_HOSTS"] = ""
        r = subprocess.run([sys.executable, "-c", codigo], cwd=base, env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DJANGO_ALLOWED_HOSTS", r.stderr)

        env["DJANGO_ALLOWED_HOSTS"] = "ruasbrasil.example.org"
        codigo_ok = codigo + "; from django.conf import settings as s; " \
            "print(s.DEBUG, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT)"
        r = subprocess.run([sys.executable, "-c", codigo_ok], cwd=base, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "False True True True")


class CriarAdminTests(TestCase):
    def criar(self, senha, *args):
        with mock.patch.dict(os.environ, {"RUAS_ADMIN_PASSWORD": senha}):
            call_command("criar_admin", *args, stdout=StringIO())

    def test_recusa_senhas_fracas(self):
        casos = ["Curta-1!", "123456789012345", "password1234", "mariana.silva2026"]
        for senha in casos:
            with self.subTest(senha=senha):
                with self.assertRaises(CommandError):
                    self.criar(senha, "mariana.silva2026", "--email", "mariana@example.com")
        self.assertFalse(get_user_model().objects.exists())

    def test_cria_superusuario_com_senha_forte(self):
        self.criar(SENHA_FORTE, "chefe")
        usuario = get_user_model().objects.get(username="chefe")
        self.assertTrue(usuario.is_superuser and usuario.is_staff)
        self.assertTrue(usuario.password.startswith("pbkdf2_sha256$"))

    def test_cria_editor_com_permissao_de_avaliar(self):
        self.criar(SENHA_FORTE, "revisora", "--editor")
        usuario = get_user_model().objects.get(username="revisora")
        self.assertFalse(usuario.is_superuser)
        self.assertTrue(usuario.has_perm("portal.avaliar_material"))
        self.assertTrue(usuario.has_perm("portal.change_material"))
        self.assertFalse(usuario.has_perm("portal.delete_material"))

    def test_usuario_duplicado(self):
        self.criar(SENHA_FORTE, "chefe")
        with self.assertRaises(CommandError):
            self.criar(SENHA_FORTE, "chefe")
