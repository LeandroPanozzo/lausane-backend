from django.conf import settings
from django.db import models
from rest_framework import serializers

from .models import (
    Cliente, ChapaGalvanizada, ChapaGruesa, ConfiguracionGlobal, CotizacionDolar, MarkupEspesorChapa, Tubo,
    Presupuesto, PresupuestoItem, PresupuestoItemExtra,
)


class ConfiguracionGlobalSerializer(serializers.ModelSerializer):
    # La contraseña nunca se devuelve en un GET — solo se acepta para
    # guardarla. Si no mandan nada (o mandan vacío), no se toca la que ya
    # estaba guardada (ver update()).
    email_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    email_password_configurada = serializers.SerializerMethodField()
    email_remitente_por_defecto = serializers.SerializerMethodField()
    email_configurado_por_defecto = serializers.SerializerMethodField()

    class Meta:
        model = ConfiguracionGlobal
        fields = [
            "precio_base_dd", "precio_base_negra", "incremento_tubos", "incremento_galvanizada",
            "incremento_gruesas",
            "email_remitente", "email_password", "email_password_configurada",
            "email_remitente_por_defecto", "email_configurado_por_defecto", "actualizado",
        ]

    def get_email_password_configurada(self, obj):
        return bool(obj.email_password)

    def get_email_remitente_por_defecto(self, obj):
        return settings.EMAIL_HOST_USER or ""

    def get_email_configurado_por_defecto(self, obj):
        return bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)

    def update(self, instance, validated_data):
        password = validated_data.pop("email_password", None)
        instance = super().update(instance, validated_data)
        if password:
            instance.email_password = password
            instance.save(update_fields=["email_password"])
        return instance


class CotizacionDolarSerializer(serializers.ModelSerializer):
    class Meta:
        model = CotizacionDolar
        fields = ["id", "compra", "venta", "fuente", "fecha"]
        read_only_fields = fields


class ClienteSerializer(serializers.ModelSerializer):
    # Opcional: si no se manda, se asigna solo (ver create()) — así no hace
    # falta que el usuario piense un número libre cada vez que carga un cliente.
    numero = serializers.IntegerField(required=False)
    coeficiente_dd = serializers.DecimalField(max_digits=8, decimal_places=5, read_only=True)
    coeficiente_negra = serializers.DecimalField(max_digits=8, decimal_places=5, read_only=True)

    class Meta:
        model = Cliente
        fields = [
            "id", "numero", "nombre", "email", "telefono", "incremento_dd", "incremento_negra",
            "descuento_dd", "descuento_negra", "descuento_galvanizada",
            "coeficiente_dd", "coeficiente_negra", "activo", "notas",
            "creado", "actualizado",
        ]
        read_only_fields = ["id", "creado", "actualizado"]

    def create(self, validated_data):
        if not validated_data.get("numero"):
            ultimo = Cliente.objects.aggregate(models.Max("numero"))["numero__max"] or 0
            validated_data["numero"] = ultimo + 1
        return super().create(validated_data)


class MarkupEspesorChapaSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarkupEspesorChapa
        fields = ["id", "tipo", "espesor", "ancho_mm", "porcentaje", "orden", "activo"]
        read_only_fields = ["id"]


class ChapaGalvanizadaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChapaGalvanizada
        fields = [
            "id", "espesor", "ancho_mm", "costo_usd_kg", "activo", "usar_incremento_general",
            "orden", "creado", "actualizado",
        ]
        read_only_fields = ["id", "creado", "actualizado"]


class ChapaGruesaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChapaGruesa
        fields = [
            "id", "espesor", "ancho_mm", "costo_usd_kg", "activo", "usar_incremento_general",
            "orden", "creado", "actualizado",
        ]
        read_only_fields = ["id", "creado", "actualizado"]


class TuboSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tubo
        fields = [
            "id", "dimensiones", "espesor_mm", "peso_unitario_kg", "costo_usd_kg",
            "largo_barra_m", "activo", "descuento_pct", "descuento_habilitado",
            "orden", "creado", "actualizado",
        ]
        read_only_fields = ["id", "creado", "actualizado"]


class ClienteResumenSerializer(serializers.ModelSerializer):
    """Versión liviana de Cliente, para anidar dentro de un Presupuesto."""

    class Meta:
        model = Cliente
        fields = ["id", "numero", "nombre", "email", "telefono"]


class PresupuestoItemExtraSerializer(serializers.ModelSerializer):
    class Meta:
        model = PresupuestoItemExtra
        fields = ["id", "descripcion", "precio_pesos", "creado"]
        read_only_fields = ["id", "creado"]


class PresupuestoItemSerializer(serializers.ModelSerializer):
    subtotal_pesos = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    extras = PresupuestoItemExtraSerializer(many=True, read_only=True)

    class Meta:
        model = PresupuestoItem
        fields = [
            "id", "tipo", "descripcion", "cantidad", "unidad", "precio_unitario_pesos", "subtotal_pesos",
            "extras", "orden",
        ]
        read_only_fields = ["id"]


class PresupuestoSerializer(serializers.ModelSerializer):
    """
    Serializer de lectura y creación de presupuestos. Los ítems se mandan
    anidados de una sola vez (todo el "carrito" del frontend en un solo
    POST) y se crean juntos de forma atómica.
    """

    items = PresupuestoItemSerializer(many=True)
    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    total_pesos = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    codigo = serializers.CharField(read_only=True)

    class Meta:
        model = Presupuesto
        fields = [
            "id", "numero", "codigo", "cliente", "cliente_detalle", "cotizacion_dolar",
            "estado", "impuesto_pct", "notas", "token_publico", "total_pesos", "items", "creado", "actualizado",
        ]
        read_only_fields = [
            "id", "numero", "codigo", "estado", "impuesto_pct", "token_publico", "creado", "actualizado",
        ]

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("El presupuesto necesita al menos un ítem.")
        return items

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        request = self.context.get("request")
        usuario = getattr(request, "user", None) if request else None
        presupuesto = Presupuesto.objects.create(
            creado_por=usuario if usuario and usuario.is_authenticated else None,
            **validated_data,
        )
        for orden, item_data in enumerate(items_data):
            PresupuestoItem.objects.create(presupuesto=presupuesto, orden=orden, **item_data)
        return presupuesto


class PresupuestoListSerializer(serializers.ModelSerializer):
    """Versión liviana para el listado (sin ítems) — más rápida de paginar."""

    cliente_detalle = ClienteResumenSerializer(source="cliente", read_only=True)
    total_pesos = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    codigo = serializers.CharField(read_only=True)

    class Meta:
        model = Presupuesto
        fields = ["id", "numero", "codigo", "cliente_detalle", "estado", "total_pesos", "creado"]


class EnviarEmailSerializer(serializers.Serializer):
    destinatario = serializers.EmailField()
    mensaje = serializers.CharField(required=False, allow_blank=True, default="")


class ElegirImpuestoSerializer(serializers.Serializer):
    impuesto_pct = serializers.ChoiceField(choices=Presupuesto.IMPUESTO_CHOICES)


class SolicitarResetPasswordSerializer(serializers.Serializer):
    username = serializers.CharField()


class ConfirmarResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(min_length=8)


class ContactoPublicoSerializer(serializers.Serializer):
    """Formulario de contacto del sitio público (lausane.com.ar)."""

    nombre = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    asunto = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    mensaje = serializers.CharField(max_length=4000)

