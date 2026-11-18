from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "RUAS BRASIL · Painel editorial"
admin.site.site_title = "Ruas Brasil"
admin.site.index_title = "Avaliação de materiais"

urlpatterns = [
    path("painel/", admin.site.urls),
    path("", include("portal.urls")),
]

handler404 = "portal.views.erro_404"
handler500 = "portal.views.erro_500"
