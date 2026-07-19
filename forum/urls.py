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
    # Nodes
    path("nodes/", views.node_list, name="node_list"),
    path("nodes/create/", views.create_node, name="create_node"),
    path("n/<slug:node_slug>/", views.node_detail, name="node_detail"),
    path("n/<slug:node_slug>/edit/", views.edit_node, name="edit_node"),
    path("n/<slug:node_slug>/subscribe/", views.toggle_node_subscription, name="toggle_node_subscription"),
    path("n/<slug:node_slug>/new/", views.post_create, name="post_create_in_node"),
    path("n/<slug:node_slug>/<slug:post_slug>/", views.post_detail_in_node, name="post_detail_in_node"),
    # PWA: Offline page
    path("offline/", views.offline_page, name="offline"),
    # Infinite scroll JSON endpoint
    path("posts/more/", views.post_list_json, name="post_list_more"),
    # Search
    path("search/", views.search_view, name="search"),
    path("debug/", views.debug_view, name="debug"),
    # Comments
    path("comment/<int:pk>/like/", views.toggle_like_comment, name="toggle_like_comment"),
    path("comment/<int:pk>/approve/", views.approve_comment, name="approve_comment"),
    path("comment/<int:pk>/delete/", views.delete_comment, name="delete_comment"),
    path("comment/<int:pk>/edit/", views.edit_comment, name="edit_comment"),
]
