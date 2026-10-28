from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Cliente, ChapaGalvanizada, ChapaGruesa, ConfiguracionGlobal, MarkupEspesorChapa, Tubo, Presupuesto,
    PresupuestoItem, PresupuestoItemExtra, PresupuestoItemAjusteUnitario,
)
from .serializers import (
    ChapaGalvanizadaSerializer,
    ChapaGruesaSerializer,
    ClienteSerializer,
    ConfiguracionGlobalSerializer,
    ContactoPublicoSerializer,
    CotizacionDolarSerializer,
    ElegirImpuestoSerializer,
    EnviarEmailSerializer,
    MarkupEspesorChapaSerializer,
    PresupuestoItemAjusteUnitarioSerializer,
    PresupuestoItemExtraSerializer,
    PresupuestoListSerializer,
    PresupuestoSerializer,
    TuboSerializer,
)
from .services import calculo_precios, cotizacion_dolar, whatsapp_service
from .services.pdf_presupuesto import generar_pdf_presupuesto, _formato_pesos
from .services.excel_presupuesto import generar_excel_presupuesto
from .services.email_presupuesto import enviar_presupuesto_por_email
from .services.whatsapp_service import WhatsAppServiceError


class ClienteViewSet(viewsets.ModelViewSet):
    """
    CRUD completo de clientes.
    GET /api/clientes/                -> listar (con ?search= por nombre)
    POST /api/clientes/               -> crear cliente nuevo
    GET/PUT/PATCH/DELETE /api/clientes/{id}/
    GET /api/clientes/{id}/precios/   -> lista de precios calculada (chapa)
    """

    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ["nombre", "numero"]

    @action(detail=True, methods=["get"], url_path="precios")
    def precios(self, request, pk=None):
        cliente = get_object_or_404(Cliente, pk=pk)
        config = ConfiguracionGlobal.actual()
        try:
            cotizacion = cotizacion_dolar.obtener_cotizacion_actual(
                forzar_actualizacion=request.query_params.get("forzar_dolar") == "true"
            )
        except cotizacion_dolar.CotizacionDolarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        precios = calculo_precios.calcular_lista_precios_chapa(cliente, config, cotizacion.venta)
        return Response({
            "cliente": ClienteSerializer(cliente).data,
            "cotizacion_dolar": CotizacionDolarSerializer(cotizacion).data,
            "precios": precios,
        })


class MarkupEspesorChapaViewSet(viewsets.ModelViewSet):
    """Tabla de recargos por espesor de chapa (compartida por todos los clientes)."""

    queryset = MarkupEspesorChapa.objects.all()
    serializer_class = MarkupEspesorChapaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # DEFAULT_FILTER_BACKENDS solo trae SearchFilter (no django-filter), así
        # que `filterset_fields` no sirve acá — filtramos "a mano" por ?tipo=.
        qs = super().get_queryset()
        tipo = self.request.query_params.get("tipo")
        if tipo:
            qs = qs.filter(tipo=tipo)
        return qs


class TuboViewSet(viewsets.ModelViewSet):
    """CRUD de tubos + precio calculado."""

    queryset = Tubo.objects.all()
    serializer_class = TuboSerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ["dimensiones"]

    @action(detail=True, methods=["get"], url_path="precio")
    def precio(self, request, pk=None):
        tubo = get_object_or_404(Tubo, pk=pk)
        config = ConfiguracionGlobal.actual()
        try:
            cotizacion = cotizacion_dolar.obtener_cotizacion_actual(
                forzar_actualizacion=request.query_params.get("forzar_dolar") == "true"
            )
        except cotizacion_dolar.CotizacionDolarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        precio = calculo_precios.calcular_precio_tubo(tubo, config, cotizacion.venta)
        return Response({
            "cotizacion_dolar": CotizacionDolarSerializer(cotizacion).data,
            "precio": precio,
        })

    @action(detail=False, methods=["get"], url_path="lista-precios")
    def lista_precios(self, request):
        config = ConfiguracionGlobal.actual()
        try:
            cotizacion = cotizacion_dolar.obtener_cotizacion_actual(
                forzar_actualizacion=request.query_params.get("forzar_dolar") == "true"
            )
        except cotizacion_dolar.CotizacionDolarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        precios = calculo_precios.calcular_lista_precios_tubos(config, cotizacion.venta)
        return Response({
            "cotizacion_dolar": CotizacionDolarSerializer(cotizacion).data,
            "incremento_tubos": config.incremento_tubos,
            "tubos": precios,
        })


class ChapaGalvanizadaViewSet(viewsets.ModelViewSet):
    """CRUD de chapa galvanizada (por espesor/ancho) + precio calculado."""

    queryset = ChapaGalvanizada.objects.all()
    serializer_class = ChapaGalvanizadaSerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ["espesor", "ancho_mm"]

    @action(detail=False, methods=["get"], url_path="lista-precios")
    def lista_precios(self, request):
        config = ConfiguracionGlobal.actual()
        try:
            cotizacion = cotizacion_dolar.obtener_cotizacion_actual(
                forzar_actualizacion=request.query_params.get("forzar_dolar") == "true"
            )
        except cotizacion_dolar.CotizacionDolarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # Sin ?cliente_id= es el catálogo global (sin descuento), usado en la
        # pantalla de administración de Chapas. Con ?cliente_id= se le aplica
        # el % de descuento propio de ese cliente (Cliente.descuento_galvanizada),
        # usado en la ficha del cliente al armar un presupuesto.
        descuento_pct = Decimal("0")
        cliente_id = request.query_params.get("cliente_id")
        if cliente_id:
            cliente = get_object_or_404(Cliente, pk=cliente_id)
            descuento_pct = cliente.descuento_galvanizada

        precios = calculo_precios.calcular_lista_precios_galvanizada(
            config, cotizacion.venta, descuento_pct=descuento_pct,
        )
        return Response({
            "cotizacion_dolar": CotizacionDolarSerializer(cotizacion).data,
            "incremento_galvanizada": config.incremento_galvanizada,
            "chapas": precios,
        })


class ChapaGruesaViewSet(viewsets.ModelViewSet):
    """CRUD de chapa gruesa (por espesor/ancho) + precio calculado."""

    queryset = ChapaGruesa.objects.all()
    serializer_class = ChapaGruesaSerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ["espesor", "ancho_mm"]

    @action(detail=False, methods=["get"], url_path="lista-precios")
    def lista_precios(self, request):
        config = ConfiguracionGlobal.actual()
        try:
            cotizacion = cotizacion_dolar.obtener_cotizacion_actual(
                forzar_actualizacion=request.query_params.get("forzar_dolar") == "true"
            )
        except cotizacion_dolar.CotizacionDolarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        precios = calculo_precios.calcular_lista_precios_gruesa(config, cotizacion.venta)
        return Response({
            "cotizacion_dolar": CotizacionDolarSerializer(cotizacion).data,
            "incremento_gruesas": config.incremento_gruesas,
            "chapas": precios,
        })


class ConfiguracionGlobalView(generics.RetrieveUpdateAPIView):
    """GET/PUT/PATCH /api/configuracion/ -> precios base DD/Negra e incremento de tubos."""

    serializer_class = ConfiguracionGlobalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return ConfiguracionGlobal.actual()


class CotizacionDolarView(APIView):
    """
    GET /api/dolar/actual/             -> cotización en uso (usa caché)
    GET /api/dolar/actual/?forzar=true -> fuerza a consultar la API externa

    Si el sistema está en modo manual (ver ConfiguracionGlobal.dolar_modo),
    la cotización "en uso" es la cargada a mano — no vence sola — y la
    respuesta suma "referencia_oficial" con la cotización online del momento,
    solo para mostrarla de referencia (no se usa en los cálculos). Ahí
    `forzar=true` refresca esa referencia, no la que está en uso.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        forzar = request.query_params.get("forzar") == "true"
        config = ConfiguracionGlobal.actual()
        en_modo_manual = config.dolar_modo == ConfiguracionGlobal.DOLAR_MODO_MANUAL

        try:
            if en_modo_manual:
                cot = cotizacion_dolar.obtener_cotizacion_actual()
                referencia = cotizacion_dolar.obtener_cotizacion_oficial_referencia(forzar_actualizacion=forzar)
            else:
                cot = cotizacion_dolar.obtener_cotizacion_actual(forzar_actualizacion=forzar)
                referencia = None
        except cotizacion_dolar.CotizacionDolarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        data = CotizacionDolarSerializer(cot).data
        data["forzado_manual"] = en_modo_manual
        data["referencia_oficial"] = CotizacionDolarSerializer(referencia).data if referencia else None
        return Response(data)


class CotizacionDolarManualView(APIView):
    """
    POST /api/dolar/manual/ -> cargar una cotización a mano y FORZAR al
    sistema a usarla en los cálculos en vez de la oficial online, hasta que
    se cargue otra o se llame a /api/dolar/volver-oficial/.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        compra = request.data.get("compra")
        venta = request.data.get("venta")
        if compra is None or venta is None:
            return Response(
                {"detail": "Se requieren los campos 'compra' y 'venta'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cot = cotizacion_dolar.fijar_cotizacion_manual(Decimal(str(compra)), Decimal(str(venta)))
        data = CotizacionDolarSerializer(cot).data
        data["forzado_manual"] = True
        data["referencia_oficial"] = None
        return Response(data, status=status.HTTP_201_CREATED)


class CotizacionDolarVolverOficialView(APIView):
    """POST /api/dolar/volver-oficial/ -> saca el pin manual y vuelve a usar
    la cotización oficial online (trayendo una fresca de una)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            cot = cotizacion_dolar.volver_a_cotizacion_oficial()
        except cotizacion_dolar.CotizacionDolarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        data = CotizacionDolarSerializer(cot).data
        data["forzado_manual"] = False
        data["referencia_oficial"] = None
        return Response(data)


class PresupuestoViewSet(viewsets.ModelViewSet):
    """
    Presupuestos armados a partir del carrito del frontend.

    POST /api/presupuestos/            -> crea el presupuesto con todos los ítems del carrito
    GET  /api/presupuestos/            -> historial (liviano, sin ítems)
    GET  /api/presupuestos/{id}/       -> detalle completo con ítems
    GET  /api/presupuestos/{id}/pdf/   -> descarga el PDF
    GET  /api/presupuestos/{id}/excel/ -> descarga el Excel
    POST /api/presupuestos/{id}/enviar-email/  -> envía el PDF por correo
    """

    queryset = Presupuesto.objects.select_related("cliente").prefetch_related("items")
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action == "list":
            return PresupuestoListSerializer
        return PresupuestoSerializer

    @staticmethod
    def _falta_elegir_impuesto(presupuesto):
        """
        Devuelve una Response 400 si todavía no se eligió el % de impuestos
        para este presupuesto (hace falta antes de ver/descargar/mandar el
        PDF por cualquier vía), o None si ya está elegido.
        """
        if presupuesto.impuesto_pct is None:
            return Response(
                {"detail": "Elegí primero el % de impuestos (10,5% o 21%) para este presupuesto."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    @action(detail=True, methods=["post"], url_path=r"items/(?P<item_pk>\d+)/agregar-extra")
    def agregar_extra(self, request, pk=None, item_pk=None):
        presupuesto = self.get_object()
        item = get_object_or_404(PresupuestoItem, pk=item_pk, presupuesto=presupuesto)
        serializer = PresupuestoItemExtraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PresupuestoItemExtra.objects.create(item=item, **serializer.validated_data)
        return Response(PresupuestoSerializer(presupuesto).data)

    @action(detail=True, methods=["delete"], url_path=r"items/(?P<item_pk>\d+)/extras/(?P<extra_pk>\d+)")
    def quitar_extra(self, request, pk=None, item_pk=None, extra_pk=None):
        presupuesto = self.get_object()
        extra = get_object_or_404(
            PresupuestoItemExtra, pk=extra_pk, item_id=item_pk, item__presupuesto=presupuesto
        )
        extra.delete()
        return Response(PresupuestoSerializer(presupuesto).data)

    @action(detail=True, methods=["post"], url_path=r"items/(?P<item_pk>\d+)/agregar-ajuste-unitario")
    def agregar_ajuste_unitario(self, request, pk=None, item_pk=None):
        presupuesto = self.get_object()
        item = get_object_or_404(PresupuestoItem, pk=item_pk, presupuesto=presupuesto)
        serializer = PresupuestoItemAjusteUnitarioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PresupuestoItemAjusteUnitario.objects.create(item=item, **serializer.validated_data)
        return Response(PresupuestoSerializer(presupuesto).data)

    @action(
        detail=True, methods=["delete"],
        url_path=r"items/(?P<item_pk>\d+)/ajustes-unitarios/(?P<ajuste_pk>\d+)",
    )
    def quitar_ajuste_unitario(self, request, pk=None, item_pk=None, ajuste_pk=None):
        presupuesto = self.get_object()
        ajuste = get_object_or_404(
            PresupuestoItemAjusteUnitario, pk=ajuste_pk, item_id=item_pk, item__presupuesto=presupuesto
        )
        ajuste.delete()
        return Response(PresupuestoSerializer(presupuesto).data)

    @action(detail=True, methods=["post"], url_path="elegir-impuesto")
    def elegir_impuesto(self, request, pk=None):
        presupuesto = self.get_object()
        serializer = ElegirImpuestoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        presupuesto.impuesto_pct = serializer.validated_data["impuesto_pct"]
        presupuesto.save(update_fields=["impuesto_pct"])
        return Response(PresupuestoSerializer(presupuesto).data)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        presupuesto = self.get_object()
        error = self._falta_elegir_impuesto(presupuesto)
        if error:
            return error
        pdf_bytes = generar_pdf_presupuesto(presupuesto)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="presupuesto_lausane_{presupuesto.numero}.pdf"'
        return response

    @action(detail=True, methods=["get"], url_path="excel")
    def excel(self, request, pk=None):
        presupuesto = self.get_object()
        excel_bytes = generar_excel_presupuesto(presupuesto)
        response = HttpResponse(
            excel_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="presupuesto_lausane_{presupuesto.numero}.xlsx"'
        return response

    @action(detail=True, methods=["post"], url_path="enviar-email")
    def enviar_email(self, request, pk=None):
        presupuesto = self.get_object()
        error = self._falta_elegir_impuesto(presupuesto)
        if error:
            return error
        serializer = EnviarEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            enviar_presupuesto_por_email(
                presupuesto,
                serializer.validated_data["destinatario"],
                serializer.validated_data.get("mensaje", ""),
            )
        except Exception as exc:  # noqa: BLE001 — cualquier falla de SMTP se informa igual
            return Response(
                {"detail": f"No se pudo enviar el email: {exc}"}, status=status.HTTP_502_BAD_GATEWAY
            )

        presupuesto.estado = Presupuesto.ESTADO_ENVIADO
        presupuesto.save(update_fields=["estado"])
        return Response({"detail": "Presupuesto enviado por email correctamente."})

    @action(detail=True, methods=["post"], url_path="marcar-enviado")
    def marcar_enviado(self, request, pk=None):
        """Se llama después de compartir por WhatsApp (no hay forma de confirmar la entrega, pero sí de marcarlo)."""
        presupuesto = self.get_object()
        presupuesto.estado = Presupuesto.ESTADO_ENVIADO
        presupuesto.save(update_fields=["estado"])
        return Response(PresupuestoSerializer(presupuesto).data)

    @action(detail=True, methods=["post"], url_path="enviar-whatsapp")
    def enviar_whatsapp(self, request, pk=None):
        """Manda el PDF por WhatsApp automáticamente, vía el servicio interno (Baileys)."""
        presupuesto = self.get_object()
        error = self._falta_elegir_impuesto(presupuesto)
        if error:
            return error
        telefono = (presupuesto.cliente.telefono or "").strip()
        if not telefono:
            return Response(
                {"detail": "Este cliente no tiene un teléfono cargado."}, status=status.HTTP_400_BAD_REQUEST
            )

        texto = (
            f"Hola {presupuesto.cliente.nombre}, te compartimos el Presupuesto Lausane "
            f"N° {presupuesto.codigo} por un total de {_formato_pesos(presupuesto.total_pesos)}."
        )
        pdf_bytes = generar_pdf_presupuesto(presupuesto)
        nombre_archivo = f"presupuesto_lausane_{presupuesto.numero}.pdf"

        try:
            whatsapp_service.enviar_documento(telefono, texto, pdf_bytes, nombre_archivo)
        except WhatsAppServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        presupuesto.estado = Presupuesto.ESTADO_ENVIADO
        presupuesto.save(update_fields=["estado"])
        return Response(PresupuestoSerializer(presupuesto).data)


class WhatsAppEstadoView(APIView):
    """GET /api/whatsapp/estado/ — estado de la sesión del servicio de WhatsApp."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            estado = whatsapp_service.obtener_estado()
        except WhatsAppServiceError as exc:
            return Response({"estado": "no_disponible", "detalle": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(estado)


class WhatsAppQrView(APIView):
    """GET /api/whatsapp/qr/ — PNG del QR vigente para vincular el teléfono (404 si no hace falta)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            png = whatsapp_service.obtener_qr_png()
        except WhatsAppServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        if png is None:
            return Response({"detail": "No hay un QR pendiente."}, status=status.HTTP_404_NOT_FOUND)
        return HttpResponse(png, content_type="image/png")


class ContactoPublicoView(APIView):
    """
    POST /api/contacto/ — formulario de contacto del sitio público
    (lausane.com.ar). Sin autenticación, con throttle propio para evitar spam.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "contacto"

    def post(self, request):
        serializer = ContactoPublicoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        cuerpo = (
            f"Nombre: {datos['nombre']}\n"
            f"Email: {datos['email']}\n"
            f"Teléfono: {datos.get('telefono') or '-'}\n\n"
            f"{datos['mensaje']}"
        )
        asunto = f"[Contacto web] {datos.get('asunto') or 'Nueva consulta'}"

        email = EmailMessage(
            subject=asunto,
            body=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.CONTACTO_EMAIL_DESTINO],
            reply_to=[datos["email"]],
        )
        try:
            email.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001 — cualquier falla de SMTP se informa igual
            return Response(
                {"detail": f"No se pudo enviar el mensaje: {exc}"}, status=status.HTTP_502_BAD_GATEWAY
            )

        return Response({"detail": "Mensaje enviado. Te vamos a contactar a la brevedad."})


class PresupuestoPublicoPDFView(APIView):
    """
    GET /api/presupuestos/publico/<token>/pdf/

    Sin autenticación: es el link que se comparte por WhatsApp o email para
    que el cliente pueda ver/descargar su presupuesto sin tener que loguearse.
    El token es un UUID random, no adivinable.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        presupuesto = get_object_or_404(Presupuesto, token_publico=token)
        pdf_bytes = generar_pdf_presupuesto(presupuesto)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="presupuesto_lausane_{presupuesto.numero}.pdf"'
        return response

