from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("categoria/<slug:slug>/", views.categoria, name="categoria"),
    path("busca/", views.busca, name="busca"),
    path("materia/<int:pk>/", views.materia, name="materia"),
    path("materia/<int:pk>/link/<str:tipo>/", views.sair_para_link, name="sair"),
    path("enviar/", views.enviar, name="enviar"),
    path("enviar/recebido/", views.recebido, name="recebido"),
    path("imagens/<int:pk>/<str:variante>/", views.imagem, name="imagem"),
]
