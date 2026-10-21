from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase


class CookieAuthTests(APITestCase):
    """El login/refresh/logout dejan el JWT en cookies httpOnly en vez de
    devolverlo en el body (ver precios/auth.py y precios/auth_views.py) para
    que un XSS en el frontend no pueda robar el token leyéndolo con JS."""

    def setUp(self):
        # El throttle de login (scope "login") usa el cache de Django, que no
        # se resetea solo entre tests — sin este clear(), correr toda la
        # suite junta puede acumular logins de otros archivos de test y
        # terminar bloqueando estos con un 429 (falso negativo).
        cache.clear()
        self.user = get_user_model().objects.create_user(username="tester", password="Sup3rSecret!42")

    def _login(self):
        return self.client.post(
            "/api/auth/token/", {"username": "tester", "password": "Sup3rSecret!42"}, format="json",
        )

    def test_login_no_expone_los_tokens_en_el_body(self):
        resp = self._login()
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("access", resp.data)
        self.assertNotIn("refresh", resp.data)
        self.assertEqual(resp.data["username"], "tester")

    def test_login_deja_cookies_httponly(self):
        resp = self._login()
        self.assertTrue(resp.cookies["access_token"]["httponly"])
        self.assertTrue(resp.cookies["refresh_token"]["httponly"])

    def test_endpoint_protegido_sin_cookie_devuelve_401(self):
        resp = self.client.get("/api/clientes/")
        self.assertEqual(resp.status_code, 401)

    def test_cookie_de_login_autentica_el_siguiente_request(self):
        self._login()
        resp = self.client.get("/api/clientes/")
        self.assertEqual(resp.status_code, 200)

    def test_refresh_rota_el_access_token(self):
        self._login()
        resp = self.client.post("/api/auth/token/refresh/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access_token", resp.cookies)

    def test_refresh_sin_cookie_devuelve_401(self):
        resp = self.client.post("/api/auth/token/refresh/")
        self.assertEqual(resp.status_code, 401)

    def test_logout_deja_de_autenticar(self):
        self._login()
        self.client.post("/api/auth/logout/")
        resp = self.client.get("/api/clientes/")
        self.assertEqual(resp.status_code, 401)


class PasswordResetTests(APITestCase):
    """Recuperar contraseña: mismo mensaje exista o no el usuario (no revela
    qué usuarios existen), manda el mail solo si hay un email cargado, y el
    link solo sirve una vez y con el usuario correcto."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="tester", password="Sup3rSecret!42", email="tester@example.com",
        )

    def _uid_token(self, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return uid, token

    def test_solicitar_con_usuario_existente_manda_el_mail(self):
        resp = self.client.post("/api/auth/password-reset/", {"username": "tester"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["tester@example.com"])
        self.assertIn("/reset-password/", mail.outbox[0].body)

    def test_solicitar_con_usuario_inexistente_responde_igual_pero_no_manda_mail(self):
        resp = self.client.post("/api/auth/password-reset/", {"username": "no-existe"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_solicitar_con_usuario_sin_email_no_manda_mail(self):
        get_user_model().objects.create_user(username="sinmail", password="Sup3rSecret!42")
        resp = self.client.post("/api/auth/password-reset/", {"username": "sinmail"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_confirmar_con_token_valido_cambia_la_contrasena(self):
        uid, token = self._uid_token(self.user)
        resp = self.client.post(
            "/api/auth/password-reset/confirmar/",
            {"uid": uid, "token": token, "password": "NuevaClaveSegura123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

        login = self.client.post(
            "/api/auth/token/", {"username": "tester", "password": "NuevaClaveSegura123"}, format="json",
        )
        self.assertEqual(login.status_code, 200)

    def test_confirmar_con_token_invalido_falla(self):
        uid, _ = self._uid_token(self.user)
        resp = self.client.post(
            "/api/auth/password-reset/confirmar/",
            {"uid": uid, "token": "token-trucho", "password": "NuevaClaveSegura123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_confirmar_con_token_ya_usado_falla_la_segunda_vez(self):
        uid, token = self._uid_token(self.user)
        primera = self.client.post(
            "/api/auth/password-reset/confirmar/",
            {"uid": uid, "token": token, "password": "NuevaClaveSegura123"},
            format="json",
        )
        self.assertEqual(primera.status_code, 200)

        segunda = self.client.post(
            "/api/auth/password-reset/confirmar/",
            {"uid": uid, "token": token, "password": "OtraClaveMas456"},
            format="json",
        )
        self.assertEqual(segunda.status_code, 400)
