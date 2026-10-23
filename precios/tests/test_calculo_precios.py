from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APITestCase

from precios.models import ChapaGalvanizada, ChapaGruesa, Cliente, ConfiguracionGlobal, MarkupEspesorChapa, Tubo
from precios.services import calculo_precios


class CoeficienteTests(TestCase):
    def test_coeficiente_es_el_porcentaje_sobre_100(self):
        self.assertEqual(calculo_precios.coeficiente(Decimal("8")), Decimal("0.08"))
        self.assertEqual(calculo_precios.coeficiente(Decimal("0")), Decimal("0"))


class CalcularBaseChapaTests(TestCase):
    def test_reproduce_las_columnas_h_i_j_k_del_excel(self):
        resultado = calculo_precios.calcular_base_chapa(
            incremento_pct=Decimal("8"), precio_base=Decimal("100"), cotizacion=Decimal("1000")
        )
        self.assertEqual(resultado["coeficiente"], Decimal("0.08"))
        self.assertEqual(resultado["resultado"], Decimal("8.00"))
        self.assertEqual(resultado["base_usd"], Decimal("108.00"))
        self.assertEqual(resultado["base_pesos"], Decimal("108000.00"))


class CalcularPrecioTuboTests(TestCase):
    def test_encadena_costo_peso_y_cotizacion(self):
        config = ConfiguracionGlobal(incremento_tubos=Decimal("0.26"))
        tubo = Tubo(
            dimensiones="30 50 0,9", peso_unitario_kg=Decimal("3"), costo_usd_kg=Decimal("2"),
        )
        resultado = calculo_precios.calcular_precio_tubo(tubo, config, cotizacion=Decimal("1000"))

        precio_usd_kg_esperado = (Decimal("2") * Decimal("1.26")).quantize(Decimal("0.00001"))
        precio_usd_tubo_esperado = (Decimal("2") * Decimal("1.26") * Decimal("3")).quantize(Decimal("0.00001"))
        precio_pesos_esperado = (Decimal("2") * Decimal("1.26") * Decimal("3") * Decimal("1000")).quantize(Decimal("0.01"))

        self.assertEqual(resultado["precio_venta_usd_kg"], precio_usd_kg_esperado)
        self.assertEqual(resultado["precio_venta_usd_tubo"], precio_usd_tubo_esperado)
        self.assertEqual(resultado["precio_venta_pesos_tubo"], precio_pesos_esperado)

        # Descuento por defecto del tubo (2%, habilitado) ya viene aplicado.
        self.assertEqual(resultado["descuento_pct"], Decimal("2.00"))
        self.assertTrue(resultado["descuento_habilitado"])
        self.assertEqual(
            resultado["precio_venta_pesos_tubo_con_descuento"],
            (precio_pesos_esperado * Decimal("0.98")).quantize(Decimal("0.01")),
        )

    def test_descuento_deshabilitado_no_se_aplica(self):
        config = ConfiguracionGlobal(incremento_tubos=Decimal("0.26"))
        tubo = Tubo(
            dimensiones="30 50 0,9", peso_unitario_kg=Decimal("3"), costo_usd_kg=Decimal("2"),
            descuento_pct=Decimal("5"), descuento_habilitado=False,
        )
        resultado = calculo_precios.calcular_precio_tubo(tubo, config, cotizacion=Decimal("1000"))
        self.assertEqual(resultado["precio_venta_pesos_tubo_con_descuento"], resultado["precio_venta_pesos_tubo"])


class AplicarDescuentoTuboTests(TestCase):
    def test_aplica_el_porcentaje_cuando_esta_habilitado(self):
        self.assertEqual(
            calculo_precios.aplicar_descuento_tubo(Decimal("1000.00"), Decimal("2"), True),
            Decimal("980.00"),
        )

    def test_no_aplica_nada_cuando_esta_deshabilitado(self):
        self.assertEqual(
            calculo_precios.aplicar_descuento_tubo(Decimal("1000.00"), Decimal("50"), False),
            Decimal("1000.00"),
        )


class CalcularListaPreciosChapaTests(TestCase):
    def setUp(self):
        self.config = ConfiguracionGlobal.actual()
        self.config.precio_base_dd = Decimal("1.3")
        self.config.precio_base_negra = Decimal("1.1")
        self.config.save()
        self.cliente = Cliente.objects.create(
            numero=1, nombre="Cliente Test", incremento_dd=Decimal("8"), incremento_negra=Decimal("5"),
        )
        MarkupEspesorChapa.objects.create(
            tipo=MarkupEspesorChapa.TIPO_DD, espesor="16", ancho_mm="1000", porcentaje=Decimal("0.07"), orden=1,
        )
        MarkupEspesorChapa.objects.create(
            tipo=MarkupEspesorChapa.TIPO_DD, espesor="18", ancho_mm="1000", porcentaje=None, orden=2,
        )

    def test_marca_disponible_false_cuando_no_hay_porcentaje(self):
        precios = calculo_precios.calcular_lista_precios_chapa(self.cliente, self.config, Decimal("1000"))
        por_espesor = precios[MarkupEspesorChapa.TIPO_DD]["precios_por_espesor"]

        fila_16 = next(f for f in por_espesor if f["espesor"] == "16")
        fila_18 = next(f for f in por_espesor if f["espesor"] == "18")

        self.assertTrue(fila_16["disponible"])
        self.assertIsNotNone(fila_16["precio_pesos"])
        self.assertFalse(fila_18["disponible"])
        self.assertIsNone(fila_18["precio_pesos"])

    def test_recargo_inactivo_no_aparece_en_la_lista_del_cliente(self):
        MarkupEspesorChapa.objects.create(
            tipo=MarkupEspesorChapa.TIPO_DD, espesor="20", ancho_mm="1000",
            porcentaje=Decimal("0.05"), orden=3, activo=False,
        )
        precios = calculo_precios.calcular_lista_precios_chapa(self.cliente, self.config, Decimal("1000"))
        por_espesor = precios[MarkupEspesorChapa.TIPO_DD]["precios_por_espesor"]
        espesores = [f["espesor"] for f in por_espesor]
        self.assertNotIn("20", espesores)
        self.assertIn("16", espesores)

    def test_sin_descuento_cargado_el_precio_no_cambia(self):
        self.cliente.descuento_dd = Decimal("0")
        self.cliente.save()
        precios = calculo_precios.calcular_lista_precios_chapa(self.cliente, self.config, Decimal("1000"))
        fila_16 = next(f for f in precios[MarkupEspesorChapa.TIPO_DD]["precios_por_espesor"] if f["espesor"] == "16")
        # base_usd=1.404 (1.3 * 1.08) * factor 1.07 = 1.50228, quantizado a 4 decimales = 1.5023
        self.assertEqual(fila_16["precio_usd"], Decimal("1.5023"))

    def test_aplica_el_descuento_propio_del_cliente_sobre_el_precio_final(self):
        self.cliente.descuento_dd = Decimal("10")
        self.cliente.save()
        precios = calculo_precios.calcular_lista_precios_chapa(self.cliente, self.config, Decimal("1000"))
        fila_16 = next(f for f in precios[MarkupEspesorChapa.TIPO_DD]["precios_por_espesor"] if f["espesor"] == "16")
        self.assertEqual(precios[MarkupEspesorChapa.TIPO_DD]["descuento_pct"], Decimal("10"))
        # precio sin descuento (1.50228) * (1 - 10%) = 1.352052, quantizado a 4 decimales = 1.3521
        self.assertEqual(fila_16["precio_usd"], Decimal("1.3521"))

    def test_el_descuento_de_dd_no_afecta_a_negra(self):
        MarkupEspesorChapa.objects.create(
            tipo=MarkupEspesorChapa.TIPO_NEGRA, espesor="2", ancho_mm="1000", porcentaje=Decimal("0.14"), orden=1,
        )
        self.cliente.descuento_dd = Decimal("50")
        self.cliente.descuento_negra = Decimal("0")
        self.cliente.save()
        precios = calculo_precios.calcular_lista_precios_chapa(self.cliente, self.config, Decimal("1000"))
        self.assertEqual(precios[MarkupEspesorChapa.TIPO_NEGRA]["descuento_pct"], Decimal("0"))


class DescuentoTuboAPITests(APITestCase):
    """El % de descuento y su checkbox se editan por tubo desde /api/tubos/{id}/
    y ya vienen aplicados en /api/tubos/{id}/precio/ y /api/tubos/lista-precios/."""

    def setUp(self):
        cache.clear()  # el throttle de login no se resetea solo entre tests
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")
        self.tubo = Tubo.objects.create(
            dimensiones="30 50 0,9", peso_unitario_kg=Decimal("3"), costo_usd_kg=Decimal("2"),
        )

    def test_tubo_nuevo_trae_2_por_ciento_habilitado_por_defecto(self):
        resp = self.client.get(f"/api/tubos/{self.tubo.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(str(resp.data["descuento_pct"])), Decimal("2.00"))
        self.assertTrue(resp.data["descuento_habilitado"])

    def test_patch_actualiza_el_descuento_del_tubo(self):
        resp = self.client.patch(
            f"/api/tubos/{self.tubo.id}/", {"descuento_pct": "5", "descuento_habilitado": False}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(str(resp.data["descuento_pct"])), Decimal("5.00"))
        self.assertFalse(resp.data["descuento_habilitado"])

        # y ese cambio ya se refleja en el precio calculado (sin aplicar nada,
        # porque lo deshabilitamos).
        resp = self.client.get(f"/api/tubos/{self.tubo.id}/precio/")
        self.assertEqual(resp.status_code, 200)
        precio = resp.data["precio"]
        self.assertEqual(precio["precio_venta_pesos_tubo_con_descuento"], precio["precio_venta_pesos_tubo"])

    def test_lista_precios_incluye_el_descuento_de_cada_tubo(self):
        self.client.patch(f"/api/tubos/{self.tubo.id}/", {"descuento_pct": "10"}, format="json")
        resp = self.client.get("/api/tubos/lista-precios/")
        self.assertEqual(resp.status_code, 200)
        fila = next(t for t in resp.data["tubos"] if t["id"] == self.tubo.id)
        self.assertEqual(Decimal(str(fila["descuento_pct"])), Decimal("10.00"))
        self.assertTrue(fila["descuento_habilitado"])
        precio_sin_desc = Decimal(str(fila["precio_venta_pesos_tubo"]))
        precio_con_desc = Decimal(str(fila["precio_venta_pesos_tubo_con_descuento"]))
        self.assertEqual(precio_con_desc, (precio_sin_desc * Decimal("0.9")).quantize(Decimal("0.01")))


class ActivoMarkupChapaAPITests(APITestCase):
    """El checkbox de activo/inactivo de un recargo de chapa se edita desde
    /api/markups-chapa/{id}/, igual que 'activo' en tubos."""

    def setUp(self):
        cache.clear()  # el throttle de login no se resetea solo entre tests
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")
        self.markup = MarkupEspesorChapa.objects.create(
            tipo=MarkupEspesorChapa.TIPO_DD, espesor="16", ancho_mm="1000", porcentaje=Decimal("0.07"),
        )

    def test_nuevo_recargo_viene_activo_por_defecto(self):
        resp = self.client.get(f"/api/markups-chapa/{self.markup.id}/")
        self.assertTrue(resp.data["activo"])

    def test_patch_puede_marcarlo_inactivo(self):
        resp = self.client.patch(f"/api/markups-chapa/{self.markup.id}/", {"activo": False}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["activo"])


class FiltroTipoMarkupChapaAPITests(APITestCase):
    """?tipo=DD/NEGRA tiene que devolver solo ese tipo — en algún momento dejó
    de funcionar en silencio (DEFAULT_FILTER_BACKENDS no trae django-filter,
    así que `filterset_fields` por sí solo no filtra nada) y la pestaña
    "Laminado en Frío" terminaba mostrando también todas las filas de Negra."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")
        MarkupEspesorChapa.objects.create(
            tipo=MarkupEspesorChapa.TIPO_DD, espesor="16", ancho_mm="1000", porcentaje=Decimal("0.07"),
        )
        MarkupEspesorChapa.objects.create(
            tipo=MarkupEspesorChapa.TIPO_NEGRA, espesor="2", ancho_mm="1000", porcentaje=Decimal("0.14"),
        )

    def test_filtra_por_tipo_dd(self):
        resp = self.client.get("/api/markups-chapa/", {"tipo": "DD"})
        self.assertEqual(resp.status_code, 200)
        resultados = resp.data["results"] if "results" in resp.data else resp.data
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["tipo"], "DD")

    def test_filtra_por_tipo_negra(self):
        resp = self.client.get("/api/markups-chapa/", {"tipo": "NEGRA"})
        self.assertEqual(resp.status_code, 200)
        resultados = resp.data["results"] if "results" in resp.data else resp.data
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["tipo"], "NEGRA")

    def test_sin_filtro_devuelve_todo(self):
        resp = self.client.get("/api/markups-chapa/")
        resultados = resp.data["results"] if "results" in resp.data else resp.data
        self.assertEqual(len(resultados), 2)


class CalcularPrecioGalvanizadaTests(TestCase):
    """A diferencia de DD/Negra, cada espesor/ancho de galvanizada tiene su
    propio costo en U$S/kg — mismo esquema que Tubo (costo + incremento
    global), no un % sobre una base compartida."""

    def test_encadena_costo_incremento_y_cotizacion(self):
        config = ConfiguracionGlobal(incremento_galvanizada=Decimal("0.20"))
        chapa = ChapaGalvanizada(espesor="16", ancho_mm="1000", costo_usd_kg=Decimal("1.5"))
        resultado = calculo_precios.calcular_precio_galvanizada(chapa, config, cotizacion=Decimal("1000"))

        precio_usd_kg_esperado = (Decimal("1.5") * Decimal("1.20")).quantize(Decimal("0.00001"))
        precio_pesos_esperado = (Decimal("1.5") * Decimal("1.20") * Decimal("1000")).quantize(Decimal("0.01"))

        self.assertEqual(resultado["precio_venta_usd_kg"], precio_usd_kg_esperado)
        self.assertEqual(resultado["precio_venta_pesos_kg"], precio_pesos_esperado)

    def test_usar_incremento_general_en_false_vende_al_costo(self):
        config = ConfiguracionGlobal(incremento_galvanizada=Decimal("0.20"))
        chapa = ChapaGalvanizada(
            espesor="16", ancho_mm="1000", costo_usd_kg=Decimal("1.5"), usar_incremento_general=False,
        )
        resultado = calculo_precios.calcular_precio_galvanizada(chapa, config, cotizacion=Decimal("1000"))

        self.assertEqual(resultado["incremento_aplicado"], Decimal("0"))
        self.assertEqual(resultado["precio_venta_usd_kg"], Decimal("1.5").quantize(Decimal("0.00001")))
        self.assertEqual(resultado["precio_venta_pesos_kg"], Decimal("1500.00"))

    def test_inactiva_no_aparece_en_la_lista(self):
        config = ConfiguracionGlobal.actual()
        ChapaGalvanizada.objects.create(espesor="16", ancho_mm="1000", costo_usd_kg=Decimal("1.5"))
        ChapaGalvanizada.objects.create(espesor="18", ancho_mm="1000", costo_usd_kg=Decimal("1.6"), activo=False)

        precios = calculo_precios.calcular_lista_precios_galvanizada(config, Decimal("1000"))
        espesores = [p["espesor"] for p in precios]
        self.assertIn("16", espesores)
        self.assertNotIn("18", espesores)


class ChapaGalvanizadaAPITests(APITestCase):
    def setUp(self):
        cache.clear()  # el throttle de login no se resetea solo entre tests
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")

    def test_crear_y_ver_en_lista_precios(self):
        resp = self.client.post(
            "/api/galvanizada/", {"espesor": "16", "ancho_mm": "1000", "costo_usd_kg": "1.5"}, format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["activo"])

        resp = self.client.get("/api/galvanizada/lista-precios/")
        self.assertEqual(resp.status_code, 200)
        fila = next(c for c in resp.data["chapas"] if c["espesor"] == "16")
        self.assertIn("precio_venta_pesos_kg", fila)

    def test_patch_puede_marcarla_inactiva(self):
        creada = self.client.post(
            "/api/galvanizada/", {"espesor": "16", "ancho_mm": "1000", "costo_usd_kg": "1.5"}, format="json",
        ).data
        resp = self.client.patch(f"/api/galvanizada/{creada['id']}/", {"activo": False}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["activo"])

    def test_patch_puede_sacarle_el_incremento_general(self):
        creada = self.client.post(
            "/api/galvanizada/", {"espesor": "16", "ancho_mm": "1000", "costo_usd_kg": "1.5"}, format="json",
        ).data
        self.assertTrue(creada["usar_incremento_general"])

        resp = self.client.patch(
            f"/api/galvanizada/{creada['id']}/", {"usar_incremento_general": False}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["usar_incremento_general"])

        resp = self.client.get("/api/galvanizada/lista-precios/")
        fila = next(c for c in resp.data["chapas"] if c["id"] == creada["id"])
        self.assertFalse(fila["usar_incremento_general"])
        self.assertEqual(Decimal(str(fila["precio_venta_usd_kg"])), Decimal("1.5").quantize(Decimal("0.00001")))


class CalcularPrecioGruesaTests(TestCase):
    """Misma lógica que galvanizada: costo propio en U$S/kg + incremento
    general, en vez de un % sobre una base compartida."""

    def test_encadena_costo_incremento_y_cotizacion(self):
        config = ConfiguracionGlobal(incremento_gruesas=Decimal("0.20"))
        chapa = ChapaGruesa(espesor="25", ancho_mm="2000", costo_usd_kg=Decimal("1.8"))
        resultado = calculo_precios.calcular_precio_gruesa(chapa, config, cotizacion=Decimal("1000"))

        precio_usd_kg_esperado = (Decimal("1.8") * Decimal("1.20")).quantize(Decimal("0.00001"))
        precio_pesos_esperado = (Decimal("1.8") * Decimal("1.20") * Decimal("1000")).quantize(Decimal("0.01"))

        self.assertEqual(resultado["precio_venta_usd_kg"], precio_usd_kg_esperado)
        self.assertEqual(resultado["precio_venta_pesos_kg"], precio_pesos_esperado)

    def test_usar_incremento_general_en_false_vende_al_costo(self):
        config = ConfiguracionGlobal(incremento_gruesas=Decimal("0.20"))
        chapa = ChapaGruesa(
            espesor="25", ancho_mm="2000", costo_usd_kg=Decimal("1.8"), usar_incremento_general=False,
        )
        resultado = calculo_precios.calcular_precio_gruesa(chapa, config, cotizacion=Decimal("1000"))

        self.assertEqual(resultado["incremento_aplicado"], Decimal("0"))
        self.assertEqual(resultado["precio_venta_usd_kg"], Decimal("1.8").quantize(Decimal("0.00001")))
        self.assertEqual(resultado["precio_venta_pesos_kg"], Decimal("1800.00"))

    def test_inactiva_no_aparece_en_la_lista(self):
        config = ConfiguracionGlobal.actual()
        ChapaGruesa.objects.create(espesor="25", ancho_mm="2000", costo_usd_kg=Decimal("1.8"))
        ChapaGruesa.objects.create(espesor="32", ancho_mm="2000", costo_usd_kg=Decimal("1.9"), activo=False)

        precios = calculo_precios.calcular_lista_precios_gruesa(config, Decimal("1000"))
        espesores = [p["espesor"] for p in precios]
        self.assertIn("25", espesores)
        self.assertNotIn("32", espesores)


class ChapaGruesaAPITests(APITestCase):
    def setUp(self):
        cache.clear()  # el throttle de login no se resetea solo entre tests
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")

    def test_crear_y_ver_en_lista_precios(self):
        resp = self.client.post(
            "/api/gruesas/", {"espesor": "25", "ancho_mm": "2000", "costo_usd_kg": "1.8"}, format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["activo"])

        resp = self.client.get("/api/gruesas/lista-precios/")
        self.assertEqual(resp.status_code, 200)
        fila = next(c for c in resp.data["chapas"] if c["espesor"] == "25")
        self.assertIn("precio_venta_pesos_kg", fila)

    def test_patch_puede_marcarla_inactiva(self):
        creada = self.client.post(
            "/api/gruesas/", {"espesor": "25", "ancho_mm": "2000", "costo_usd_kg": "1.8"}, format="json",
        ).data
        resp = self.client.patch(f"/api/gruesas/{creada['id']}/", {"activo": False}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["activo"])

    def test_patch_puede_sacarle_el_incremento_general(self):
        creada = self.client.post(
            "/api/gruesas/", {"espesor": "25", "ancho_mm": "2000", "costo_usd_kg": "1.8"}, format="json",
        ).data
        self.assertTrue(creada["usar_incremento_general"])

        resp = self.client.patch(
            f"/api/gruesas/{creada['id']}/", {"usar_incremento_general": False}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["usar_incremento_general"])

        resp = self.client.get("/api/gruesas/lista-precios/")
        fila = next(c for c in resp.data["chapas"] if c["id"] == creada["id"])
        self.assertFalse(fila["usar_incremento_general"])
        self.assertEqual(Decimal(str(fila["precio_venta_usd_kg"])), Decimal("1.8").quantize(Decimal("0.00001")))


class DescuentoClienteAPITests(APITestCase):
    """El % de descuento propio de DD/Negra se edita por cliente desde
    /api/clientes/{id}/ y se ve reflejado en /api/clientes/{id}/precios/."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")
        config = ConfiguracionGlobal.actual()
        config.precio_base_dd = Decimal("1.3")
        config.save()
        self.cliente = Cliente.objects.create(
            numero=1, nombre="Cliente Test", incremento_dd=Decimal("8"), incremento_negra=Decimal("5"),
        )
        MarkupEspesorChapa.objects.create(
            tipo=MarkupEspesorChapa.TIPO_DD, espesor="16", ancho_mm="1000", porcentaje=Decimal("0.07"),
        )

    def test_cliente_nuevo_viene_sin_descuento_por_defecto(self):
        resp = self.client.get(f"/api/clientes/{self.cliente.id}/")
        self.assertEqual(Decimal(resp.data["descuento_dd"]), Decimal("0"))
        self.assertEqual(Decimal(resp.data["descuento_negra"]), Decimal("0"))

    def test_patch_carga_el_descuento_y_se_aplica_en_precios(self):
        resp = self.client.patch(f"/api/clientes/{self.cliente.id}/", {"descuento_dd": "10"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(resp.data["descuento_dd"]), Decimal("10"))

        resp = self.client.get(f"/api/clientes/{self.cliente.id}/precios/")
        self.assertEqual(resp.status_code, 200)
        fila = next(f for f in resp.data["precios"]["DD"]["precios_por_espesor"] if f["espesor"] == "16")
        self.assertEqual(Decimal(str(fila["precio_usd"])), Decimal("1.3521"))
