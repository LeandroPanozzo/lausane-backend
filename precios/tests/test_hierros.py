from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APITestCase

from precios.models import Cliente, ConfiguracionHierro, Hierro, MONEDA_ARS, MONEDA_USD, Presupuesto, PresupuestoItem
from precios.services import calculo_precios


class CalcularPrecioHierroTests(TestCase):
    """Mismo esquema que Galvanizada/Gruesa: costo propio en U$S/kg + el
    incremento general propio de su tipo (ConfiguracionHierro)."""

    def test_encadena_costo_incremento_y_cotizacion(self):
        config_tipo = ConfiguracionHierro(tipo=ConfiguracionHierro.TIPO_PLANCHUELA, incremento_general=Decimal("0.20"))
        hierro = Hierro(tipo=ConfiguracionHierro.TIPO_PLANCHUELA, medida="25x3mm", costo_usd_kg=Decimal("1.5"))
        resultado = calculo_precios.calcular_precio_hierro(hierro, config_tipo, cotizacion=Decimal("1000"))

        precio_usd_esperado = (Decimal("1.5") * Decimal("1.20")).quantize(Decimal("0.00001"))
        precio_pesos_esperado = (Decimal("1.5") * Decimal("1.20") * Decimal("1000")).quantize(Decimal("0.01"))
        self.assertEqual(resultado["precio_venta_usd_kg"], precio_usd_esperado)
        self.assertEqual(resultado["precio_venta_pesos_kg"], precio_pesos_esperado)

    def test_sin_peso_unitario_los_precios_por_unidad_son_none(self):
        config_tipo = ConfiguracionHierro(tipo=ConfiguracionHierro.TIPO_PLANCHUELA, incremento_general=Decimal("0.20"))
        hierro = Hierro(tipo=ConfiguracionHierro.TIPO_PLANCHUELA, medida="25x3mm", costo_usd_kg=Decimal("1.5"))
        resultado = calculo_precios.calcular_precio_hierro(hierro, config_tipo, cotizacion=Decimal("1000"))

        self.assertIsNone(resultado["peso_unitario_kg"])
        self.assertIsNone(resultado["precio_venta_usd_unidad"])
        self.assertIsNone(resultado["precio_venta_pesos_unidad"])
        self.assertIsNone(resultado["precio_venta_pesos_unidad_con_descuento"])

    def test_con_peso_unitario_calcula_el_precio_por_unidad(self):
        """Igual que Tubo.peso_unitario_kg: precio por kg * peso = precio por unidad/barra."""
        config_tipo = ConfiguracionHierro(tipo=ConfiguracionHierro.TIPO_PERFIL_IPN, incremento_general=Decimal("0.20"))
        hierro = Hierro(
            tipo=ConfiguracionHierro.TIPO_PERFIL_IPN, medida="IPN 80", costo_usd_kg=Decimal("1.5"),
            peso_unitario_kg=Decimal("6"), descuento_pct=Decimal("10"), descuento_habilitado=True,
        )
        resultado = calculo_precios.calcular_precio_hierro(hierro, config_tipo, cotizacion=Decimal("1000"))

        # 1.5 * 1.20 = 1.80 USD/kg -> 1800.00 $/kg -> * 6kg = 10800.00 $/unidad sin descuento
        self.assertEqual(resultado["precio_venta_pesos_unidad"], Decimal("10800.00"))
        # Con 10% de descuento: 10800 * 0.90 = 9720.00
        self.assertEqual(resultado["precio_venta_pesos_unidad_con_descuento"], Decimal("9720.00"))

    def test_usar_incremento_general_en_false_vende_al_costo(self):
        config_tipo = ConfiguracionHierro(tipo=ConfiguracionHierro.TIPO_REDONDO_MACIZO, incremento_general=Decimal("0.20"))
        hierro = Hierro(
            tipo=ConfiguracionHierro.TIPO_REDONDO_MACIZO, medida='1/2"', costo_usd_kg=Decimal("1.5"),
            usar_incremento_general=False,
        )
        resultado = calculo_precios.calcular_precio_hierro(hierro, config_tipo, cotizacion=Decimal("1000"))

        self.assertEqual(resultado["incremento_aplicado"], Decimal("0"))
        self.assertEqual(resultado["precio_venta_usd_kg"], Decimal("1.5").quantize(Decimal("0.00001")))
        self.assertEqual(resultado["precio_venta_pesos_kg"], Decimal("1500.00"))

    def test_precio_manual_en_pesos_pisa_el_calculo_automatico(self):
        config_tipo = ConfiguracionHierro(tipo=ConfiguracionHierro.TIPO_CUADRADO_MACIZO, incremento_general=Decimal("0.20"))
        hierro = Hierro(
            tipo=ConfiguracionHierro.TIPO_CUADRADO_MACIZO, medida="10mm", costo_usd_kg=Decimal("1.5"),
            precio_venta_manual=Decimal("2000"), precio_venta_moneda=MONEDA_ARS,
        )
        resultado = calculo_precios.calcular_precio_hierro(hierro, config_tipo, cotizacion=Decimal("1000"))

        self.assertIsNone(resultado["incremento_aplicado"])
        self.assertEqual(resultado["precio_venta_pesos_kg"], Decimal("2000.00"))

    def test_precio_manual_en_dolares_se_multiplica_por_la_cotizacion(self):
        config_tipo = ConfiguracionHierro(tipo=ConfiguracionHierro.TIPO_PERFIL_IPN, incremento_general=Decimal("0.20"))
        hierro = Hierro(
            tipo=ConfiguracionHierro.TIPO_PERFIL_IPN, medida="IPN 80", costo_usd_kg=Decimal("1.5"),
            precio_venta_manual=Decimal("3"), precio_venta_moneda=MONEDA_USD,
        )
        resultado = calculo_precios.calcular_precio_hierro(hierro, config_tipo, cotizacion=Decimal("1000"))

        self.assertEqual(resultado["precio_venta_usd_kg"], Decimal("3").quantize(Decimal("0.00001")))
        self.assertEqual(resultado["precio_venta_pesos_kg"], Decimal("3000.00"))

    def test_precio_sin_descuento_es_el_catalogo_el_descuento_se_aplica_aparte(self):
        """Igual que Tubo: el precio que devuelve calcular_precio_hierro es SIN
        descuento (precio de catálogo) — el descuento del item se aplica con
        aplicar_descuento_hierro, para que el cliente lo pueda pisar en el
        carrito sin tocar el default guardado."""
        config_tipo = ConfiguracionHierro(tipo=ConfiguracionHierro.TIPO_PERFIL_UPN, incremento_general=Decimal("0.20"))
        hierro = Hierro(
            tipo=ConfiguracionHierro.TIPO_PERFIL_UPN, medida="UPN 80", costo_usd_kg=Decimal("1.5"),
            descuento_pct=Decimal("10"), descuento_habilitado=True,
        )
        resultado = calculo_precios.calcular_precio_hierro(hierro, config_tipo, cotizacion=Decimal("1000"))

        # 1.5 * 1.20 = 1.80 USD/kg -> 1800.00 $/kg, SIN descuento
        self.assertEqual(resultado["precio_venta_pesos_kg"], Decimal("1800.00"))
        # Con el 10% de descuento del item: 1800 * 0.90 = 1620.00
        self.assertEqual(resultado["precio_venta_pesos_kg_con_descuento"], Decimal("1620.00"))

    def test_descuento_deshabilitado_no_se_aplica(self):
        config_tipo = ConfiguracionHierro(tipo=ConfiguracionHierro.TIPO_PERFIL_UPN, incremento_general=Decimal("0.20"))
        hierro = Hierro(
            tipo=ConfiguracionHierro.TIPO_PERFIL_UPN, medida="UPN 80", costo_usd_kg=Decimal("1.5"),
            descuento_pct=Decimal("10"), descuento_habilitado=False,
        )
        resultado = calculo_precios.calcular_precio_hierro(hierro, config_tipo, cotizacion=Decimal("1000"))
        self.assertEqual(resultado["precio_venta_pesos_kg_con_descuento"], Decimal("1800.00"))

    def test_inactivo_no_aparece_en_la_lista(self):
        config_tipo = ConfiguracionHierro.actual(ConfiguracionHierro.TIPO_PLANCHUELA)
        Hierro.objects.create(tipo=ConfiguracionHierro.TIPO_PLANCHUELA, medida="25x3mm", costo_usd_kg=Decimal("1.5"))
        Hierro.objects.create(
            tipo=ConfiguracionHierro.TIPO_PLANCHUELA, medida="30x4mm", costo_usd_kg=Decimal("1.6"), activo=False,
        )

        precios = calculo_precios.calcular_lista_precios_hierro(
            ConfiguracionHierro.TIPO_PLANCHUELA, config_tipo, Decimal("1000"),
        )
        medidas = [p["medida"] for p in precios]
        self.assertIn("25x3mm", medidas)
        self.assertNotIn("30x4mm", medidas)

    def test_lista_de_precios_filtra_por_tipo(self):
        config_tipo = ConfiguracionHierro.actual(ConfiguracionHierro.TIPO_PLANCHUELA)
        Hierro.objects.create(tipo=ConfiguracionHierro.TIPO_PLANCHUELA, medida="25x3mm", costo_usd_kg=Decimal("1.5"))
        Hierro.objects.create(tipo=ConfiguracionHierro.TIPO_REDONDO_MACIZO, medida='1/2"', costo_usd_kg=Decimal("1.6"))

        precios = calculo_precios.calcular_lista_precios_hierro(
            ConfiguracionHierro.TIPO_PLANCHUELA, config_tipo, Decimal("1000"),
        )
        self.assertEqual(len(precios), 1)
        self.assertEqual(precios[0]["medida"], "25x3mm")


class HierroAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")

    def test_crear_y_ver_en_lista_precios(self):
        resp = self.client.post(
            "/api/hierros/", {"tipo": "PLANCHUELA", "medida": "25x3mm", "costo_usd_kg": "1.5"}, format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["activo"])

        resp = self.client.get("/api/hierros/lista-precios/", {"tipo": "PLANCHUELA"})
        self.assertEqual(resp.status_code, 200)
        fila = next(h for h in resp.data["hierros"] if h["medida"] == "25x3mm")
        self.assertIn("precio_venta_pesos_kg", fila)

    def test_lista_precios_sin_tipo_devuelve_400(self):
        resp = self.client.get("/api/hierros/lista-precios/")
        self.assertEqual(resp.status_code, 400)

    def test_listar_filtra_por_tipo(self):
        self.client.post("/api/hierros/", {"tipo": "PLANCHUELA", "medida": "25x3mm", "costo_usd_kg": "1.5"}, format="json")
        self.client.post("/api/hierros/", {"tipo": "PERFIL_IPN", "medida": "IPN 80", "costo_usd_kg": "2"}, format="json")

        resp = self.client.get("/api/hierros/", {"tipo": "PLANCHUELA"})
        medidas = [h["medida"] for h in (resp.data["results"] if "results" in resp.data else resp.data)]
        self.assertIn("25x3mm", medidas)
        self.assertNotIn("IPN 80", medidas)

    def test_patch_puede_marcarlo_inactivo(self):
        creado = self.client.post(
            "/api/hierros/", {"tipo": "CUADRADO_MACIZO", "medida": "10mm", "costo_usd_kg": "1.5"}, format="json",
        ).data
        resp = self.client.patch(f"/api/hierros/{creado['id']}/", {"activo": False}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["activo"])

    def test_patch_precio_manual_se_refleja_en_lista_precios(self):
        creado = self.client.post(
            "/api/hierros/", {"tipo": "PERFIL_UPN", "medida": "UPN 80", "costo_usd_kg": "1.5"}, format="json",
        ).data
        resp = self.client.patch(
            f"/api/hierros/{creado['id']}/",
            {"precio_venta_manual": "2500", "precio_venta_moneda": "ARS"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/api/hierros/lista-precios/", {"tipo": "PERFIL_UPN"})
        fila = next(h for h in resp.data["hierros"] if h["id"] == creado["id"])
        self.assertEqual(Decimal(str(fila["precio_venta_pesos_kg"])), Decimal("2500.00"))

    def test_patch_peso_unitario_se_refleja_en_lista_precios(self):
        creado = self.client.post(
            "/api/hierros/", {"tipo": "PERFIL_IPN", "medida": "IPN 80", "costo_usd_kg": "1.5"}, format="json",
        ).data
        resp = self.client.get("/api/hierros/lista-precios/", {"tipo": "PERFIL_IPN"})
        fila = next(h for h in resp.data["hierros"] if h["id"] == creado["id"])
        self.assertIsNone(fila["peso_unitario_kg"])
        self.assertIsNone(fila["precio_venta_pesos_unidad"])

        resp = self.client.patch(f"/api/hierros/{creado['id']}/", {"peso_unitario_kg": "6"}, format="json")
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/api/hierros/lista-precios/", {"tipo": "PERFIL_IPN"})
        fila = next(h for h in resp.data["hierros"] if h["id"] == creado["id"])
        self.assertEqual(Decimal(str(fila["peso_unitario_kg"])), Decimal("6"))
        esperado = (Decimal(str(fila["precio_venta_pesos_kg"])) * Decimal("6")).quantize(Decimal("0.01"))
        self.assertEqual(Decimal(str(fila["precio_venta_pesos_unidad"])), esperado)


class DescuentoHierroAPITests(APITestCase):
    """El % de descuento de un hierro es propio del item (igual que Tubo.
    descuento_pct/descuento_habilitado) — se edita desde el catálogo (PATCH
    /api/hierros/{id}/) y la lista de precios devuelve el precio con y sin
    ese descuento, sin depender de ningún cliente."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")
        config_tipo = ConfiguracionHierro.actual(ConfiguracionHierro.TIPO_PLANCHUELA)
        config_tipo.incremento_general = Decimal("0.20")
        config_tipo.save()
        self.hierro = Hierro.objects.create(tipo=ConfiguracionHierro.TIPO_PLANCHUELA, medida="25x3mm", costo_usd_kg=Decimal("1.5"))

    def test_nuevo_item_sin_descuento_por_defecto(self):
        resp = self.client.get("/api/hierros/lista-precios/", {"tipo": "PLANCHUELA"})
        fila = next(h for h in resp.data["hierros"] if h["id"] == self.hierro.id)
        self.assertEqual(fila["precio_venta_pesos_kg"], fila["precio_venta_pesos_kg_con_descuento"])

    def test_patch_descuento_pct_se_refleja_en_lista_precios(self):
        resp = self.client.patch(f"/api/hierros/{self.hierro.id}/", {"descuento_pct": "10"}, format="json")
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/api/hierros/lista-precios/", {"tipo": "PLANCHUELA"})
        fila = next(h for h in resp.data["hierros"] if h["id"] == self.hierro.id)
        # El 10% de descuento se aplica sobre el precio sin descuento, sea cual sea la cotización del día.
        esperado = (Decimal(str(fila["precio_venta_pesos_kg"])) * Decimal("0.9")).quantize(Decimal("0.01"))
        self.assertEqual(Decimal(str(fila["precio_venta_pesos_kg_con_descuento"])), esperado)

    def test_patch_descuento_habilitado_en_false_lo_desactiva(self):
        self.client.patch(f"/api/hierros/{self.hierro.id}/", {"descuento_pct": "10"}, format="json")
        resp = self.client.patch(f"/api/hierros/{self.hierro.id}/", {"descuento_habilitado": False}, format="json")
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/api/hierros/lista-precios/", {"tipo": "PLANCHUELA"})
        fila = next(h for h in resp.data["hierros"] if h["id"] == self.hierro.id)
        self.assertEqual(fila["precio_venta_pesos_kg"], fila["precio_venta_pesos_kg_con_descuento"])


class ConfiguracionHierroAPITests(APITestCase):
    """Config por tipo: % de incremento general propio + qué columnas se
    muestran — independiente entre tipos (cambiar Planchuela no toca Redondos)."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")
        self.client.post("/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json")

    def test_listar_crea_las_5_filas_solas(self):
        resp = self.client.get("/api/configuracion-hierro/")
        self.assertEqual(resp.status_code, 200)
        datos = resp.data["results"] if "results" in resp.data else resp.data
        tipos = {c["tipo"] for c in datos}
        self.assertEqual(
            tipos,
            {"PLANCHUELA", "REDONDO_MACIZO", "CUADRADO_MACIZO", "PERFIL_IPN", "PERFIL_UPN"},
        )

    def test_patch_incremento_de_un_tipo_no_afecta_a_otro(self):
        resp = self.client.patch("/api/configuracion-hierro/PLANCHUELA/", {"incremento_general": "0.35"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(str(resp.data["incremento_general"])), Decimal("0.35"))

        resp = self.client.get("/api/configuracion-hierro/REDONDO_MACIZO/")
        self.assertEqual(Decimal(str(resp.data["incremento_general"])), Decimal("0.20"))

    def test_patch_oculta_una_columna(self):
        resp = self.client.patch(
            "/api/configuracion-hierro/PERFIL_IPN/", {"mostrar_costo_usd_kg": False}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["mostrar_costo_usd_kg"])
        self.assertTrue(resp.data["mostrar_incremento"])

    def test_columnas_de_peso_y_venta_por_unidad_vienen_visibles_por_defecto(self):
        resp = self.client.get("/api/configuracion-hierro/PLANCHUELA/")
        self.assertTrue(resp.data["mostrar_peso_unitario"])
        self.assertTrue(resp.data["mostrar_venta_unidad"])

    def test_patch_oculta_la_columna_de_venta_por_unidad(self):
        resp = self.client.patch(
            "/api/configuracion-hierro/PLANCHUELA/", {"mostrar_venta_unidad": False}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["mostrar_venta_unidad"])
        self.assertTrue(resp.data["mostrar_peso_unitario"])

    def test_incremento_de_tipo_se_usa_al_calcular_lista_precios(self):
        self.client.patch("/api/configuracion-hierro/PLANCHUELA/", {"incremento_general": "0.5"}, format="json")
        creado = self.client.post(
            "/api/hierros/", {"tipo": "PLANCHUELA", "medida": "25x3mm", "costo_usd_kg": "2"}, format="json",
        ).data

        resp = self.client.get("/api/hierros/lista-precios/", {"tipo": "PLANCHUELA"})
        fila = next(h for h in resp.data["hierros"] if h["id"] == creado["id"])
        self.assertEqual(Decimal(str(fila["precio_venta_usd_kg"])), Decimal("3").quantize(Decimal("0.00001")))


class PresupuestoConHierroAPITests(APITestCase):
    """Un hierro se agrega a un presupuesto igual que cualquier otro ítem
    (el carrito del frontend manda tipo/descripcion/cantidad/precio ya
    calculados) — acá se verifica que el tipo 'HIERRO' sea válido, que el
    total se calcule bien, y que quede afuera de las funciones que son
    solo para chapa (extra de precio unitario, longitud)."""

    def setUp(self):
        cache.clear()
        self.usuario = get_user_model().objects.create_user(username="u1", password="x", is_staff=True)
        self.client.force_authenticate(self.usuario)
        self.cliente = Cliente.objects.create(
            numero=9100, nombre="Cliente Hierro", incremento_dd=Decimal("0"), incremento_negra=Decimal("0"),
        )

    def test_crear_presupuesto_con_item_hierro(self):
        resp = self.client.post(
            "/api/presupuestos/",
            {
                "cliente": self.cliente.id,
                "cotizacion_dolar": "1000",
                "items": [
                    {
                        "tipo": "HIERRO",
                        "descripcion": "Planchuela · 25x3mm",
                        "cantidad": "10",
                        "unidad": "kg",
                        "precio_unitario_pesos": "1500.50",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["items"][0]["tipo"], "HIERRO")
        self.assertEqual(Decimal(str(resp.data["total_pesos"])), Decimal("15005.00"))

    def test_longitud_y_extra_unitario_no_aplican_a_hierro(self):
        presupuesto = Presupuesto.objects.create(cliente=self.cliente, cotizacion_dolar=Decimal("1000"))
        item = PresupuestoItem.objects.create(
            presupuesto=presupuesto, tipo=PresupuestoItem.TIPO_HIERRO, descripcion="Planchuela · 25x3mm",
            cantidad=Decimal("10"), precio_unitario_pesos=Decimal("1500"),
        )

        resp = self.client.post(f"/api/presupuestos/{presupuesto.id}/items/{item.id}/longitud/", {"longitud_mm": 2000}, format="json")
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post(
            f"/api/presupuestos/{presupuesto.id}/items/{item.id}/agregar-ajuste-unitario/",
            {"descripcion": "Estampado", "monto_pesos": "10"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
