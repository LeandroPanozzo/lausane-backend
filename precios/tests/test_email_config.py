from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from rest_framework.test import APITestCase

from precios.models import Cliente, ConfiguracionGlobal, Presupuesto, PresupuestoItem
from precios.services.email_config import obtener_conexion_email, obtener_remitente
from precios.services.email_presupuesto import enviar_presupuesto_por_email


class ObtenerConexionEmailTests(APITestCase):
    """Si en Configuración se cargó una cuenta de Gmail, se usa esa para
    mandar — si no, cae en la configuración fija del .env."""

    def test_sin_cuenta_cargada_usa_la_conexion_por_defecto(self):
        conexion = obtener_conexion_email()
        # en tests Django ya fuerza el backend de memoria (mail.outbox);
        # lo importante es que NO sea una conexión SMTP a Gmail.
        self.assertFalse(hasattr(conexion, "host") and getattr(conexion, "host", None) == "smtp.gmail.com")

    def test_con_cuenta_cargada_arma_una_conexion_smtp_a_gmail(self):
        config = ConfiguracionGlobal.actual()
        config.email_remitente = "ventas@lausane.com.ar"
        config.email_password = "abcd efgh ijkl mnop"
        config.save(update_fields=["email_remitente", "email_password"])

        conexion = obtener_conexion_email()

        self.assertEqual(conexion.host, "smtp.gmail.com")
        self.assertEqual(conexion.port, 465)
        self.assertEqual(conexion.username, "ventas@lausane.com.ar")
        self.assertEqual(conexion.password, "abcd efgh ijkl mnop")
        self.assertTrue(conexion.use_ssl)

    def test_remitente_usa_el_default_si_no_hay_cuenta_cargada(self):
        from django.conf import settings
        self.assertEqual(obtener_remitente(), settings.DEFAULT_FROM_EMAIL)

    def test_remitente_usa_la_cuenta_cargada(self):
        config = ConfiguracionGlobal.actual()
        config.email_remitente = "ventas@lausane.com.ar"
        config.save(update_fields=["email_remitente"])
        self.assertEqual(obtener_remitente(), "ventas@lausane.com.ar")


class EnviarPresupuestoUsaLaCuentaConfiguradaTests(APITestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            numero=1, nombre="Test", incremento_dd=8, incremento_negra=5,
        )
        self.presupuesto = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=1000)
        PresupuestoItem.objects.create(
            presupuesto=self.presupuesto, descripcion="Item", cantidad=1, unidad="kg",
            precio_unitario_pesos=100,
        )

    def test_el_from_email_es_la_cuenta_configurada(self):
        config = ConfiguracionGlobal.actual()
        config.email_remitente = "ventas@lausane.com.ar"
        config.save(update_fields=["email_remitente"])

        enviar_presupuesto_por_email(self.presupuesto, "cliente@example.com")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "ventas@lausane.com.ar")
        self.assertEqual(mail.outbox[0].to, ["cliente@example.com"])
        self.assertEqual(len(mail.outbox[0].attachments), 1)


class ConfiguracionGlobalEmailAPITests(APITestCase):
    """La contraseña de Gmail se puede cargar/cambiar desde la API, pero
    nunca se devuelve en un GET — y un PATCH sin contraseña no borra la que
    ya estaba guardada."""

    def setUp(self):
        cache.clear()  # el throttle de login no se resetea solo entre tests
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")

    def test_get_nunca_devuelve_la_contrasena(self):
        config = ConfiguracionGlobal.actual()
        config.email_password = "secreta"
        config.save(update_fields=["email_password"])

        resp = self.client.get("/api/configuracion/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("email_password", resp.data)
        self.assertTrue(resp.data["email_password_configurada"])

    def test_patch_carga_remitente_y_contrasena(self):
        resp = self.client.patch(
            "/api/configuracion/",
            {"email_remitente": "ventas@lausane.com.ar", "email_password": "abcd efgh ijkl mnop"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["email_remitente"], "ventas@lausane.com.ar")
        self.assertTrue(resp.data["email_password_configurada"])

        config = ConfiguracionGlobal.actual()
        self.assertEqual(config.email_password, "abcd efgh ijkl mnop")

    def test_patch_sin_contrasena_no_borra_la_guardada(self):
        config = ConfiguracionGlobal.actual()
        config.email_password = "ya-guardada"
        config.save(update_fields=["email_password"])

        resp = self.client.patch(
            "/api/configuracion/", {"email_remitente": "otra@lausane.com.ar"}, format="json",
        )
        self.assertEqual(resp.status_code, 200)

        config.refresh_from_db()
        self.assertEqual(config.email_password, "ya-guardada")
        self.assertEqual(config.email_remitente, "otra@lausane.com.ar")
