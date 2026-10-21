"""
URL configuration for config project (Lista de Precios — chapa y tubo).
"""
from django.contrib import admin
from django.urls import include, path
from precios.auth_views import (
    CookieTokenObtainPairView, CookieTokenRefreshView, LogoutView,
    SolicitarResetPasswordView, ConfirmarResetPasswordView,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth JWT (tokens en cookies httpOnly, ver precios/auth.py)
    path('api/auth/token/', CookieTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/logout/', LogoutView.as_view(), name='logout'),
    path('api/auth/password-reset/', SolicitarResetPasswordView.as_view(), name='password_reset'),
    path('api/auth/password-reset/confirmar/', ConfirmarResetPasswordView.as_view(), name='password_reset_confirm'),

    # API de la app
    path('api/', include('precios.urls')),
]
