from django.urls import path

from . import views

urlpatterns = [
    path('templates', views.list_templates),
    path('templates/upload', views.upload_template),
]
