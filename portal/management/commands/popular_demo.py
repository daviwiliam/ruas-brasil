"""Popula o portal com dados FICTÍCIOS de demonstração.

Não cria administrador nem senha. Por padrão os materiais ficam PENDENTES, para
que a aprovação seja feita pelo painel. Use --aprovar-como <usuário> (um
administrador já existente, criado com `criar_admin`) para publicá-los.
"""
import io
import random

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageDraw

from portal import services
from portal.models import Categoria, Material

PALETA = [(31, 61, 43), (242, 194, 48), (26, 26, 23), (196, 98, 45), (60, 110, 140), (140, 60, 90)]

DEMO_PRINCIPAL = {
    "nome_artistico": "Lua Norte",
    "email_contato": "lua.norte@example.com",
    "cidade": "Piraquara",
    "uf": "PR",
    "titulo": "Vozes do Bairro",
    "descricao": "EP independente com quatro faixas sobre encontros e histórias da cidade.",
    "categoria_slug": "musica",
    "texto_alternativo": "Capa do EP Vozes do Bairro: formas geométricas em verde e amarelo sobre fundo creme.",
    "link_obra": "https://example.com/vozes-do-bairro",
    "link_canal": "https://example.com/lua-norte",
}

NOMES = ["Coletivo Serra Viva", "Ana Grafite", "Beto Pixel", "Cia. Mananciais", "Rua Verso",
         "Maré Alta", "Tinta Fresca", "Duo Neblina", "Ateliê Araucária", "Joana Lente"]
TITULOS = ["Muros que Falam", "Cartografia Afetiva", "Noite no Terminal", "Fios da Feira",
           "Poemas de Ônibus", "Pixel e Pinhão", "Retratos da Represa", "Costura Urbana",
           "Trilha da Serra", "Ecos da Praça"]
CIDADES = ["Piraquara", "Pinhais", "São José dos Pinhais", "Quatro Barras", "Curitiba"]


def imagem_ficticia(semente: int, nome: str) -> SimpleUploadedFile:
    rnd = random.Random(semente)
    img = Image.new("RGB", (1200, 900), (245, 239, 224))
    desenho = ImageDraw.Draw(img)
    for _ in range(14):
        cor = rnd.choice(PALETA)
        x, y = rnd.randint(-200, 1100), rnd.randint(-200, 800)
        t = rnd.randint(120, 420)
        if rnd.random() < 0.5:
            desenho.rectangle([x, y, x + t, y + t // 2], fill=cor)
        else:
            desenho.ellipse([x, y, x + t, y + t], fill=cor)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return SimpleUploadedFile(nome, buffer.getvalue(), content_type="image/png")


class Command(BaseCommand):
    help = "Cria materiais fictícios de demonstração (sem administrador e sem senha)."

    def add_arguments(self, parser):
        parser.add_argument("--quantidade", type=int, default=0,
                            help="Materiais fictícios extras (ex.: 100 para testar desempenho).")
        parser.add_argument("--aprovar-como", metavar="USUARIO",
                            help="Aprova e publica os materiais criados em nome deste administrador existente.")

    def handle(self, *args, **opcoes):
        call_command("carregar_categorias", stdout=io.StringIO())
        avaliador = None
        if opcoes["aprovar_como"]:
            User = get_user_model()
            try:
                avaliador = User.objects.get(username=opcoes["aprovar_como"])
            except User.DoesNotExist:
                raise CommandError("Administrador não encontrado. Crie-o antes com `manage.py criar_admin`.")
            if not services.pode_avaliar(avaliador):
                raise CommandError("Este usuário não tem permissão para avaliar materiais.")

        categorias = {c.slug: c for c in Categoria.objects.all()}
        criados = []

        if not Material.objects.filter(titulo=DEMO_PRINCIPAL["titulo"],
                                       artista__email_contato=DEMO_PRINCIPAL["email_contato"]).exists():
            dados = {k: v for k, v in DEMO_PRINCIPAL.items() if k != "categoria_slug"}
            dados["categoria"] = categorias[DEMO_PRINCIPAL["categoria_slug"]]
            criados.append(services.registrar_envio(dados=dados, imagem=imagem_ficticia(1, "capa.png")))

        lista_categorias = list(categorias.values())
        for i in range(opcoes["quantidade"]):
            nome = NOMES[i % len(NOMES)]
            dados = {
                "nome_artistico": nome,
                "email_contato": f"artista{i + 1}@example.com",
                "cidade": CIDADES[i % len(CIDADES)],
                "uf": "PR",
                "titulo": f"{TITULOS[i % len(TITULOS)]} #{i + 1}",
                "descricao": "Trabalho fictício criado para demonstração e testes de desempenho.\n"
                             "Nenhuma pessoa real está associada a este conteúdo.",
                "categoria": lista_categorias[i % len(lista_categorias)],
                "texto_alternativo": "Composição abstrata com formas coloridas (imagem de demonstração).",
                "link_obra": f"https://example.com/obra-{i + 1}",
                "link_canal": "",
            }
            criados.append(services.registrar_envio(dados=dados, imagem=imagem_ficticia(i + 100, "demo.png")))

        if avaliador:
            for material in criados:
                services.aprovar_material(material.pk, avaliador)

        estado = "aprovados e publicados" if avaliador else "pendentes (aprove pelo painel)"
        self.stdout.write(self.style.SUCCESS(f"{len(criados)} material(is) de demonstração criados, {estado}."))
