"""
URL configuration for db_metadata_crawler project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

#autenticacao sem senha
# from django.contrib.auth import views as auth_views   #original
from metadata_crawler.views import UsernameOnlyLoginView

from metadata_crawler.views import UsernameOnlyLoginView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('metadata_crawler.urls')),
    
    #esta linha tem que vir antes da seguinte, senão não funciona (ver explicação abaixo)
    path('accounts/login/', UsernameOnlyLoginView.as_view(), name='login'),
    
    # <-- this is key para o logout funcionar, é o comportamento default p/ login e logout
    # Django's default logout view, included via:
    path('accounts/', include('django.contrib.auth.urls')),  
    #...requires a POST request to log out. This is a security measure to prevent CSRF attacks (someone tricking you into logging out just by visiting a link).
    # That line registers a set of default authentication routes, including 'login'
    #   So even though you're adding (below):
    #       path('accounts/logina/', UsernameOnlyLoginView.as_view(), name='login'),
    #   ...your browser still goes to /accounts/login/, and it is being handled by the default Django auth view — not your custom one.
    #   To make Django use your custom login view, you need to override the /accounts/login/ route yourself, before the built-in ones are included.
    #   And move it above the line that includes the default auth URLs:
    #   Django resolves routes in order. If it finds a match, it stops looking. 
    #   So your custom route must be above include('django.contrib.auth.urls').
    # path('accounts/logina/', UsernameOnlyLoginView.as_view(), name='login'),     # <<==movi para cima, aí funcionou
    #   Ou então, altere isso no settings.py:
    #   LOGIN_URL = '/logina/'  # Tells Django to redirect here if login is required
    # path('accounts/login/', auth_views.LoginView.as_view(template_name='metadata_crawler/login.html'), name='login'),
    # path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/', http_method_names=['get', 'post']), name='logout'),
 
]

