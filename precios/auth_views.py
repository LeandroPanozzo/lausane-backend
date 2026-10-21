"""Vistas de login/refresh/logout que escriben los tokens JWT como cookies
httpOnly en vez de devolverlos en el body. Ver `precios.auth` para la clase
de autenticación que las lee de vuelta."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import EmailMessage
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from precios.serializers import ConfirmarResetPasswordSerializer, SolicitarResetPasswordSerializer
from precios.services.email_config import obtener_conexion_email, obtener_remitente


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


class SolicitarResetPasswordView(APIView):
    """POST /api/auth/password-reset/ — manda (si existe y tiene email
    cargado) un link para elegir una contraseña nueva. Siempre responde lo
    mismo, exista o no el usuario, para no revelar qué usuarios existen."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "password_reset"

    MENSAJE = "Si el usuario existe y tiene un email cargado, le enviamos un correo con instrucciones."

    def post(self, request):
        serializer = SolicitarResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        User = get_user_model()
        try:
            user = User.objects.get(username=serializer.validated_data["username"])
        except User.DoesNotExist:
            return Response({"detail": self.MENSAJE})

        if user.email:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}"
            email = EmailMessage(
                subject="Recuperar contraseña — Lausane S.A.C.",
                body=(
                    f"Hola {user.username},\n\n"
                    f"Pediste recuperar tu contraseña. Entrá a este link para elegir una nueva "
                    f"(válido por un tiempo limitado):\n\n{link}\n\n"
                    f"Si no fuiste vos, podés ignorar este mensaje."
                ),
                from_email=obtener_remitente(),
                to=[user.email],
                connection=obtener_conexion_email(),
            )
            email.send(fail_silently=False)

        return Response({"detail": self.MENSAJE})


class ConfirmarResetPasswordView(APIView):
    """POST /api/auth/password-reset/confirmar/ — toma el uid/token del link
    del mail y la contraseña nueva, y la aplica si el token es válido."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = ConfirmarResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        User = get_user_model()
        try:
            pk = urlsafe_base64_decode(datos["uid"]).decode()
            user = User.objects.get(pk=pk)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return Response({"detail": "El link no es válido o ya expiró."}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, datos["token"]):
            return Response({"detail": "El link no es válido o ya expiró."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(datos["password"], user)
        except DjangoValidationError as exc:
            return Response({"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(datos["password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Contraseña actualizada."})


class LogoutView(APIView):
    """POST /api/auth/logout/ — borra las cookies de sesión."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        response = Response({"detail": "Sesión cerrada."}, status=status.HTTP_200_OK)
        response.delete_cookie(settings.AUTH_COOKIE_ACCESS, path="/")
        response.delete_cookie(settings.AUTH_COOKIE_REFRESH, path="/")
        return response
