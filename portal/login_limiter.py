"""Limitação de tentativas de login do painel.

Regra: 5 falhas em 15 minutos para a mesma CONTA ou o mesmo IP bloqueiam novas
tentativas dessa conta/IP por 15 minutos — inclusive com a senha correta.

Armazenamento: tabela `portal_controlelogin` no banco principal. Como o banco
é compartilhado, o limite vale para todos os processos/workers do Gunicorn e
para várias máquinas que usem o mesmo PostgreSQL. As atualizações usam
`select_for_update` dentro de transação para não perder contagens quando duas
requisições falham ao mesmo tempo.
"""
from datetime import timedelta
from ipaddress import ip_address

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import ControleLogin


def obter_ip(request) -> str:
    """IP do cliente. X-Forwarded-For só é considerado com proxies confiáveis
    configurados explicitamente (DJANGO_TRUSTED_PROXY_COUNT)."""
    remoto = request.META.get("REMOTE_ADDR", "") or "desconhecido"
    proxies = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if proxies > 0:
        cadeia = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
        # Cada proxy confiável acrescenta o IP de quem o chamou ao fim da lista.
        if len(cadeia) >= proxies:
            candidato = cadeia[-proxies]
            try:
                return str(ip_address(candidato))
            except ValueError:
                pass
    return remoto


def _chaves(username: str, ip: str) -> list[tuple[str, str]]:
    chaves = [(ControleLogin.Tipo.IP, ip[:64])]
    if username:
        chaves.append((ControleLogin.Tipo.CONTA, username.strip().lower()[:150]))
    return chaves


def esta_bloqueado(username: str, ip: str) -> bool:
    agora = timezone.now()
    for tipo, chave in _chaves(username, ip):
        if ControleLogin.objects.filter(tipo=tipo, chave=chave, bloqueado_ate__gt=agora).exists():
            return True
    return False


def _obter_para_atualizar(tipo, chave):
    try:
        with transaction.atomic():
            ControleLogin.objects.get_or_create(tipo=tipo, chave=chave)
    except IntegrityError:
        pass  # outro processo criou ao mesmo tempo
    return ControleLogin.objects.select_for_update().get(tipo=tipo, chave=chave)


def registrar_falha(username: str, ip: str) -> None:
    agora = timezone.now()
    janela = timedelta(seconds=settings.LOGIN_JANELA_SEGUNDOS)
    for tipo, chave in _chaves(username, ip):
        with transaction.atomic():
            ctrl = _obter_para_atualizar(tipo, chave)
            if ctrl.janela_inicio is None or ctrl.janela_inicio < agora - janela:
                ctrl.janela_inicio = agora
                ctrl.falhas = 0
            ctrl.falhas += 1
            if ctrl.falhas >= settings.LOGIN_MAX_FALHAS:
                ctrl.bloqueado_ate = agora + timedelta(seconds=settings.LOGIN_BLOQUEIO_SEGUNDOS)
                ctrl.falhas = 0
                ctrl.janela_inicio = None
            ctrl.save()


def registrar_sucesso(username: str) -> None:
    """Zera apenas o contador da conta; o do IP continua valendo."""
    ControleLogin.objects.filter(
        tipo=ControleLogin.Tipo.CONTA, chave=username.strip().lower()[:150]
    ).delete()
