from decimal import Decimal

from rest_framework.test import APITestCase

from precios.models import Cliente, Presupuesto, PresupuestoItem
from precios.services.pdf_presupuesto import generar_pdf_presupuesto
from precios.services.excel_presupuesto import generar_excel_presupuesto


class DescuentoOcultoEnPdfYExcelTests(APITestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            numero=9007, nombre="Cliente Tubo Desc", incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )
        self.presupuesto = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"))
        PresupuestoItem.objects.create(
            presupuesto=self.presupuesto, tipo=PresupuestoItem.TIPO_TUBO,
            descripcion="Tubo 30 60 2 (desc. 2%)", cantidad=Decimal("2"), unidad="unidad",
            precio_unitario_pesos=Decimal("36581.77"),
        )

    def test_pdf_no_explota_y_es_valido(self):
        pdf_bytes = generar_pdf_presupuesto(self.presupuesto)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_excel_no_explota(self):
        excel_bytes = generar_excel_presupuesto(self.presupuesto)
        self.assertTrue(len(excel_bytes) > 0)
