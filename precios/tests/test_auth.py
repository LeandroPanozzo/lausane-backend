from django.contrib.auth import get_user_model
from django.core.cache import cache
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
