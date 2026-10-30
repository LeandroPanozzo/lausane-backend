from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from precios.models import Cliente, LongitudChapa, Presupuesto, PresupuestoItem
from precios.services.pdf_presupuesto import generar_pdf_presupuesto
from precios.services.excel_presupuesto import generar_excel_presupuesto


class LongitudChapaAPITests(APITestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="u1", password="x", is_staff=True)
        self.client.force_authenticate(self.usuario)

    def test_seed_longitudes_cargadas_por_migracion(self):
        self.assertEqual(LongitudChapa.objects.filter(ancho_mm="1220").count(), 2)
        self.assertEqual(LongitudChapa.objects.filter(ancho_mm="1000").count(), 1)

    def test_listar_filtra_por_ancho(self):
        resp = self.client.get("/api/longitudes-chapa/", {"ancho_mm": "1220"})
        self.assertEqual(resp.status_code, 200)
        valores = sorted(r["longitud_mm"] for r in resp.data["results"])
        self.assertEqual(valores, [2440, 3000])

    def test_listar_sin_filtro_trae_todas(self):
        resp = self.client.get("/api/longitudes-chapa/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["count"], 8)

    def test_crear_longitud_nueva(self):
        resp = self.client.post("/api/longitudes-chapa/", {"ancho_mm": "1220", "longitud_mm": 3600})
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(LongitudChapa.objects.filter(ancho_mm="1220", longitud_mm=3600).exists())

    def test_crear_longitud_duplicada_falla(self):
        resp = self.client.post("/api/longitudes-chapa/", {"ancho_mm": "1220", "longitud_mm": 2440})
        self.assertEqual(resp.status_code, 400)

    def test_eliminar_longitud(self):
        l = LongitudChapa.objects.create(ancho_mm="999", longitud_mm=1111)
        resp = self.client.delete(f"/api/longitudes-chapa/{l.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(LongitudChapa.objects.filter(id=l.id).exists())


class LongitudEnItemPresupuestoTests(APITestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="u2", password="x", is_staff=True)
        self.client.force_authenticate(self.usuario)
        self.cliente = Cliente.objects.create(
            numero=9012, nombre="Cliente Longitud", incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )

    def test_crear_presupuesto_con_longitud(self):
        payload = {
            "cliente": self.cliente.id,
            "cotizacion_dolar": "1000",
            "items": [{
                "tipo": "CHAPA", "descripcion": "Chapa Laminado en Frío · espesor 12 · ancho 1220mm",
                "cantidad": "10", "unidad": "kg", "precio_unitario_pesos": "1000", "longitud_mm": 2440,
            }],
        }
        resp = self.client.post("/api/presupuestos/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["items"][0]["longitud_mm"], 2440)

    def test_item_sin_longitud_devuelve_null(self):
        payload = {
            "cliente": self.cliente.id,
            "cotizacion_dolar": "1000",
            "items": [{
                "tipo": "TUBO", "descripcion": "Tubo 30x60",
                "cantidad": "2", "unidad": "unidad", "precio_unitario_pesos": "1000",
            }],
        }
        resp = self.client.post("/api/presupuestos/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.data["items"][0]["longitud_mm"])

    def test_pdf_y_excel_con_longitud_no_explotan(self):
        presupuesto = Presupuesto.objects.create(
            cliente=self.cliente, cotizacion_dolar=Decimal("1000"), impuesto_pct=Decimal("21"),
        )
        PresupuestoItem.objects.create(
            presupuesto=presupuesto, tipo=PresupuestoItem.TIPO_CHAPA,
            descripcion="Chapa Laminado en Frío · espesor 12 · ancho 1220mm",
            cantidad=Decimal("10"), precio_unitario_pesos=Decimal("1000"), longitud_mm=2440,
        )
        PresupuestoItem.objects.create(
            presupuesto=presupuesto, tipo=PresupuestoItem.TIPO_TUBO,
            descripcion="Tubo 30x60", cantidad=Decimal("2"), precio_unitario_pesos=Decimal("500"),
        )
        pdf_bytes = generar_pdf_presupuesto(presupuesto)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        excel_bytes = generar_excel_presupuesto(presupuesto)
        self.assertTrue(len(excel_bytes) > 0)
