from .models import Categoria


def navegacao(request):
    if request.path.startswith("/painel/"):
        return {}
    return {"categorias_menu": Categoria.objects.all()}
