from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from precios.models import Cliente, Presupuesto, PresupuestoItem, PresupuestoItemAjusteUnitario
from precios.services.texto_presupuesto import descripcion_item_con_ajustes, limpiar_descripcion_item


class LimpiarDescripcionItemTests(APITestCase):
    def test_quita_el_sufijo_de_descuento(self):
        self.assertEqual(limpiar_descripcion_item("Tubo 30 60 2 (desc. 2%)"), "Tubo 30 60 2")

    def test_quita_el_sufijo_de_descuento_con_decimales(self):
        self.assertEqual(limpiar_descripcion_item("Tubo 30 60 2 (desc. 10,5%)"), "Tubo 30 60 2")

    def test_sin_sufijo_no_cambia_nada(self):
        texto = "Chapa Laminado en Frío · espesor 23 · ancho 20000mm"
        self.assertEqual(limpiar_descripcion_item(texto), texto)

    def test_chapa_dd_vieja_se_renombra(self):
        self.assertEqual(
            limpiar_descripcion_item("Chapa DD · espesor 23 · ancho 20000mm"),
            "Chapa Laminado en Frío · espesor 23 · ancho 20000mm",
        )

    def test_chapa_negra_vieja_se_renombra(self):
        self.assertEqual(
            limpiar_descripcion_item("Chapa Negra · espesor 10 · ancho 1000mm"),
            "Chapa Laminado en Caliente · espesor 10 · ancho 1000mm",
        )

    def test_descripcion_ya_actualizada_no_cambia(self):
        texto = "Chapa Laminado en Frío · espesor 23 · ancho 20000mm"
        self.assertEqual(limpiar_descripcion_item(texto), texto)

    def test_no_toca_descripciones_sin_relacion(self):
        texto = "Tubo 30 60 2"
        self.assertEqual(limpiar_descripcion_item(texto), texto)

    def test_combina_ambas_limpiezas(self):
        self.assertEqual(
            limpiar_descripcion_item("Chapa DD · espesor 23 · ancho 20000mm (desc. 2%)"),
            "Chapa Laminado en Frío · espesor 23 · ancho 20000mm",
        )

    def test_agrega_los_extras_unitarios_al_lado_de_la_descripcion(self):
        cliente = Cliente.objects.create(
            numero=9012, nombre="Cliente Descripción", incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )
        presupuesto = Presupuesto.objects.create(cliente=cliente, cotizacion_dolar=Decimal("1000"))
        item = PresupuestoItem.objects.create(
            presupuesto=presupuesto, tipo=PresupuestoItem.TIPO_CHAPA, descripcion="Chapa DD · espesor 16",
            cantidad=Decimal("1"), precio_unitario_pesos=Decimal("1000"),
        )
        PresupuestoItemAjusteUnitario.objects.create(item=item, descripcion="Estampado", monto_pesos=Decimal("50"))
        self.assertEqual(
            descripcion_item_con_ajustes(item),
            "Chapa Laminado en Frío · espesor 16 (Estampado)",
        )


class DescripcionLimpiaEnApiTests(APITestCase):
    """La pantalla de Ítems del presupuesto usa la API: un ítem viejo con
    'Chapa DD' guardado tiene que verse ahí también con el nombre actual."""

    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="u1", password="x", is_staff=True)
        self.client.force_authenticate(self.usuario)
        self.cliente = Cliente.objects.create(
            numero=9011, nombre="Cliente Texto API", incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )
        self.presupuesto = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"))
        PresupuestoItem.objects.create(
            presupuesto=self.presupuesto, tipo=PresupuestoItem.TIPO_CHAPA,
            descripcion="Chapa DD · espesor 23 · ancho 20000mm",
            cantidad=Decimal("1"), precio_unitario_pesos=Decimal("1000"),
        )

    def test_descripcion_vieja_llega_limpia_por_la_api(self):
        resp = self.client.get(f"/api/presupuestos/{self.presupuesto.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["items"][0]["descripcion"], "Chapa Laminado en Frío · espesor 23 · ancho 20000mm")
