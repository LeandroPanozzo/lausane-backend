"""Cliente HTTP contra el servicio interno de WhatsApp (Node + Baileys).

Ese servicio corre en la misma máquina (127.0.0.1, no expuesto por nginx) y
mantiene la sesión de WhatsApp vinculada desde el teléfono. Acá solo hacemos
los pedidos HTTP para consultar el estado, servir el QR y mandar presupuestos.
"""
import base64

import requests
from django.conf import settings


class WhatsAppServiceError(Exception):
    pass


def _headers():
    if settings.WHATSAPP_SERVICE_TOKEN:
        return {"X-Internal-Token": settings.WHATSAPP_SERVICE_TOKEN}
    return {}


def obtener_estado():
    try:
        resp = requests.get(f"{settings.WHATSAPP_SERVICE_URL}/estado", headers=_headers(), timeout=5)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise WhatsAppServiceError(f"No se pudo conectar con el servicio de WhatsApp: {exc}") from exc
    return resp.json()


def obtener_qr_png():
    try:
        resp = requests.get(f"{settings.WHATSAPP_SERVICE_URL}/qr.png", headers=_headers(), timeout=5)
    except requests.RequestException as exc:
        raise WhatsAppServiceError(f"No se pudo conectar con el servicio de WhatsApp: {exc}") from exc
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content


def enviar_documento(telefono, texto, archivo_bytes, nombre_archivo, mimetype="application/pdf"):
    payload = {
        "telefono": telefono,
        "texto": texto,
        "archivo_base64": base64.b64encode(archivo_bytes).decode("ascii"),
        "nombre_archivo": nombre_archivo,
        "mimetype": mimetype,
    }
    try:
        resp = requests.post(
            f"{settings.WHATSAPP_SERVICE_URL}/enviar", json=payload, headers=_headers(), timeout=30
        )
    except requests.RequestException as exc:
        raise WhatsAppServiceError(f"No se pudo conectar con el servicio de WhatsApp: {exc}") from exc

    if resp.status_code != 200:
        try:
            detalle = resp.json().get("error", resp.text)
        except ValueError:
            detalle = resp.text
        raise WhatsAppServiceError(detalle)
    return resp.json()
