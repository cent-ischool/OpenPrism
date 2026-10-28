from django.urls import path

from . import views

urlpatterns = [
    path('projects/<uuid:pk>/collab/invite', views.create_invite),
    path('collab/resolve', views.resolve),
    path('projects/<uuid:pk>/collab/flush', views.flush),
    path('projects/<uuid:pk>/collab/status', views.status),
]
