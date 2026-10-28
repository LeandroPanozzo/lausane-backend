from decimal import Decimal

from rest_framework.test import APITestCase

from precios.models import Cliente, Presupuesto, PresupuestoItem
from precios.services.pdf_presupuesto import (
    _sin_sufijo_descuento, _con_nombres_actuales, generar_pdf_presupuesto,
)
from precios.services.excel_presupuesto import generar_excel_presupuesto


class SinSufijoDescuentoTests(APITestCase):
    def test_quita_el_sufijo(self):
        self.assertEqual(_sin_sufijo_descuento("Tubo 30 60 2 (desc. 2%)"), "Tubo 30 60 2")

    def test_quita_el_sufijo_con_decimales(self):
        self.assertEqual(_sin_sufijo_descuento("Tubo 30 60 2 (desc. 10,5%)"), "Tubo 30 60 2")

    def test_sin_sufijo_no_cambia_nada(self):
        texto = "Chapa Laminado en Frío · espesor 23 · ancho 20000mm"
        self.assertEqual(_sin_sufijo_descuento(texto), texto)


class ConNombresActualesTests(APITestCase):
    def test_chapa_dd_vieja_se_renombra(self):
        self.assertEqual(
            _con_nombres_actuales("Chapa DD · espesor 23 · ancho 20000mm"),
            "Chapa Laminado en Frío · espesor 23 · ancho 20000mm",
        )

    def test_chapa_negra_vieja_se_renombra(self):
        self.assertEqual(
            _con_nombres_actuales("Chapa Negra · espesor 10 · ancho 1000mm"),
            "Chapa Laminado en Caliente · espesor 10 · ancho 1000mm",
        )

    def test_descripcion_ya_actualizada_no_cambia(self):
        texto = "Chapa Laminado en Frío · espesor 23 · ancho 20000mm"
        self.assertEqual(_con_nombres_actuales(texto), texto)

    def test_no_toca_descripciones_sin_relacion(self):
        texto = "Tubo 30 60 2"
        self.assertEqual(_con_nombres_actuales(texto), texto)


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
