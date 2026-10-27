from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from precios.models import Cliente, Presupuesto, PresupuestoItem, PresupuestoItemExtra
from precios.services.pdf_presupuesto import generar_pdf_presupuesto
from precios.services.excel_presupuesto import generar_excel_presupuesto


class ExtrasModeloTests(APITestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            numero=9004, nombre="Cliente Extras", incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )
        self.presupuesto = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"))
        self.item = PresupuestoItem.objects.create(
            presupuesto=self.presupuesto, tipo=PresupuestoItem.TIPO_OTRO, descripcion="Tubo 30x60",
            cantidad=Decimal("2"), precio_unitario_pesos=Decimal("1000"),
        )

    def test_subtotal_sin_extras(self):
        self.assertEqual(self.item.subtotal_pesos, Decimal("2000.00"))

    def test_subtotal_con_un_extra(self):
        PresupuestoItemExtra.objects.create(item=self.item, descripcion="Flete", precio_pesos=Decimal("500"))
        self.assertEqual(self.item.subtotal_pesos, Decimal("2500.00"))

    def test_subtotal_con_varios_extras(self):
        PresupuestoItemExtra.objects.create(item=self.item, descripcion="Flete", precio_pesos=Decimal("500"))
        PresupuestoItemExtra.objects.create(item=self.item, descripcion="Corte especial", precio_pesos=Decimal("300"))
        self.assertEqual(self.item.subtotal_pesos, Decimal("2800.00"))

    def test_total_presupuesto_incluye_extras(self):
        PresupuestoItemExtra.objects.create(item=self.item, descripcion="Flete", precio_pesos=Decimal("500"))
        self.assertEqual(self.presupuesto.total_pesos, Decimal("2500.00"))


class ExtrasAPITests(APITestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="u1", password="x", is_staff=True)
        self.client.force_authenticate(self.usuario)

        self.cliente = Cliente.objects.create(
            numero=9005, nombre="Cliente Extras API", incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )
        self.presupuesto = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"))
        self.item = PresupuestoItem.objects.create(
            presupuesto=self.presupuesto, tipo=PresupuestoItem.TIPO_OTRO, descripcion="Tubo 30x60",
            cantidad=Decimal("2"), precio_unitario_pesos=Decimal("1000"),
        )

    def test_agregar_extra_ok(self):
        resp = self.client.post(
            f"/api/presupuestos/{self.presupuesto.id}/items/{self.item.id}/agregar-extra/",
            {"descripcion": "Flete especial", "precio_pesos": "800"},
        )
        self.assertEqual(resp.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.extras.count(), 1)
        self.assertEqual(self.item.subtotal_pesos, Decimal("2800.00"))
        extra_devuelto = resp.data["items"][0]["extras"][0]
        self.assertEqual(extra_devuelto["descripcion"], "Flete especial")

    def test_agregar_extra_sin_descripcion_falla(self):
        resp = self.client.post(
            f"/api/presupuestos/{self.presupuesto.id}/items/{self.item.id}/agregar-extra/",
            {"precio_pesos": "800"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_agregar_extra_a_item_de_otro_presupuesto_404(self):
        otro_presupuesto = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"))
        resp = self.client.post(
            f"/api/presupuestos/{otro_presupuesto.id}/items/{self.item.id}/agregar-extra/",
            {"descripcion": "Flete", "precio_pesos": "800"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_quitar_extra_ok(self):
        extra = PresupuestoItemExtra.objects.create(item=self.item, descripcion="Flete", precio_pesos=Decimal("500"))
        resp = self.client.delete(
            f"/api/presupuestos/{self.presupuesto.id}/items/{self.item.id}/extras/{extra.id}/"
        )
        self.assertEqual(resp.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.extras.count(), 0)
        self.assertEqual(self.item.subtotal_pesos, Decimal("2000.00"))


class ExtrasEnDocumentosTests(APITestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            numero=9006, nombre="Cliente Doc Extras", incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )
        self.presupuesto = Presupuesto.objects.create(
            cliente=self.cliente, cotizacion_dolar=Decimal("1000"), impuesto_pct=Decimal("21"),
        )
        self.item = PresupuestoItem.objects.create(
            presupuesto=self.presupuesto, tipo=PresupuestoItem.TIPO_OTRO, descripcion="Tubo 30x60",
            cantidad=Decimal("2"), precio_unitario_pesos=Decimal("1000"),
        )
        PresupuestoItemExtra.objects.create(item=self.item, descripcion="Flete especial", precio_pesos=Decimal("800"))

    def test_pdf_con_extra_no_explota(self):
        pdf_bytes = generar_pdf_presupuesto(self.presupuesto)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_excel_con_extra_no_explota(self):
        excel_bytes = generar_excel_presupuesto(self.presupuesto)
        self.assertTrue(len(excel_bytes) > 0)
