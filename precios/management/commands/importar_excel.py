"""
Importa clientes, config global, markups de espesor y tubos desde el Excel
original.

Uso:
    python manage.py importar_excel /ruta/al/LISTA_UNIFICADA_dic.xlsx
    python manage.py importar_excel archivo.xlsx --hoja-cliente 1
"""
from django.core.management.base import BaseCommand, CommandError

from precios.services.importar_excel import importar_workbook


class Command(BaseCommand):
    help = "Importa el Excel de lista de precios (clientes, config, markups, tubos)."

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str, help="Ruta al archivo .xlsx")
        parser.add_argument(
            "--hoja-cliente", type=str, default="1",
            help="Nombre de la hoja de cliente usada como referencia para los markups de espesor (default: '1')",
        )

    def handle(self, *args, **options):
        ruta = options["archivo"]
        hoja = options["hoja_cliente"]
        try:
            with open(ruta, "rb") as f:
                resultado = importar_workbook(f, hoja_cliente_referencia=hoja)
        except FileNotFoundError as exc:
            raise CommandError(f"No se encontró el archivo: {ruta}") from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Importación completa:"))
        for k, v in resultado.as_dict().items():
            self.stdout.write(f"  {k}: {v}")
