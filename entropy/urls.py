"""
URL configuration for entropy project.

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
from django.urls import include, path

from accounts import views as account_views
from forum import views as forum_views

handler404 = 'forum.views.custom_404'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('secret-panel/', account_views.secret_panel, name='secret_panel'),
    # SEO: robots.txt и динамический sitemap.xml
    path('robots.txt', forum_views.robots_txt, name='robots_txt'),
    path('sitemap.xml', forum_views.sitemap_xml, name='sitemap_xml'),
    # PWA: Service Worker (нужен в корне, чтобы scope был /)
    path('sw.js', forum_views.service_worker, name='service_worker'),
    # PWA: manifest.json
    path('manifest.json', forum_views.manifest_json, name='manifest_json'),
    path('', include('forum.urls')),
]
