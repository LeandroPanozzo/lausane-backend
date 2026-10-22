from django.contrib import admin

from .models import (
    ChapaGalvanizada, ChapaGruesa, Cliente, ConfiguracionGlobal, CotizacionDolar, MarkupEspesorChapa, Tubo,
    Presupuesto, PresupuestoItem,
)


@admin.register(ConfiguracionGlobal)
class ConfiguracionGlobalAdmin(admin.ModelAdmin):
    list_display = ("precio_base_dd", "precio_base_negra", "incremento_tubos", "actualizado")

    def has_add_permission(self, request):
        # Es un singleton: no se crean instancias nuevas desde el admin.
        return not ConfiguracionGlobal.objects.exists()


@admin.register(CotizacionDolar)
class CotizacionDolarAdmin(admin.ModelAdmin):
    list_display = ("fecha", "compra", "venta", "fuente")
    list_filter = ("fuente",)
    ordering = ("-fecha",)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("numero", "nombre", "email", "telefono", "incremento_dd", "incremento_negra", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "numero")
    ordering = ("numero",)


class PresupuestoItemInline(admin.TabularInline):
    model = PresupuestoItem
    extra = 0


@admin.register(Presupuesto)
class PresupuestoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "cliente", "estado", "total_pesos", "creado")
    list_filter = ("estado",)
    search_fields = ("numero", "cliente__nombre")
    inlines = [PresupuestoItemInline]
    readonly_fields = ("numero", "token_publico", "creado", "actualizado")


@admin.register(MarkupEspesorChapa)
class MarkupEspesorChapaAdmin(admin.ModelAdmin):
    list_display = ("tipo", "espesor", "ancho_mm", "porcentaje", "orden")
    list_filter = ("tipo",)
    ordering = ("tipo", "orden")


@admin.register(Tubo)
class TuboAdmin(admin.ModelAdmin):
    list_display = ("dimensiones", "espesor_mm", "peso_unitario_kg", "costo_usd_kg", "activo")
    list_filter = ("activo",)
    search_fields = ("dimensiones",)
    ordering = ("orden",)


@admin.register(ChapaGalvanizada)
class ChapaGalvanizadaAdmin(admin.ModelAdmin):
    list_display = ("espesor", "ancho_mm", "costo_usd_kg", "activo")
    list_filter = ("activo",)
    search_fields = ("espesor", "ancho_mm")
    ordering = ("orden", "espesor")


@admin.register(ChapaGruesa)
class ChapaGruesaAdmin(admin.ModelAdmin):
    list_display = ("espesor", "ancho_mm", "costo_usd_kg", "activo")
    list_filter = ("activo",)
    search_fields = ("espesor", "ancho_mm")
    ordering = ("orden", "espesor")
