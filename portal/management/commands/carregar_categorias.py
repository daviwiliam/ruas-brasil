from django.core.management.base import BaseCommand

from portal.models import Categoria

CATEGORIAS = [
    ("Música", "musica"),
    ("Artes visuais", "artes-visuais"),
    ("Jogos", "jogos"),
    ("Audiovisual", "audiovisual"),
    ("Literatura", "literatura"),
    ("Moda", "moda"),
]


class Command(BaseCommand):
    help = "Cria as categorias padrão do portal (idempotente)."

    def handle(self, *args, **opcoes):
        criadas = 0
        for nome, slug in CATEGORIAS:
            _, criada = Categoria.objects.get_or_create(slug=slug, defaults={"nome": nome})
            criadas += int(criada)
        self.stdout.write(self.style.SUCCESS(f"Categorias criadas: {criadas}; total: {Categoria.objects.count()}."))
