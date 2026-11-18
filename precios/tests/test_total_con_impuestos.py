"""
El "total" que se le comunica al cliente (texto del email, texto de
WhatsApp) tiene que ser el total final CON impuestos, no el neto —
regresión de un bug donde esos textos usaban total_pesos (neto) en vez
de total_pesos + IVA.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework.test import APITestCase

from precios.models import Cliente, Presupuesto, PresupuestoItem
from precios.serializers import PresupuestoSerializer
from precios.services.email_presupuesto import enviar_presupuesto_por_email


class TotalConImpuestosPesosTests(APITestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            numero=9200, nombre="Cliente Impuestos", incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )

    def test_sin_impuesto_elegido_es_igual_al_neto(self):
        presupuesto = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"))
        PresupuestoItem.objects.create(
            presupuesto=presupuesto, descripcion="Item", cantidad=Decimal("1"), precio_unitario_pesos=Decimal("1000"),
        )
        self.assertEqual(presupuesto.total_con_impuestos_pesos, presupuesto.total_pesos)

    def test_con_impuesto_elegido_suma_el_porcentaje_sobre_el_neto(self):
        presupuesto = Presupuesto.objects.create(
            cliente=self.cliente, cotizacion_dolar=Decimal("1000"), impuesto_pct=Decimal("21"),
        )
        PresupuestoItem.objects.create(
            presupuesto=presupuesto, descripcion="Item", cantidad=Decimal("1"), precio_unitario_pesos=Decimal("1000"),
        )
        self.assertEqual(presupuesto.total_pesos, Decimal("1000.00"))
        # 1000 + 21% = 1210.00
        self.assertEqual(presupuesto.total_con_impuestos_pesos, Decimal("1210.00"))

    def test_serializer_expone_el_total_con_impuestos(self):
        presupuesto = Presupuesto.objects.create(
            cliente=self.cliente, cotizacion_dolar=Decimal("1000"), impuesto_pct=Decimal("10.5"),
        )
        PresupuestoItem.objects.create(
            presupuesto=presupuesto, descripcion="Item", cantidad=Decimal("1"), precio_unitario_pesos=Decimal("1000"),
        )
        datos = PresupuestoSerializer(presupuesto).data
        self.assertEqual(Decimal(str(datos["total_con_impuestos_pesos"])), Decimal("1105.00"))


class EmailMuestraElTotalConImpuestosTests(APITestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            numero=9201, nombre="Cliente Email Impuestos", incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )
        self.presupuesto = Presupuesto.objects.create(
            cliente=self.cliente, cotizacion_dolar=Decimal("1000"), impuesto_pct=Decimal("21"),
        )
        PresupuestoItem.objects.create(
            presupuesto=self.presupuesto, descripcion="Item", cantidad=Decimal("1"), precio_unitario_pesos=Decimal("1000"),
        )

    def test_el_cuerpo_del_mail_muestra_el_total_con_impuestos_no_el_neto(self):
        enviar_presupuesto_por_email(self.presupuesto, "cliente@example.com")

        self.assertEqual(len(mail.outbox), 1)
        cuerpo = mail.outbox[0].body
        self.assertIn("Total: $ 1,210.00", cuerpo)
        self.assertNotIn("Total: $ 1,000.00", cuerpo)


class WhatsappMuestraElTotalConImpuestosTests(APITestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="u1", password="x", is_staff=True)
        self.client.force_authenticate(self.usuario)
        self.cliente = Cliente.objects.create(
            numero=9202, nombre="Cliente WSP Impuestos", telefono="5491137860195",
            incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )
        self.presupuesto = Presupuesto.objects.create(
            cliente=self.cliente, cotizacion_dolar=Decimal("1000"), impuesto_pct=Decimal("21"),
        )
        PresupuestoItem.objects.create(
            presupuesto=self.presupuesto, descripcion="Item", cantidad=Decimal("1"), precio_unitario_pesos=Decimal("1000"),
        )

    @patch("precios.views.whatsapp_service.enviar_documento")
    def test_el_texto_del_whatsapp_muestra_el_total_con_impuestos_no_el_neto(self, mock_enviar):
        mock_enviar.return_value = {"ok": True}
        resp = self.client.post(f"/api/presupuestos/{self.presupuesto.id}/enviar-whatsapp/")
        self.assertEqual(resp.status_code, 200)

        texto_mandado = mock_enviar.call_args.args[1]
        self.assertIn("$ 1.210,00", texto_mandado)
        self.assertNotIn("$ 1.000,00", texto_mandado)
