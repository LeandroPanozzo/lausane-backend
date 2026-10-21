"""Envío del presupuesto por email, con el PDF adjunto."""

from django.core.mail import EmailMessage

from precios.models import Presupuesto
from precios.services.email_config import obtener_conexion_email, obtener_remitente
from precios.services.pdf_presupuesto import generar_pdf_presupuesto


def enviar_presupuesto_por_email(presupuesto: Presupuesto, destinatario: str, mensaje: str = "") -> None:
    asunto = f"Presupuesto Lausane N° {presupuesto.codigo}"
    cuerpo = mensaje.strip() or (
        f"Hola {presupuesto.cliente.nombre},\n\n"
        f"Adjuntamos el presupuesto N° {presupuesto.codigo} solicitado.\n\n"
        f"Total: $ {presupuesto.total_pesos:,.2f}\n\n"
        f"Ante cualquier consulta, quedamos a disposición.\n\n"
        f"Saludos,\nLausane S.A.C."
    )

    email = EmailMessage(
        subject=asunto,
        body=cuerpo,
        from_email=obtener_remitente(),
        to=[destinatario],
        connection=obtener_conexion_email(),
    )
    pdf_bytes = generar_pdf_presupuesto(presupuesto)
    email.attach(f"presupuesto_lausane_{presupuesto.numero}.pdf", pdf_bytes, "application/pdf")
    email.send(fail_silently=False)
