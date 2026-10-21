"""
Cotización del dólar en tiempo real.

Reemplaza la celda INICIO!J8 ("Dólar Definido"), que en el Excel estaba
hardcodeada (1498) y se completaba a mano mirando bna.com.ar.

Fuente por defecto: dolarapi.com (agrega la cotización oficial que publica el
BNA). Se puede cambiar la URL en settings.DOLAR_API_URL / variable de entorno
DOLAR_API_URL sin tocar código.
"""

import logging
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

from precios.models import ConfiguracionGlobal, CotizacionDolar

logger = logging.getLogger(__name__)


class CotizacionDolarError(Exception):
    """La API externa no respondió o devolvió datos inválidos."""


def _fetch_desde_api() -> CotizacionDolar:
    resp = requests.get(settings.DOLAR_API_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    try:
        compra = Decimal(str(data["compra"]))
        venta = Decimal(str(data["venta"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise CotizacionDolarError(f"Respuesta inesperada de la API de dólar: {data}") from exc

    return CotizacionDolar.objects.create(
        compra=compra,
        venta=venta,
        fuente=CotizacionDolar.FUENTE_OFICIAL,
    )


def _ultima_oficial() -> CotizacionDolar | None:
    return CotizacionDolar.objects.filter(fuente=CotizacionDolar.FUENTE_OFICIAL).order_by("-fecha").first()


def _ultima_manual() -> CotizacionDolar | None:
    return CotizacionDolar.objects.filter(fuente=CotizacionDolar.FUENTE_MANUAL).order_by("-fecha").first()


def actualizar_cotizacion() -> CotizacionDolar:
    """Fuerza una consulta a la API externa y guarda un registro nuevo."""
    return _fetch_desde_api()


def obtener_cotizacion_oficial_referencia(forzar_actualizacion: bool = False) -> CotizacionDolar:
    """
    Cotización oficial online, cacheada por DOLAR_CACHE_MINUTOS — se usa tanto
    para los cálculos en modo automático como para mostrar de referencia
    cuando el sistema está forzado a modo manual.

    Si la API externa falla y hay una cotización oficial previa, se devuelve
    esa (mejor un valor un poco viejo que romper todos los cálculos de precios).
    """
    ultima = _ultima_oficial()
    cache_vencido = (
        ultima is None
        or (timezone.now() - ultima.fecha).total_seconds() > settings.DOLAR_CACHE_MINUTOS * 60
    )

    if forzar_actualizacion or cache_vencido:
        try:
            return _fetch_desde_api()
        except (requests.RequestException, CotizacionDolarError) as exc:
            logger.warning("No se pudo actualizar la cotización del dólar: %s", exc)
            if ultima is not None:
                return ultima
            raise CotizacionDolarError(
                "No hay cotización cacheada y la API externa no respondió."
            ) from exc

    return ultima


def obtener_cotizacion_actual(forzar_actualizacion: bool = False) -> CotizacionDolar:
    """
    Devuelve la cotización que hay que usar para calcular precios:

    - En modo manual (ConfiguracionGlobal.dolar_modo == MANUAL), siempre
      devuelve la última cotización cargada a mano, sin importar su
      antigüedad — es un valor forzado, no un caché que vence solo.
      `forzar_actualizacion` no rompe este pin (para eso está
      `volver_a_cotizacion_oficial`); solo se ignora si por algún motivo
      quedó en modo manual sin ninguna fila manual cargada.
    - En modo automático, se comporta como antes: cachea la cotización
      oficial online por DOLAR_CACHE_MINUTOS y la re-consulta si venció el
      caché, no hay ninguna, o se pide forzar_actualizacion=True.
    """
    config = ConfiguracionGlobal.actual()

    if config.dolar_modo == ConfiguracionGlobal.DOLAR_MODO_MANUAL:
        manual = _ultima_manual()
        if manual is not None:
            return manual
        config.dolar_modo = ConfiguracionGlobal.DOLAR_MODO_AUTOMATICO
        config.save(update_fields=["dolar_modo"])

    return obtener_cotizacion_oficial_referencia(forzar_actualizacion=forzar_actualizacion)


def fijar_cotizacion_manual(compra: Decimal, venta: Decimal) -> CotizacionDolar:
    """Carga una cotización a mano y fuerza al sistema a usarla en vez de la
    oficial online, hasta que se cargue otra o se llame a
    `volver_a_cotizacion_oficial`."""
    cot = CotizacionDolar.objects.create(compra=compra, venta=venta, fuente=CotizacionDolar.FUENTE_MANUAL)
    config = ConfiguracionGlobal.actual()
    config.dolar_modo = ConfiguracionGlobal.DOLAR_MODO_MANUAL
    config.save(update_fields=["dolar_modo"])
    return cot


def volver_a_cotizacion_oficial() -> CotizacionDolar:
    """Saca el pin manual y vuelve a modo automático, trayendo una cotización
    online fresca de una."""
    config = ConfiguracionGlobal.actual()
    config.dolar_modo = ConfiguracionGlobal.DOLAR_MODO_AUTOMATICO
    config.save(update_fields=["dolar_modo"])
    return obtener_cotizacion_oficial_referencia(forzar_actualizacion=True)
