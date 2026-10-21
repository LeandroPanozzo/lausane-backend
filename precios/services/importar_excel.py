"""
Importador del Excel LISTA_UNIFICADA (hoja INICIO + hoja de ejemplo de un
cliente para los markups de espesor + tablas de tubos).

Qué hace:
  1. Config global: toma INICIO!C6 (base DD) y C8 (base Negra) y el
     % de incremento de tubos (fila '% Incremento', columna E, ej. 0.26).
  2. Clientes: recorre las filas de la tabla de clientes (a partir de la fila
     donde está el encabezado 'CLIENTES:'), usando columnas B (número),
     D (nombre), F (% incremento DD) y L (% incremento Negra).
  3. Markups de espesor de chapa: los toma de la PRIMERA hoja de cliente que
     encuentre (por defecto la hoja '1'), porque en el Excel original esos
     porcentajes son iguales para todos los clientes. Se leen las fórmulas
     tipo '=SUM(C16*0.07)+C16' y se extrae el 0.07 con una regex.
  4. Tubos: recorre todos los bloques que empiezan con el encabezado
     'Peso Teorico Tubo' en la columna A de la hoja INICIO, hasta la primera
     fila vacía de cada bloque.

Este parser asume que el archivo sigue el mismo layout que el Excel de
referencia. Si cambia la estructura, conviene revisar los resultados del
import (queda un resumen con todo lo que se creó/actualizó y lo que no se
pudo interpretar).
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

import openpyxl
from django.db import transaction

from precios.models import Cliente, ConfiguracionGlobal, MarkupEspesorChapa, Tubo

PORCENTAJE_RE = re.compile(r"\*\s*(0?\.\d+)\s*\)")


@dataclass
class ResultadoImportacion:
    clientes_creados: int = 0
    clientes_actualizados: int = 0
    markups_creados: int = 0
    markups_actualizados: int = 0
    tubos_creados: int = 0
    tubos_actualizados: int = 0
    advertencias: list = field(default_factory=list)

    def as_dict(self):
        return {
            "clientes_creados": self.clientes_creados,
            "clientes_actualizados": self.clientes_actualizados,
            "markups_creados": self.markups_creados,
            "markups_actualizados": self.markups_actualizados,
            "tubos_creados": self.tubos_creados,
            "tubos_actualizados": self.tubos_actualizados,
            "advertencias": self.advertencias,
        }


def _to_decimal(valor) -> Optional[Decimal]:
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = valor.strip().replace(",", ".")
        if valor == "" or valor.upper() == "XXX":
            return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None


def _extraer_porcentaje_formula(formula) -> Optional[Decimal]:
    """De '=SUM(C16*0.07)+C16' extrae Decimal('0.07'). None si es 'XXX' o vacío."""
    if formula is None:
        return None
    if not isinstance(formula, str):
        return _to_decimal(formula)
    if formula.strip().upper() == "XXX":
        return None
    match = PORCENTAJE_RE.search(formula)
    if match:
        return Decimal(match.group(1))
    return None


def importar_configuracion_global(ws_inicio, resultado: ResultadoImportacion) -> ConfiguracionGlobal:
    config = ConfiguracionGlobal.actual()
    base_dd = _to_decimal(ws_inicio["C6"].value)
    base_negra = _to_decimal(ws_inicio["C8"].value)
    if base_dd:
        config.precio_base_dd = base_dd
    if base_negra:
        config.precio_base_negra = base_negra

    # Fila '% Incremento' de la sección de tubos: columna E trae el valor
    # como fracción (0.26). Se busca dinámicamente por si cambia de fila.
    incremento_tubos = None
    for row in ws_inicio.iter_rows(min_col=1, max_col=1):
        cell = row[0]
        if cell.value == "% Incremento":
            incremento_tubos = _to_decimal(ws_inicio.cell(row=cell.row, column=5).value)
            break
    if incremento_tubos:
        config.incremento_tubos = incremento_tubos
    else:
        resultado.advertencias.append(
            "No se encontró la fila '% Incremento' de tubos; se mantiene el valor por defecto."
        )

    config.save()
    return config


def importar_clientes(ws_inicio, resultado: ResultadoImportacion) -> None:
    # Ubicar la fila de encabezado 'CLIENTES:' en columna B, los datos arrancan
    # dos filas después (hay una fila de subtítulos en el medio).
    fila_header = None
    for row in ws_inicio.iter_rows(min_col=2, max_col=2):
        if row[0].value == "CLIENTES:":
            fila_header = row[0].row
            break
    if fila_header is None:
        resultado.advertencias.append("No se encontró la fila 'CLIENTES:' en INICIO; no se importó ningún cliente.")
        return

    fila = fila_header + 1
    filas_vacias_seguidas = 0
    while filas_vacias_seguidas < 3:
        numero = ws_inicio.cell(row=fila, column=2).value  # B
        nombre = ws_inicio.cell(row=fila, column=4).value  # D
        incremento_dd = ws_inicio.cell(row=fila, column=6).value  # F
        incremento_negra = ws_inicio.cell(row=fila, column=12).value  # L

        if numero is None or not isinstance(numero, (int, float)):
            filas_vacias_seguidas += 1
            fila += 1
            continue
        filas_vacias_seguidas = 0

        nombre = (nombre or f"Cliente {int(numero)}").strip() if isinstance(nombre, str) else f"Cliente {int(numero)}"
        inc_dd = _to_decimal(incremento_dd) or Decimal("0")
        inc_negra = _to_decimal(incremento_negra) or Decimal("0")

        _, creado = Cliente.objects.update_or_create(
            numero=int(numero),
            defaults={
                "nombre": nombre,
                "incremento_dd": inc_dd,
                "incremento_negra": inc_negra,
            },
        )
        if creado:
            resultado.clientes_creados += 1
        else:
            resultado.clientes_actualizados += 1
        fila += 1


def importar_markups_espesor(ws_cliente, resultado: ResultadoImportacion) -> None:
    """
    Lee la grilla de precios en pesos de una hoja de cliente (ej. hoja '1'),
    filas 6 a 14, y extrae el % de recargo de cada celda-fórmula.

    DD: columnas C (1000mm), D (1220mm), E (1500mm) -> filas 6-14
    NEGRA: columnas H (1000mm), I (1245mm), J (1500mm) -> filas 6-14
    Los espesores están en la columna B (DD) / G (NEGRA) de esas mismas filas.
    """
    anchos_dd = {"C": "1000", "D": "1220", "E": "1500"}
    anchos_negra = {"H": "1000", "I": "1245", "J": "1500"}

    orden = 0
    for fila in range(6, 15):
        espesor_dd = ws_cliente[f"B{fila}"].value
        espesor_negra = ws_cliente[f"G{fila}"].value
        orden += 1

        if espesor_dd is not None:
            for col, ancho in anchos_dd.items():
                formula = ws_cliente[f"{col}{fila}"].value
                pct = _extraer_porcentaje_formula(formula)
                _, creado = MarkupEspesorChapa.objects.update_or_create(
                    tipo=MarkupEspesorChapa.TIPO_DD,
                    espesor=str(espesor_dd),
                    ancho_mm=ancho,
                    defaults={"porcentaje": pct, "orden": orden},
                )
                if creado:
                    resultado.markups_creados += 1
                else:
                    resultado.markups_actualizados += 1

        if espesor_negra is not None:
            for col, ancho in anchos_negra.items():
                formula = ws_cliente[f"{col}{fila}"].value
                pct = _extraer_porcentaje_formula(formula)
                _, creado = MarkupEspesorChapa.objects.update_or_create(
                    tipo=MarkupEspesorChapa.TIPO_NEGRA,
                    espesor=str(espesor_negra),
                    ancho_mm=ancho,
                    defaults={"porcentaje": pct, "orden": orden},
                )
                if creado:
                    resultado.markups_creados += 1
                else:
                    resultado.markups_actualizados += 1


def _espesor_desde_dimensiones(dimensiones: str) -> Optional[Decimal]:
    """De '30 50 0,9' intenta sacar el último número como espesor en mm."""
    if not dimensiones:
        return None
    partes = re.split(r"[x\s]+", dimensiones.strip().lower().replace("x", " "))
    partes = [p for p in partes if p]
    if not partes:
        return None
    return _to_decimal(partes[-1])


def importar_tubos(ws_inicio, resultado: ResultadoImportacion) -> None:
    orden = 0
    for row in ws_inicio.iter_rows(min_col=1, max_col=1):
        cell = row[0]
        if cell.value != "Peso Teorico Tubo":
            continue
        fila = cell.row + 1
        while True:
            peso_teorico = ws_inicio.cell(row=fila, column=1).value  # A
            costo = ws_inicio.cell(row=fila, column=2).value  # B
            dimensiones = ws_inicio.cell(row=fila, column=4).value  # D
            peso_unitario = ws_inicio.cell(row=fila, column=5).value  # E

            fila_vacia = all(
                v is None or (isinstance(v, str) and v.strip() == "")
                for v in (peso_teorico, costo, dimensiones, peso_unitario)
            )
            if fila_vacia:
                break

            costo_dec = _to_decimal(costo)
            peso_dec = _to_decimal(peso_unitario) or _to_decimal(peso_teorico)
            dimensiones_str = str(dimensiones).strip() if dimensiones else None

            if costo_dec is None or peso_dec is None or not dimensiones_str:
                resultado.advertencias.append(
                    f"Tubo en fila {fila} de INICIO ignorado por datos incompletos."
                )
                fila += 1
                continue

            orden += 1
            _, creado = Tubo.objects.update_or_create(
                dimensiones=dimensiones_str,
                defaults={
                    "espesor_mm": _espesor_desde_dimensiones(dimensiones_str),
                    "peso_unitario_kg": peso_dec,
                    "costo_usd_kg": costo_dec,
                    "orden": orden,
                },
            )
            if creado:
                resultado.tubos_creados += 1
            else:
                resultado.tubos_actualizados += 1
            fila += 1


def importar_workbook(archivo, hoja_cliente_referencia: str = "1") -> ResultadoImportacion:
    """
    Punto de entrada principal. `archivo` puede ser una ruta o un file-like
    (ej. request.FILES['archivo'] en la vista de upload).
    """
    resultado = ResultadoImportacion()
    wb = openpyxl.load_workbook(archivo, data_only=False)

    if "INICIO" not in wb.sheetnames:
        raise ValueError("El archivo no tiene una hoja 'INICIO'; no coincide con el formato esperado.")
    ws_inicio = wb["INICIO"]

    # Todo el import es una sola transacción: si algo falla a mitad de camino
    # (fila con datos corruptos, excepción inesperada, etc.) se revierte
    # completo en vez de dejar la base con una mezcla de datos viejos y nuevos.
    with transaction.atomic():
        importar_configuracion_global(ws_inicio, resultado)
        importar_clientes(ws_inicio, resultado)
        importar_tubos(ws_inicio, resultado)

        if hoja_cliente_referencia in wb.sheetnames:
            importar_markups_espesor(wb[hoja_cliente_referencia], resultado)
        else:
            resultado.advertencias.append(
                f"No se encontró la hoja de referencia '{hoja_cliente_referencia}' para los markups de espesor."
            )

    return resultado
