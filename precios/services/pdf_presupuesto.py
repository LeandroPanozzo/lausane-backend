"""
Genera el PDF de un presupuesto, con la identidad visual de Lausane S.A.C.
(rojo/blanco). Se usa tanto para la descarga directa como para adjuntar en
el envío por email.
"""

from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

from precios.models import Presupuesto
from precios.services.texto_presupuesto import limpiar_descripcion_item

ROJO_LAUSANE = colors.HexColor("#E30613")
GRIS_TEXTO = colors.HexColor("#2b2b2b")
GRIS_CLARO = colors.HexColor("#f4f4f5")
GRIS_BORDE = colors.HexColor("#dcdcdc")

LOGO_PATH = Path(__file__).resolve().parent.parent / "static" / "precios" / "img" / "logo-lausane.png"


def _formato_pesos(valor: Decimal) -> str:
    texto = f"{valor:,.2f}"
    # de formato en-US (1,234.56) a formato es-AR (1.234,56)
    texto = texto.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"$ {texto}"


def _formato_porcentaje(valor: Decimal) -> str:
    """10.5 -> '10,5%' ; 21 -> '21%' (sin ',0' de más)."""
    texto = f"{valor.normalize():f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return f"{texto.replace('.', ',')}%"


def _formato_cantidad(valor: Decimal) -> str:
    """Evita que '500' se muestre como '500.000' por el decimal_places del campo."""
    texto = f"{valor:f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto


def generar_pdf_presupuesto(presupuesto: Presupuesto) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
    )
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        "TituloPresupuesto", parent=styles["Heading1"], fontSize=20, textColor=ROJO_LAUSANE,
        spaceAfter=2, fontName="Helvetica-Bold",
    )
    sub_style = ParagraphStyle(
        "SubPresupuesto", parent=styles["Normal"], fontSize=10, textColor=GRIS_TEXTO, spaceAfter=0,
    )
    cliente_style = ParagraphStyle(
        "Cliente", parent=styles["Normal"], fontSize=11, textColor=GRIS_TEXTO, leading=15,
    )
    nota_style = ParagraphStyle(
        "Nota", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#666666"),
    )

    elementos = []

    # --- Encabezado: logo + título del presupuesto ---
    if LOGO_PATH.exists():
        logo = Image(str(LOGO_PATH), width=42 * mm, height=11 * mm)
    else:
        logo = Paragraph("LAUSANE", titulo_style)

    encabezado = Table(
        [[logo, Paragraph(f"Presupuesto Lausane<br/>N° {presupuesto.codigo}", titulo_style)]],
        colWidths=[70 * mm, None],
    )
    encabezado.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    elementos.append(encabezado)
    elementos.append(Spacer(1, 4 * mm))
    elementos.append(HRFlowable(width="100%", thickness=1.4, color=ROJO_LAUSANE))
    elementos.append(Spacer(1, 6 * mm))

    # --- Datos del cliente y del presupuesto ---
    fecha_local = timezone.localtime(presupuesto.creado).strftime("%d/%m/%Y")
    datos = Table(
        [
            [
                Paragraph(f"<b>Cliente:</b> {presupuesto.cliente.nombre}", cliente_style),
                Paragraph(f"<b>Fecha:</b> {fecha_local}", cliente_style),
            ]
        ],
        colWidths=[None, None],
    )
    datos.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elementos.append(datos)
    elementos.append(Spacer(1, 8 * mm))

    # --- Tabla de ítems ---
    extra_style = ParagraphStyle(
        "ExtraItem", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#666666"),
        leftIndent=10, fontName="Helvetica-Oblique",
    )
    encabezados = ["Descripción", "Cantidad", "Unidad", "Precio unit.", "Subtotal"]
    filas = [encabezados]
    for item in presupuesto.items.all():
        filas.append([
            Paragraph(limpiar_descripcion_item(item.descripcion), styles["Normal"]),
            _formato_cantidad(item.cantidad),
            item.unidad,
            _formato_pesos(item.precio_unitario_pesos),
            _formato_pesos(item.subtotal_pesos),
        ])
        for ajuste in item.ajustes_unitarios.all():
            etiqueta = ajuste.descripcion or "Ajuste"
            filas.append([
                Paragraph(f"+ {etiqueta} (por unidad)", extra_style),
                "", "",
                _formato_pesos(ajuste.monto_pesos),
                "",
            ])
        for extra in item.extras.all():
            filas.append([
                Paragraph(f"+ {extra.descripcion}", extra_style),
                "", "", "",
                _formato_pesos(extra.precio_pesos),
            ])

    tabla = Table(filas, colWidths=[80 * mm, 22 * mm, 22 * mm, 30 * mm, 30 * mm], repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ROJO_LAUSANE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_CLARO]),
        ("GRID", (0, 0), (-1, -1), 0.4, GRIS_BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elementos.append(tabla)
    elementos.append(Spacer(1, 6 * mm))

    # --- Neto / Impuestos / Total ---
    total_style = ParagraphStyle(
        "Total", parent=styles["Heading2"], alignment=TA_RIGHT, textColor=ROJO_LAUSANE, fontSize=15,
    )
    mas_impuestos_style = ParagraphStyle(
        "MasImpuestos", parent=styles["Heading2"], alignment=TA_RIGHT, textColor=ROJO_LAUSANE,
        fontSize=14, spaceBefore=2,
    )

    neto = presupuesto.total_pesos
    if presupuesto.impuesto_pct is not None:
        monto_impuestos = (neto * presupuesto.impuesto_pct / Decimal("100")).quantize(Decimal("0.01"))
        elementos.append(Paragraph(f"Neto: {_formato_pesos(neto)}", total_style))
        elementos.append(
            Paragraph(
                f"{_formato_porcentaje(presupuesto.impuesto_pct)} de IVA: {_formato_pesos(monto_impuestos)}",
                mas_impuestos_style,
            )
        )
        elementos.append(Paragraph(f"Total: {_formato_pesos(neto + monto_impuestos)}", total_style))
        elementos.append(Paragraph("+Impuestos varios", mas_impuestos_style))
    else:
        elementos.append(Paragraph(f"Total: {_formato_pesos(neto)}", total_style))
    elementos.append(Spacer(1, 10 * mm))

    if presupuesto.notas:
        elementos.append(Paragraph(f"<b>Notas:</b> {presupuesto.notas}", nota_style))
        elementos.append(Spacer(1, 6 * mm))

    elementos.append(HRFlowable(width="100%", thickness=0.6, color=GRIS_BORDE))
    elementos.append(Spacer(1, 3 * mm))
    pie_style = ParagraphStyle("Pie", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#888888"), alignment=TA_CENTER)
    elementos.append(Paragraph(
        "Presupuesto válido por 24 horas. Precios sujetos a variación de la cotización del dólar. — LAUSANE S.A.C.",
        pie_style,
    ))

    doc.build(elementos)
    return buffer.getvalue()
