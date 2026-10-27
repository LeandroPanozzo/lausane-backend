from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from precios.models import Cliente, Presupuesto, PresupuestoItem
from precios.services.pdf_presupuesto import generar_pdf_presupuesto


class ImpuestoPresupuestoAPITests(APITestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="u1", password="x", is_staff=True)
        self.client.force_authenticate(self.usuario)

        self.cliente = Cliente.objects.create(
            numero=9002, nombre="Cliente Impuesto", email="cliente@test.com", telefono="5491137860195",
            incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )
        self.presupuesto = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"))
        PresupuestoItem.objects.create(
            presupuesto=self.presupuesto,
            tipo=PresupuestoItem.TIPO_OTRO,
            descripcion="Item de prueba",
            cantidad=Decimal("1"),
            precio_unitario_pesos=Decimal("1000"),
        )

    def test_pdf_sin_elegir_impuesto_devuelve_400(self):
        resp = self.client.get(f"/api/presupuestos/{self.presupuesto.id}/pdf/")
        self.assertEqual(resp.status_code, 400)

    def test_excel_no_necesita_elegir_impuesto(self):
        resp = self.client.get(f"/api/presupuestos/{self.presupuesto.id}/excel/")
        self.assertEqual(resp.status_code, 200)

    def test_enviar_email_sin_elegir_impuesto_devuelve_400(self):
        resp = self.client.post(
            f"/api/presupuestos/{self.presupuesto.id}/enviar-email/",
            {"destinatario": "cliente@test.com"},
        )
        self.assertEqual(resp.status_code, 400)

    @patch("precios.views.whatsapp_service.enviar_documento")
    def test_enviar_whatsapp_sin_elegir_impuesto_devuelve_400(self, mock_enviar):
        resp = self.client.post(f"/api/presupuestos/{self.presupuesto.id}/enviar-whatsapp/")
        self.assertEqual(resp.status_code, 400)
        mock_enviar.assert_not_called()

    def test_elegir_impuesto_valido(self):
        resp = self.client.post(
            f"/api/presupuestos/{self.presupuesto.id}/elegir-impuesto/", {"impuesto_pct": "10.5"}
        )
        self.assertEqual(resp.status_code, 200)
        self.presupuesto.refresh_from_db()
        self.assertEqual(self.presupuesto.impuesto_pct, Decimal("10.5"))

    def test_elegir_impuesto_invalido_rechazado(self):
        resp = self.client.post(
            f"/api/presupuestos/{self.presupuesto.id}/elegir-impuesto/", {"impuesto_pct": "15"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_pdf_funciona_despues_de_elegir_impuesto(self):
        self.client.post(f"/api/presupuestos/{self.presupuesto.id}/elegir-impuesto/", {"impuesto_pct": "21"})
        resp = self.client.get(f"/api/presupuestos/{self.presupuesto.id}/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")


class PdfTextoImpuestoTests(APITestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            numero=9003, nombre="Cliente PDF", incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )
        self.presupuesto = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"))
        PresupuestoItem.objects.create(
            presupuesto=self.presupuesto, tipo=PresupuestoItem.TIPO_OTRO, descripcion="Item",
            cantidad=Decimal("1"), precio_unitario_pesos=Decimal("1000"),
        )

    def _texto_pdf(self):
        pdf_bytes = generar_pdf_presupuesto(self.presupuesto)
        # Extracción simple: reportlab comprime los streams, así que buscamos
        # en el PDF crudo no es confiable — en cambio inspeccionamos que no
        # tire error y devolvemos los bytes para un chequeo de tamaño/validez.
        return pdf_bytes

    def test_genera_pdf_sin_impuesto_elegido_sin_explotar(self):
        pdf_bytes = self._texto_pdf()
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_genera_pdf_con_10_5_sin_explotar(self):
        self.presupuesto.impuesto_pct = Decimal("10.5")
        self.presupuesto.save(update_fields=["impuesto_pct"])
        pdf_bytes = self._texto_pdf()
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_genera_pdf_con_21_sin_explotar(self):
        self.presupuesto.impuesto_pct = Decimal("21")
        self.presupuesto.save(update_fields=["impuesto_pct"])
        pdf_bytes = self._texto_pdf()
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
