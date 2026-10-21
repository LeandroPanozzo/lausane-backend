"""
Conexión de email configurable desde la app (Panel → cuenta de Gmail), en vez
de quedar fija en el .env. Si no se cargó ninguna cuenta en Configuración, cae
en la configuración estática de settings (EMAIL_BACKEND/EMAIL_* del .env).
"""

from django.conf import settings
from django.core.mail import get_connection

from precios.models import ConfiguracionGlobal


def obtener_conexion_email():
    config = ConfiguracionGlobal.actual()
    if config.email_remitente and config.email_password:
        return get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host="smtp.gmail.com",
            port=465,
            username=config.email_remitente,
            password=config.email_password,
            use_ssl=True,
        )
    return get_connection()


def obtener_remitente() -> str:
    config = ConfiguracionGlobal.actual()
    return config.email_remitente or settings.DEFAULT_FROM_EMAIL
