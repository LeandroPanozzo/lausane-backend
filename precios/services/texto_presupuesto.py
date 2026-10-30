"""
Limpieza del texto de la descripción de un ítem de presupuesto para
mostrarla (API, PDF, Excel), sin tocar lo que está guardado en la base —
así los presupuestos ya creados antes de estos cambios también se ven
actualizados.
"""
import re

_RE_SUFIJO_DESCUENTO = re.compile(r"\s*\(desc\.?\s*[\d.,]+\s*%\)\s*$", re.IGNORECASE)


def limpiar_descripcion_item(descripcion: str) -> str:
    """
    - Saca el "(desc. X%)" interno que antes se guardaba en los ítems de tubo
      (el cliente no tiene por qué ver el % de descuento interno).
    - Renombra "Chapa DD"/"Chapa Negra" (nombre comercial viejo) a "Chapa
      Laminado en Frío"/"Chapa Laminado en Caliente" (nombre actual).
    """
    descripcion = _RE_SUFIJO_DESCUENTO.sub("", descripcion)
    descripcion = re.sub(r"^Chapa DD\b", "Chapa Laminado en Frío", descripcion)
    descripcion = re.sub(r"^Chapa Negra\b", "Chapa Laminado en Caliente", descripcion)
    return descripcion


def descripcion_item_con_ajustes(item) -> str:
    """Agrega junto a la descripción los extras que forman parte del precio unitario."""
    descripcion = limpiar_descripcion_item(item.descripcion)
    etiquetas = [ajuste.descripcion or "Extra" for ajuste in item.ajustes_unitarios.all()]
    if etiquetas:
        descripcion = f"{descripcion} ({', '.join(etiquetas)})"
    return descripcion
