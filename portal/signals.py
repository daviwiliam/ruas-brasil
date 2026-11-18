from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Material


@receiver(post_delete, sender=Material)
def remover_arquivos(sender, instance, **kwargs):
    """Apaga os arquivos privados quando o material é excluído."""
    for campo in (instance.imagem, instance.miniatura):
        if campo and campo.name:
            campo.storage.delete(campo.name)
