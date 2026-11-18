"""Cria um administrador validando a força da senha.

`set_password` NÃO valida a senha; por isso chamamos `validate_password`
explicitamente (mínimo de 12 caracteres, senhas comuns, numéricas e parecidas
com os dados do usuário). A senha é pedida de forma interativa ou lida da
variável de ambiente RUAS_ADMIN_PASSWORD (útil em automação); nunca por argumento
de linha de comando, para não ficar no histórico do shell.
"""
import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

GRUPO_EDITORES = "Editores"
PERMISSOES_EDITOR = [
    "view_material", "change_material", "avaliar_material",
    "view_artista", "change_artista", "view_categoria",
]


def garantir_grupo_editores() -> Group:
    grupo, _ = Group.objects.get_or_create(name=GRUPO_EDITORES)
    grupo.permissions.set(Permission.objects.filter(content_type__app_label="portal",
                                                    codename__in=PERMISSOES_EDITOR))
    return grupo


class Command(BaseCommand):
    help = "Cria um administrador (superusuário) ou editor, validando a senha."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--email", default="")
        parser.add_argument("--editor", action="store_true",
                            help="Cria um editor (grupo Editores) em vez de superusuário.")

    def handle(self, *args, username, email, editor, **opcoes):
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            raise CommandError(f"O usuário '{username}' já existe.")

        senha = os.environ.get("RUAS_ADMIN_PASSWORD")
        if not senha:
            senha = getpass.getpass("Senha (mínimo 12 caracteres): ")
            if senha != getpass.getpass("Confirme a senha: "):
                raise CommandError("As senhas não coincidem.")

        usuario = User(username=username, email=email, is_staff=True, is_superuser=not editor)
        try:
            validate_password(senha, user=usuario)
        except ValidationError as erro:
            raise CommandError("Senha recusada: " + " ".join(erro.messages))

        with transaction.atomic():
            usuario.set_password(senha)  # PBKDF2-HMAC-SHA256 com salt
            usuario.save()
            if editor:
                usuario.groups.add(garantir_grupo_editores())

        papel = "editor" if editor else "administrador"
        self.stdout.write(self.style.SUCCESS(f"{papel.capitalize()} '{username}' criado."))
