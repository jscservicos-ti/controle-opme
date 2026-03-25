from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('estoque.urls')), # Redireciona a raiz do site para o nosso app
]