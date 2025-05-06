from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/match/$", consumers.MatchConsumer.as_asgi()),
    re_path(r"ws/nearby/$", consumers.NearbyConsumer.as_asgi()),
]
