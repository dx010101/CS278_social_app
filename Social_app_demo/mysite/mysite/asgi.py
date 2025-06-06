import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import match.routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
django.setup()

application = ProtocolTypeRouter({
    "http": get_asgi_application(),

    "websocket": AuthMiddlewareStack(
        URLRouter(
            match.routing.websocket_urlpatterns
        )
    ),
})