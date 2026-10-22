from unittest.mock import patch, MagicMock

from django.core.mail import EmailMessage
from django.test import TestCase, override_settings

from precios.services.sendgrid_backend import SendGridBackend


@override_settings(SENDGRID_API_KEY="clave-de-prueba")
class SendGridBackendTests(TestCase):
    """El backend manda por la API HTTP de SendGrid (no SMTP) porque
    DigitalOcean bloquea los puertos SMTP de salida por política."""

    def _mensaje(self, con_adjunto=False):
        mensaje = EmailMessage(
            subject="Asunto de prueba",
            body="Cuerpo de prueba",
            from_email="remitente@lausane.com.ar",
            to=["cliente@example.com"],
        )
        if con_adjunto:
            mensaje.attach("presupuesto.pdf", b"contenido-pdf", "application/pdf")
        return mensaje

    @patch("precios.services.sendgrid_backend.requests.post")
    def test_manda_un_post_a_la_api_de_sendgrid_con_bearer_token(self, mock_post):
        mock_post.return_value = MagicMock(status_code=202, raise_for_status=lambda: None)

        enviados = SendGridBackend().send_messages([self._mensaje()])

        self.assertEqual(enviados, 1)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer clave-de-prueba")
        self.assertEqual(kwargs["json"]["from"], {"email": "remitente@lausane.com.ar"})
        self.assertEqual(kwargs["json"]["personalizations"][0]["to"], [{"email": "cliente@example.com"}])
        self.assertEqual(kwargs["json"]["subject"], "Asunto de prueba")

    @patch("precios.services.sendgrid_backend.requests.post")
    def test_separa_nombre_y_email_cuando_el_remitente_tiene_display_name(self, mock_post):
        mock_post.return_value = MagicMock(status_code=202, raise_for_status=lambda: None)
        mensaje = EmailMessage(
            subject="Asunto", body="Cuerpo",
            from_email='"Lausane S.A.C." <lausane.ventas1@gmail.com>',
            to=["cliente@example.com"],
        )

        SendGridBackend().send_messages([mensaje])

        _, kwargs = mock_post.call_args
        self.assertEqual(
            kwargs["json"]["from"], {"email": "lausane.ventas1@gmail.com", "name": "Lausane S.A.C."},
        )

    @patch("precios.services.sendgrid_backend.requests.post")
    def test_adjunta_el_pdf_codificado_en_base64(self, mock_post):
        mock_post.return_value = MagicMock(status_code=202, raise_for_status=lambda: None)

        SendGridBackend().send_messages([self._mensaje(con_adjunto=True)])

        _, kwargs = mock_post.call_args
        adjunto = kwargs["json"]["attachments"][0]
        self.assertEqual(adjunto["filename"], "presupuesto.pdf")
        self.assertEqual(adjunto["type"], "application/pdf")
        import base64
        self.assertEqual(base64.b64decode(adjunto["content"]), b"contenido-pdf")

    @override_settings(SENDGRID_API_KEY="")
    def test_sin_api_key_configurada_tira_error(self):
        with self.assertRaises(ValueError):
            SendGridBackend().send_messages([self._mensaje()])

    @override_settings(SENDGRID_API_KEY="")
    def test_sin_api_key_y_fail_silently_no_tira_error(self):
        enviados = SendGridBackend(fail_silently=True).send_messages([self._mensaje()])
        self.assertEqual(enviados, 0)

    @patch("precios.services.sendgrid_backend.requests.post")
    def test_si_sendgrid_responde_error_y_no_es_fail_silently_propaga_la_excepcion(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("boom")

        with self.assertRaises(requests.RequestException):
            SendGridBackend().send_messages([self._mensaje()])

    def test_sin_mensajes_no_hace_nada(self):
        enviados = SendGridBackend().send_messages([])
        self.assertEqual(enviados, 0)
