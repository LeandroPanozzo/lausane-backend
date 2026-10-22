"""
Backend de email que manda por la API HTTP de SendGrid (puerto 443) en vez de
SMTP (puertos 465/587). Se armó porque DigitalOcean bloquea por política los
puertos SMTP de salida en droplets nuevos para frenar spam — HTTPS normal no
tiene ese problema.

Se activa solo cuando EMAIL_BACKEND apunta acá (ver settings.py / .env). Usa
el mismo remitente ya verificado en SendGrid como "Single Sender".
"""

import base64
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


def _email_sendgrid(direccion):
    """SendGrid quiere {"email": ..., "name": ...} separados, pero Django
    guarda el remitente como un string tipo 'Nombre <email>'."""
    nombre, email = parseaddr(direccion)
    datos = {"email": email}
    if nombre:
        datos["name"] = nombre
    return datos


class SendGridBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = settings.SENDGRID_API_KEY
        if not api_key:
            if self.fail_silently:
                return 0
            raise ValueError("SENDGRID_API_KEY no está configurada.")

        enviados = 0
        for mensaje in email_messages:
            payload = self._armar_payload(mensaje)
            try:
                resp = requests.post(
                    SENDGRID_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=15,
                )
                resp.raise_for_status()
                enviados += 1
            except requests.RequestException:
                if not self.fail_silently:
                    raise
        return enviados

    def _armar_payload(self, mensaje):
        payload = {
            "personalizations": [{"to": [_email_sendgrid(destinatario) for destinatario in mensaje.to]}],
            "from": _email_sendgrid(mensaje.from_email),
            "subject": mensaje.subject,
            "content": [{"type": "text/plain", "value": mensaje.body}],
        }

        if mensaje.attachments:
            payload["attachments"] = [
                {
                    "content": base64.b64encode(contenido).decode("ascii"),
                    "filename": nombre,
                    "type": tipo or "application/octet-stream",
                    "disposition": "attachment",
                }
                for nombre, contenido, tipo in mensaje.attachments
            ]

        return payload
