from decimal import Decimal

from django.test import TestCase

from precios.models import Cliente, Presupuesto


class ClienteTests(TestCase):
    def test_coeficientes_son_el_incremento_dividido_100(self):
        cliente = Cliente.objects.create(
            numero=1, nombre="Test", incremento_dd=Decimal("8"), incremento_negra=Decimal("5"),
        )
        self.assertEqual(cliente.coeficiente_dd, Decimal("0.08"))
        self.assertEqual(cliente.coeficiente_negra, Decimal("0.05"))


class PresupuestoNumeracionTests(TestCase):
    """El número de presupuesto se asigna solo (arranca en 1000 y se
    incrementa), ver save() en models.py — antes tenía una condición de
    carrera si dos requests creaban un presupuesto al mismo tiempo."""

    def setUp(self):
        self.cliente = Cliente.objects.create(
            numero=1, nombre="Test", incremento_dd=Decimal("8"), incremento_negra=Decimal("5"),
        )

    def test_arranca_en_1000_y_se_incrementa(self):
        p1 = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"))
        p2 = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"))
        self.assertEqual(p1.numero, 1000)
        self.assertEqual(p2.numero, 1001)

    def test_no_pisa_un_numero_asignado_a_mano(self):
        p = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"), numero=5000)
        self.assertEqual(p.numero, 5000)
