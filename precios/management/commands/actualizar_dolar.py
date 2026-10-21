"""
Actualiza la cotización del dólar consultando la API externa.

Pensado para correr en un cron / Celery beat cada X minutos, ej:
    */10 * * * * cd /ruta/proyecto && python manage.py actualizar_dolar

También podés forzar la actualización manualmente:
    python manage.py actualizar_dolar
"""
from django.core.management.base import BaseCommand

from precios.services.cotizacion_dolar import CotizacionDolarError, actualizar_cotizacion


class Command(BaseCommand):
    help = "Consulta la API de cotización del dólar y guarda un registro nuevo."

    def handle(self, *args, **options):
        try:
            cot = actualizar_cotizacion()
        except CotizacionDolarError as exc:
            self.stderr.write(self.style.ERROR(f"No se pudo actualizar: {exc}"))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Cotización actualizada: compra ${cot.compra} / venta ${cot.venta} ({cot.fecha:%Y-%m-%d %H:%M})"
        ))
