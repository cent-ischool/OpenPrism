from django.urls import path

from .consumers import CollabConsumer

websocket_urlpatterns = [path('api/collab', CollabConsumer.as_asgi())]
