from django.core import mail
from rest_framework.test import APITestCase


class ContactoPublicoTests(APITestCase):
    """Formulario de contacto del sitio público: sin auth, manda un email."""

    def test_envia_email_con_los_datos_del_formulario(self):
        resp = self.client.post(
            "/api/contacto/",
            {
                "nombre": "Juan Pérez",
                "email": "juan@example.com",
                "telefono": "1122334455",
                "asunto": "Consulta por chapa DD",
                "mensaje": "Necesito precio de chapa 1000x1.6mm.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        enviado = mail.outbox[0]
        self.assertIn("Juan Pérez", enviado.body)
        self.assertIn("Necesito precio", enviado.body)
        self.assertEqual(enviado.reply_to, ["juan@example.com"])

    def test_requiere_nombre_email_y_mensaje(self):
        resp = self.client.post("/api/contacto/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("nombre", resp.data)
        self.assertIn("email", resp.data)
        self.assertIn("mensaje", resp.data)
