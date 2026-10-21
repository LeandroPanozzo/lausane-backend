"""Vistas de login/refresh/logout que escriben los tokens JWT como cookies
httpOnly en vez de devolverlos en el body. Ver `precios.auth` para la clase
de autenticación que las lee de vuelta."""

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


def _set_auth_cookies(response, access=None, refresh=None):
    if access is not None:
        response.set_cookie(
            settings.AUTH_COOKIE_ACCESS, access,
            httponly=True, secure=settings.AUTH_COOKIE_SECURE, samesite=settings.AUTH_COOKIE_SAMESITE,
            max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()), path="/",
        )
    if refresh is not None:
        response.set_cookie(
            settings.AUTH_COOKIE_REFRESH, refresh,
            httponly=True, secure=settings.AUTH_COOKIE_SECURE, samesite=settings.AUTH_COOKIE_SAMESITE,
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()), path="/",
        )


class CookieTokenObtainPairView(TokenObtainPairView):
    """POST /api/auth/token/ — login estándar de simplejwt, pero en vez de
    devolver access/refresh en el body los deja en cookies httpOnly."""

    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            access = response.data.pop("access", None)
            refresh = response.data.pop("refresh", None)
            _set_auth_cookies(response, access, refresh)
            response.data = {"username": request.data.get("username", "")}
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """POST /api/auth/token/refresh/ — lee el refresh token de la cookie (no
    del body) y devuelve el access nuevo (+ refresh rotado) en cookies."""

    def post(self, request, *args, **kwargs):
        refresh = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if not refresh:
            return Response({"detail": "No hay sesión activa."}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = self.get_serializer(data={"refresh": refresh})
        serializer.is_valid(raise_exception=True)

        response = Response(dict(serializer.validated_data), status=status.HTTP_200_OK)
        access = response.data.pop("access", None)
        refresh_nuevo = response.data.pop("refresh", None)
        _set_auth_cookies(response, access, refresh_nuevo)
        response.data = {"detail": "Token renovado."}
        return response


class LogoutView(APIView):
    """POST /api/auth/logout/ — borra las cookies de sesión."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        response = Response({"detail": "Sesión cerrada."}, status=status.HTTP_200_OK)
        response.delete_cookie(settings.AUTH_COOKIE_ACCESS, path="/")
        response.delete_cookie(settings.AUTH_COOKIE_REFRESH, path="/")
        return response
