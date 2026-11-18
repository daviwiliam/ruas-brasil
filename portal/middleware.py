"""Content-Security-Policy sem scripts inline.

Django 5.2 não tem CSP nativo; este middleware aplica uma política estrita ao
portal público. O painel (Django Admin) usa atributos `style` inline em alguns
templates, por isso recebe `style-src 'unsafe-inline'` — scripts continuam
restritos a arquivos do próprio domínio.
"""

BASE = {
    "default-src": "'self'",
    "script-src": "'self'",
    "style-src": "'self'",
    "img-src": "'self' data:",
    "font-src": "'self'",
    "connect-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "frame-ancestors": "'none'",
}


def _politica(admin: bool) -> str:
    diretivas = dict(BASE)
    if admin:
        diretivas["style-src"] = "'self' 'unsafe-inline'"
    return "; ".join(f"{k} {v}" for k, v in diretivas.items())


POLITICA_PUBLICA = _politica(False)
POLITICA_ADMIN = _politica(True)


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if "Content-Security-Policy" not in response:
            admin = request.path.startswith("/painel/")
            response["Content-Security-Policy"] = POLITICA_ADMIN if admin else POLITICA_PUBLICA
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
