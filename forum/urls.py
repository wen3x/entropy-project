from django.urls import path

from . import views

app_name = "forum"

urlpatterns = [
    path("", views.post_list, name="post_list"),
    path("graveyard/", views.graveyard_list, name="graveyard_list"),
    path("posts/new/", views.post_create, name="post_create"),
    path("p/<slug:slug>/", views.post_detail, name="post_detail"),
    path("p/<slug:slug>/delete/", views.post_delete, name="post_delete"),
    path("p/<slug:slug>/resurrect/", views.post_resurrect, name="post_resurrect"),
    path("p/<slug:slug>/destroy/", views.post_destroy, name="post_destroy"),
    path("p/<slug:slug>/like/", views.toggle_like_post, name="toggle_like_post"),
    path("p/<slug:slug>/pin/", views.toggle_pin_post, name="toggle_pin_post"),
    path("comment/<int:pk>/like/", views.toggle_like_comment, name="toggle_like_comment"),
    path("comment/<int:pk>/approve/", views.approve_comment, name="approve_comment"),
]
