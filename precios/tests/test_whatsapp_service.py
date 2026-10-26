from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from precios.models import Cliente, Presupuesto, PresupuestoItem
from precios.services import whatsapp_service
from precios.services.whatsapp_service import WhatsAppServiceError


class WhatsAppServiceUnitTests(APITestCase):
    """Pruebas del cliente HTTP contra el servicio Node, sin levantarlo de verdad."""

    @patch("precios.services.whatsapp_service.requests.get")
    def test_obtener_estado_ok(self, mock_get):
        mock_get.return_value = Mock(status_code=200, json=lambda: {"estado": "conectado", "numero": "5491100000000"})
        mock_get.return_value.raise_for_status = lambda: None
        resultado = whatsapp_service.obtener_estado()
        self.assertEqual(resultado["estado"], "conectado")

    @patch("precios.services.whatsapp_service.requests.get")
    def test_obtener_estado_sin_conexion_lanza_error(self, mock_get):
        import requests

        mock_get.side_effect = requests.ConnectionError("no se pudo conectar")
        with self.assertRaises(WhatsAppServiceError):
            whatsapp_service.obtener_estado()

    @patch("precios.services.whatsapp_service.requests.get")
    def test_obtener_qr_png_404_devuelve_none(self, mock_get):
        mock_get.return_value = Mock(status_code=404)
        self.assertIsNone(whatsapp_service.obtener_qr_png())

    @patch("precios.services.whatsapp_service.requests.post")
    def test_enviar_documento_ok(self, mock_post):
        mock_post.return_value = Mock(status_code=200, json=lambda: {"ok": True})
        resultado = whatsapp_service.enviar_documento("5491100000000", "hola", b"PDF", "a.pdf")
        self.assertTrue(resultado["ok"])
        # el archivo se manda en base64, no crudo
        payload_mandado = mock_post.call_args.kwargs["json"]
        self.assertIn("archivo_base64", payload_mandado)
        self.assertNotIn("archivo_bytes", payload_mandado)

    @patch("precios.services.whatsapp_service.requests.post")
    def test_enviar_documento_servicio_desconectado_lanza_error(self, mock_post):
        mock_post.return_value = Mock(
            status_code=503, json=lambda: {"error": "WhatsApp no está conectado todavía"}
        )
        with self.assertRaises(WhatsAppServiceError):
            whatsapp_service.enviar_documento("5491100000000", "hola", b"PDF", "a.pdf")


class WhatsAppEndpointsAPITests(APITestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="u1", password="x", is_staff=True)
        self.client.force_authenticate(self.usuario)

        self.cliente = Cliente.objects.create(
            numero=9001, nombre="Cliente WSP", telefono="5491137860195",
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

    @patch("precios.views.whatsapp_service.obtener_estado")
    def test_estado_proxy(self, mock_estado):
        mock_estado.return_value = {"estado": "conectado", "numero": "5491100000000"}
        resp = self.client.get("/api/whatsapp/estado/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["estado"], "conectado")

    @patch("precios.views.whatsapp_service.obtener_estado")
    def test_estado_servicio_caido_devuelve_502(self, mock_estado):
        mock_estado.side_effect = WhatsAppServiceError("no se pudo conectar")
        resp = self.client.get("/api/whatsapp/estado/")
        self.assertEqual(resp.status_code, 502)

    @patch("precios.views.whatsapp_service.obtener_qr_png")
    def test_qr_sin_pendiente_devuelve_404(self, mock_qr):
        mock_qr.return_value = None
        resp = self.client.get("/api/whatsapp/qr/")
        self.assertEqual(resp.status_code, 404)

    @patch("precios.views.whatsapp_service.obtener_qr_png")
    def test_qr_devuelve_imagen(self, mock_qr):
        mock_qr.return_value = b"\x89PNG..."
        resp = self.client.get("/api/whatsapp/qr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/png")

    @patch("precios.views.whatsapp_service.enviar_documento")
    def test_enviar_whatsapp_marca_como_enviado(self, mock_enviar):
        mock_enviar.return_value = {"ok": True}
        resp = self.client.post(f"/api/presupuestos/{self.presupuesto.id}/enviar-whatsapp/")
        self.assertEqual(resp.status_code, 200)
        self.presupuesto.refresh_from_db()
        self.assertEqual(self.presupuesto.estado, Presupuesto.ESTADO_ENVIADO)
        telefono_mandado = mock_enviar.call_args.args[0]
        self.assertEqual(telefono_mandado, "5491137860195")

    @patch("precios.views.whatsapp_service.enviar_documento")
    def test_enviar_whatsapp_sin_telefono_no_llama_al_servicio(self, mock_enviar):
        self.cliente.telefono = ""
        self.cliente.save(update_fields=["telefono"])
        resp = self.client.post(f"/api/presupuestos/{self.presupuesto.id}/enviar-whatsapp/")
        self.assertEqual(resp.status_code, 400)
        mock_enviar.assert_not_called()
        self.presupuesto.refresh_from_db()
        self.assertEqual(self.presupuesto.estado, Presupuesto.ESTADO_BORRADOR)

    @patch("precios.views.whatsapp_service.enviar_documento")
    def test_enviar_whatsapp_servicio_caido_no_marca_como_enviado(self, mock_enviar):
        mock_enviar.side_effect = WhatsAppServiceError("WhatsApp no está conectado todavía")
        resp = self.client.post(f"/api/presupuestos/{self.presupuesto.id}/enviar-whatsapp/")
        self.assertEqual(resp.status_code, 502)
        self.presupuesto.refresh_from_db()
        self.assertEqual(self.presupuesto.estado, Presupuesto.ESTADO_BORRADOR)
