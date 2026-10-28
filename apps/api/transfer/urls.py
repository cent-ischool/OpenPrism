from django.urls import path

from . import views

urlpatterns = [
    path('transfer/start', views.start),
    path('transfer/start-mineru', views.start_mineru),
    path('transfer/step', views.step),
    path('transfer/submit-images', views.submit_images),
    path('transfer/status/<str:job_id>', views.status),
    path('transfer/upload-pdf', views.upload_pdf),
]
