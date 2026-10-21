from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"clientes", views.ClienteViewSet, basename="cliente")
router.register(r"markups-chapa", views.MarkupEspesorChapaViewSet, basename="markup-chapa")
router.register(r"tubos", views.TuboViewSet, basename="tubo")
router.register(r"galvanizada", views.ChapaGalvanizadaViewSet, basename="galvanizada")
router.register(r"presupuestos", views.PresupuestoViewSet, basename="presupuesto")

urlpatterns = [
    # Rutas públicas primero, para que no choquen con el router de "presupuestos/<pk>/"
    path(
        "presupuestos-publico/<uuid:token>/pdf/",
        views.PresupuestoPublicoPDFView.as_view(),
        name="presupuesto-publico-pdf",
    ),
    path("contacto/", views.ContactoPublicoView.as_view(), name="contacto-publico"),

    path("", include(router.urls)),
    path("configuracion/", views.ConfiguracionGlobalView.as_view(), name="configuracion-global"),
    path("dolar/actual/", views.CotizacionDolarView.as_view(), name="dolar-actual"),
    path("dolar/manual/", views.CotizacionDolarManualView.as_view(), name="dolar-manual"),
    path("dolar/volver-oficial/", views.CotizacionDolarVolverOficialView.as_view(), name="dolar-volver-oficial"),
]
