"""
Lógica de cálculo de precios — réplica fiel de las fórmulas de la hoja INICIO
y de las hojas por cliente del Excel LISTA_UNIFICADA.

Referencia de fórmulas originales (hoja INICIO, ejemplo cliente fila 14):
    H14 (Coeficiente)   = PRODUCT(F14, G14)      -> % incremento * 0.01
    I14 (Resultado)     = PRODUCT(H14, C6)       -> coeficiente * precio base
    J14 (Base U$S)      = SUM(C6, I14)           -> precio base + resultado
    K14 (Base $)        = PRODUCT(J8, J14)       -> base U$S * cotización dólar

Y en la hoja de cada cliente (ej. hoja "1"):
    C6 (precio por espesor) = SUM(C16*0.07) + C16   -> base * (1 + %) por espesor
"""

from decimal import Decimal
from typing import Optional

from precios.models import Cliente, ChapaGalvanizada, ChapaGruesa, ConfiguracionGlobal, MarkupEspesorChapa, Tubo


def coeficiente(incremento_pct: Decimal) -> Decimal:
    """Excel: H = PRODUCT(F, G) con G siempre 0.01 -> % / 100."""
    return incremento_pct / Decimal("100")


def calcular_base_chapa(incremento_pct: Decimal, precio_base: Decimal, cotizacion: Decimal) -> dict:
    """
    Reproduce las columnas H..K (o N..Q) de la hoja INICIO para un cliente y tipo
    de chapa (DD o Negra) dados.
    """
    coef = coeficiente(incremento_pct)
    resultado = coef * precio_base
    base_usd = precio_base + resultado
    base_pesos = base_usd * cotizacion
    return {
        "coeficiente": coef,
        "resultado": resultado,
        "base_usd": base_usd,
        "base_pesos": base_pesos,
    }


def calcular_precio_base_cliente(cliente: Cliente, config: ConfiguracionGlobal, cotizacion: Decimal, tipo: str) -> dict:
    """tipo: 'DD' o 'NEGRA'."""
    if tipo == MarkupEspesorChapa.TIPO_DD:
        incremento = cliente.incremento_dd
        precio_base = config.precio_base_dd
    else:
        incremento = cliente.incremento_negra
        precio_base = config.precio_base_negra
    return calcular_base_chapa(incremento, precio_base, cotizacion)


def calcular_lista_precios_chapa(cliente: Cliente, config: ConfiguracionGlobal, cotizacion: Decimal) -> dict:
    """
    Arma la lista de precios completa de un cliente para chapa DD y Negra,
    abierta por espesor/ancho — equivalente a la hoja individual del cliente
    en el Excel (ej. hoja "1").

    Además del % de incremento (que define la BASE compartida), cada cliente
    puede tener su propio % de descuento para DD y para Negra (Cliente.
    descuento_dd / descuento_negra) — se aplica sobre el precio final de cada
    espesor, no sobre la base, así "Base" sigue siendo la réplica fiel del
    Excel y el descuento es un recorte aparte, propio de este cliente.
    """
    resultado = {}
    for tipo, _ in MarkupEspesorChapa.TIPO_CHOICES:
        base = calcular_precio_base_cliente(cliente, config, cotizacion, tipo)
        descuento_pct = cliente.descuento_dd if tipo == MarkupEspesorChapa.TIPO_DD else cliente.descuento_negra
        factor_descuento = Decimal("1") - (descuento_pct / Decimal("100"))
        precios_por_espesor = []
        markups = MarkupEspesorChapa.objects.filter(tipo=tipo, activo=True).order_by("orden", "espesor")
        for m in markups:
            if m.porcentaje is None:
                precios_por_espesor.append({
                    "espesor": m.espesor,
                    "ancho_mm": m.ancho_mm,
                    "porcentaje": None,
                    "precio_usd": None,
                    "precio_pesos": None,
                    "disponible": False,
                })
                continue
            factor = Decimal("1") + m.porcentaje
            precios_por_espesor.append({
                "espesor": m.espesor,
                "ancho_mm": m.ancho_mm,
                "porcentaje": m.porcentaje,
                "precio_usd": (base["base_usd"] * factor * factor_descuento).quantize(Decimal("0.0001")),
                "precio_pesos": (base["base_pesos"] * factor * factor_descuento).quantize(Decimal("0.01")),
                "disponible": True,
            })
        resultado[tipo] = {
            "base": {k: v.quantize(Decimal("0.00001")) for k, v in base.items()},
            "descuento_pct": descuento_pct,
            "precios_por_espesor": precios_por_espesor,
        }
    return resultado


def calcular_precio_tubo(tubo: Tubo, config: ConfiguracionGlobal, cotizacion: Decimal) -> dict:
    """
    Reproduce la tabla 'Peso Teorico Tubo' de INICIO:
        precio_venta_usd_kg  = costo_usd_kg * (1 + incremento_tubos)
        precio_venta_usd_tubo = precio_venta_usd_kg * peso_unitario_kg
        precio_venta_pesos    = precio_venta_usd_tubo * cotizacion

    El descuento (por tubo, editable) es informativo acá — el precio final
    con descuento ya aplicado se calcula con `aplicar_descuento_tubo`, porque
    al armar el carrito de un cliente ese % se puede pisar puntualmente sin
    tocar el default del catálogo.
    """
    incremento = config.incremento_tubos
    precio_usd_kg = tubo.precio_venta_usd_kg(incremento)
    precio_usd_tubo = tubo.precio_venta_usd_tubo(incremento)
    precio_pesos_tubo = tubo.precio_venta_pesos_tubo(incremento, cotizacion).quantize(Decimal("0.01"))
    return {
        "id": tubo.id,
        "dimensiones": tubo.dimensiones,
        "espesor_mm": tubo.espesor_mm,
        "peso_unitario_kg": tubo.peso_unitario_kg,
        "costo_usd_kg": tubo.costo_usd_kg,
        "incremento_aplicado": incremento,
        "precio_venta_usd_kg": precio_usd_kg.quantize(Decimal("0.00001")),
        "precio_venta_usd_tubo": precio_usd_tubo.quantize(Decimal("0.00001")),
        "precio_venta_pesos_tubo": precio_pesos_tubo,
        "descuento_pct": tubo.descuento_pct,
        "descuento_habilitado": tubo.descuento_habilitado,
        "precio_venta_pesos_tubo_con_descuento": aplicar_descuento_tubo(
            precio_pesos_tubo, tubo.descuento_pct, tubo.descuento_habilitado
        ),
    }


def aplicar_descuento_tubo(precio_pesos_tubo: Decimal, descuento_pct: Decimal, descuento_habilitado: bool) -> Decimal:
    """Precio final de un tubo aplicando (o no) su % de descuento."""
    if not descuento_habilitado:
        return precio_pesos_tubo.quantize(Decimal("0.01"))
    factor = Decimal("1") - (descuento_pct / Decimal("100"))
    return (precio_pesos_tubo * factor).quantize(Decimal("0.01"))


def calcular_lista_precios_tubos(config: ConfiguracionGlobal, cotizacion: Decimal, queryset: Optional[list] = None) -> list:
    tubos = queryset if queryset is not None else Tubo.objects.filter(activo=True)
    return [calcular_precio_tubo(t, config, cotizacion) for t in tubos]


def calcular_precio_galvanizada(chapa: ChapaGalvanizada, config: ConfiguracionGlobal, cotizacion: Decimal) -> dict:
    """
    Chapa galvanizada: a diferencia de DD/Negra, cada espesor/ancho tiene su
    propio costo en U$S/kg (no un % sobre una base compartida) — mismo
    esquema que Tubo, aplicando incremento_galvanizada en vez de
    incremento_tubos.
        precio_venta_usd_kg = costo_usd_kg * (1 + incremento_galvanizada)
        precio_venta_pesos_kg = precio_venta_usd_kg * cotizacion

    Si `usar_incremento_general` está destildado para esta chapa puntual, no
    se le aplica el incremento — se vende directo al costo.
    """
    incremento = config.incremento_galvanizada if chapa.usar_incremento_general else Decimal("0")
    precio_usd_kg = chapa.costo_usd_kg * (Decimal("1") + incremento)
    precio_pesos_kg = precio_usd_kg * cotizacion
    return {
        "id": chapa.id,
        "espesor": chapa.espesor,
        "ancho_mm": chapa.ancho_mm,
        "costo_usd_kg": chapa.costo_usd_kg,
        "usar_incremento_general": chapa.usar_incremento_general,
        "incremento_aplicado": incremento,
        "precio_venta_usd_kg": precio_usd_kg.quantize(Decimal("0.00001")),
        "precio_venta_pesos_kg": precio_pesos_kg.quantize(Decimal("0.01")),
    }


def calcular_lista_precios_galvanizada(
    config: ConfiguracionGlobal, cotizacion: Decimal, queryset: Optional[list] = None
) -> list:
    chapas = queryset if queryset is not None else ChapaGalvanizada.objects.filter(activo=True)
    return [calcular_precio_galvanizada(c, config, cotizacion) for c in chapas]


def calcular_precio_gruesa(chapa: ChapaGruesa, config: ConfiguracionGlobal, cotizacion: Decimal) -> dict:
    """Chapa gruesa: mismo esquema que galvanizada (costo propio en U$S/kg +
    incremento_gruesas, en vez de un % sobre una base compartida)."""
    incremento = config.incremento_gruesas if chapa.usar_incremento_general else Decimal("0")
    precio_usd_kg = chapa.costo_usd_kg * (Decimal("1") + incremento)
    precio_pesos_kg = precio_usd_kg * cotizacion
    return {
        "id": chapa.id,
        "espesor": chapa.espesor,
        "ancho_mm": chapa.ancho_mm,
        "costo_usd_kg": chapa.costo_usd_kg,
        "usar_incremento_general": chapa.usar_incremento_general,
        "incremento_aplicado": incremento,
        "precio_venta_usd_kg": precio_usd_kg.quantize(Decimal("0.00001")),
        "precio_venta_pesos_kg": precio_pesos_kg.quantize(Decimal("0.01")),
    }


def calcular_lista_precios_gruesa(
    config: ConfiguracionGlobal, cotizacion: Decimal, queryset: Optional[list] = None
) -> list:
    chapas = queryset if queryset is not None else ChapaGruesa.objects.filter(activo=True)
    return [calcular_precio_gruesa(c, config, cotizacion) for c in chapas]
