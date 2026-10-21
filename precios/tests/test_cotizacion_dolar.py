from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from precios.models import Cliente, ConfiguracionGlobal, CotizacionDolar, Tubo
from precios.services import cotizacion_dolar


def _mock_response(compra="1000", venta="1020"):
    resp = mock.Mock()
    resp.raise_for_status = mock.Mock()
    resp.json.return_value = {"compra": compra, "venta": venta}
    return resp


class ObtenerCotizacionActualTests(TestCase):
    """El modo manual fuerza el valor cargado a mano en vez de la oficial
    online, sin vencer solo — antes la carga manual era apenas un respaldo
    que se pisaba solo a los DOLAR_CACHE_MINUTOS."""

    @mock.patch("precios.services.cotizacion_dolar.requests.get")
    def test_modo_automatico_consulta_la_api_si_no_hay_cache(self, mock_get):
        mock_get.return_value = _mock_response()
        cot = cotizacion_dolar.obtener_cotizacion_actual()
        self.assertEqual(cot.fuente, CotizacionDolar.FUENTE_OFICIAL)
        self.assertEqual(cot.venta, Decimal("1020"))
        mock_get.assert_called_once()

    def test_carga_manual_fuerza_el_valor_aunque_este_viejo(self):
        manual = cotizacion_dolar.fijar_cotizacion_manual(Decimal("900"), Decimal("950"))
        # Simulamos que pasó mucho más que DOLAR_CACHE_MINUTOS desde la carga.
        CotizacionDolar.objects.filter(pk=manual.pk).update(
            fecha=timezone.now() - timedelta(days=2)
        )

        with mock.patch("precios.services.cotizacion_dolar.requests.get") as mock_get:
            cot = cotizacion_dolar.obtener_cotizacion_actual()
            mock_get.assert_not_called()

        self.assertEqual(cot.fuente, CotizacionDolar.FUENTE_MANUAL)
        self.assertEqual(cot.venta, Decimal("950"))

    def test_forzar_actualizacion_no_rompe_el_pin_manual(self):
        cotizacion_dolar.fijar_cotizacion_manual(Decimal("900"), Decimal("950"))
        with mock.patch("precios.services.cotizacion_dolar.requests.get") as mock_get:
            cot = cotizacion_dolar.obtener_cotizacion_actual(forzar_actualizacion=True)
            mock_get.assert_not_called()
        self.assertEqual(cot.fuente, CotizacionDolar.FUENTE_MANUAL)

    @mock.patch("precios.services.cotizacion_dolar.requests.get")
    def test_volver_a_oficial_saca_el_pin_y_trae_una_fresca(self, mock_get):
        cotizacion_dolar.fijar_cotizacion_manual(Decimal("900"), Decimal("950"))
        mock_get.return_value = _mock_response(compra="1000", venta="1020")

        cot = cotizacion_dolar.volver_a_cotizacion_oficial()

        self.assertEqual(cot.fuente, CotizacionDolar.FUENTE_OFICIAL)
        self.assertEqual(cot.venta, Decimal("1020"))
        config = ConfiguracionGlobal.actual()
        self.assertEqual(config.dolar_modo, ConfiguracionGlobal.DOLAR_MODO_AUTOMATICO)

        # Una vez de vuelta en automático, obtener_cotizacion_actual ya no
        # debe usar la manual vieja.
        with mock.patch("precios.services.cotizacion_dolar.requests.get") as mock_get2:
            cot2 = cotizacion_dolar.obtener_cotizacion_actual()
            mock_get2.assert_not_called()  # todavía "fresca" (recién la trajimos)
        self.assertEqual(cot2.fuente, CotizacionDolar.FUENTE_OFICIAL)

    @mock.patch("precios.services.cotizacion_dolar.requests.get")
    def test_referencia_oficial_no_depende_del_modo_manual(self, mock_get):
        cotizacion_dolar.fijar_cotizacion_manual(Decimal("900"), Decimal("950"))
        mock_get.return_value = _mock_response(compra="1000", venta="1020")

        referencia = cotizacion_dolar.obtener_cotizacion_oficial_referencia(forzar_actualizacion=True)

        self.assertEqual(referencia.fuente, CotizacionDolar.FUENTE_OFICIAL)
        self.assertEqual(referencia.venta, Decimal("1020"))
        # el pin manual sigue intacto: no se lo pisó al pedir la referencia.
        config = ConfiguracionGlobal.actual()
        self.assertEqual(config.dolar_modo, ConfiguracionGlobal.DOLAR_MODO_MANUAL)
        self.assertEqual(cotizacion_dolar.obtener_cotizacion_actual().fuente, CotizacionDolar.FUENTE_MANUAL)


class CotizacionDolarAPITests(APITestCase):
    def setUp(self):
        cache.clear()  # el throttle de login no se resetea solo entre tests
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")

    @mock.patch("precios.services.cotizacion_dolar.requests.get")
    def test_actual_en_modo_automatico_no_trae_referencia(self, mock_get):
        mock_get.return_value = _mock_response()
        resp = self.client.get("/api/dolar/actual/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["forzado_manual"])
        self.assertIsNone(resp.data["referencia_oficial"])

    @mock.patch("precios.services.cotizacion_dolar.requests.get")
    def test_manual_fuerza_y_expone_referencia_oficial(self, mock_get):
        mock_get.return_value = _mock_response(compra="1000", venta="1020")

        resp = self.client.post("/api/dolar/manual/", {"compra": "900", "venta": "950"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["forzado_manual"])
        self.assertEqual(Decimal(str(resp.data["venta"])), Decimal("950"))

        resp = self.client.get("/api/dolar/actual/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["forzado_manual"])
        self.assertEqual(Decimal(str(resp.data["venta"])), Decimal("950"))
        self.assertIsNotNone(resp.data["referencia_oficial"])
        self.assertEqual(Decimal(str(resp.data["referencia_oficial"]["venta"])), Decimal("1020"))

    @mock.patch("precios.services.cotizacion_dolar.requests.get")
    def test_volver_oficial_endpoint_saca_el_forzado(self, mock_get):
        mock_get.return_value = _mock_response(compra="1000", venta="1020")
        self.client.post("/api/dolar/manual/", {"compra": "900", "venta": "950"}, format="json")

        resp = self.client.post("/api/dolar/volver-oficial/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["forzado_manual"])
        self.assertEqual(Decimal(str(resp.data["venta"])), Decimal("1020"))

        resp = self.client.get("/api/dolar/actual/")
        self.assertFalse(resp.data["forzado_manual"])


class PreciosUsanCotizacionForzadaTests(APITestCase):
    """Confirma que forzar el dólar manual efectivamente cambia el valor que
    usan los cálculos de precio de clientes y tubos — no solo lo que se
    muestra en el gauge."""

    def setUp(self):
        cache.clear()  # el throttle de login no se resetea solo entre tests
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")
        self.cliente = Cliente.objects.create(
            numero=1, nombre="Test", incremento_dd=Decimal("8"), incremento_negra=Decimal("5"),
        )
        self.tubo = Tubo.objects.create(
            dimensiones="30 50 0,9", peso_unitario_kg=Decimal("3"), costo_usd_kg=Decimal("2"),
        )

    @mock.patch("precios.services.cotizacion_dolar.requests.get")
    def test_precios_de_cliente_usan_el_dolar_forzado_no_el_online(self, mock_get):
        mock_get.return_value = _mock_response(compra="1000", venta="1020")
        self.client.post("/api/dolar/manual/", {"compra": "900", "venta": "950"}, format="json")

        resp = self.client.get(f"/api/clientes/{self.cliente.id}/precios/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(str(resp.data["cotizacion_dolar"]["venta"])), Decimal("950"))

    @mock.patch("precios.services.cotizacion_dolar.requests.get")
    def test_precio_de_tubo_usa_el_dolar_forzado_en_el_numero_final(self, mock_get):
        mock_get.return_value = _mock_response(compra="1000", venta="1020")
        self.client.post("/api/dolar/manual/", {"compra": "900", "venta": "950"}, format="json")

        resp = self.client.get(f"/api/tubos/{self.tubo.id}/precio/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(str(resp.data["cotizacion_dolar"]["venta"])), Decimal("950"))

        config = ConfiguracionGlobal.actual()
        precio_esperado = self.tubo.precio_venta_pesos_tubo(config.incremento_tubos, Decimal("950")).quantize(Decimal("0.01"))
        precio_con_online = self.tubo.precio_venta_pesos_tubo(config.incremento_tubos, Decimal("1020")).quantize(Decimal("0.01"))

        precio_devuelto = Decimal(str(resp.data["precio"]["precio_venta_pesos_tubo"]))
        self.assertEqual(precio_devuelto, precio_esperado)
        self.assertNotEqual(precio_devuelto, precio_con_online)

    @mock.patch("precios.services.cotizacion_dolar.requests.get")
    def test_forzar_dolar_por_query_param_no_rompe_el_pin_en_los_precios(self, mock_get):
        mock_get.return_value = _mock_response(compra="1000", venta="1020")
        self.client.post("/api/dolar/manual/", {"compra": "900", "venta": "950"}, format="json")

        resp = self.client.get(f"/api/clientes/{self.cliente.id}/precios/?forzar_dolar=true")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(str(resp.data["cotizacion_dolar"]["venta"])), Decimal("950"))
