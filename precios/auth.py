"""
Clase de autenticación JWT vía cookie httpOnly (ver `precios.auth_views` para
las vistas de login/refresh/logout que las escriben).

Antes el frontend guardaba access/refresh en localStorage y los mandaba en el
header Authorization. Un XSS en el frontend podía leer esos tokens con JS y
robar la sesión. Ahora el login deja los tokens en cookies httpOnly (no
accesibles desde JS).

Este módulo se referencia por string desde REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES,
así que se mantiene deliberadamente sin importar `rest_framework.views` (eso
dispara la carga de `rest_framework.schemas`, que a su vez evalúa esa misma
setting y produce un import circular si ambas cosas viven en el mismo módulo).
"""

from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    """Igual que JWTAuthentication, pero si no vino el header Authorization
    busca el access token en la cookie httpOnly. Soporta ambos caminos para
    no romper clientes que sí mandan el header (ej. pruebas con curl/Postman)."""

    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            return super().authenticate(request)

        raw_token = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
