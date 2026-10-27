import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.core.validators import MinValueValidator


class ConfiguracionGlobal(models.Model):
    """
    Singleton con los valores 'semilla' del Excel (hoja INICIO, celdas C6/C8),
    más el % de incremento general de tubos (hoja INICIO, sección inferior).

    Solo debe existir una fila: usá ConfiguracionGlobal.actual() para leerla/crearla.
    """

    precio_base_dd = models.DecimalField(
        max_digits=10, decimal_places=5, default=Decimal("1.297"),
        help_text="PRECIO BASE DD (U$S/kg) — Excel INICIO!C6",
    )
    precio_base_negra = models.DecimalField(
        max_digits=10, decimal_places=5, default=Decimal("1.140"),
        help_text="PRECIO BASE NEGRA (U$S/kg) — Excel INICIO!C8",
    )
    incremento_tubos = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0.26"),
        help_text="% de incremento general para tubos, como fracción (0.26 = 26%)",
    )
    incremento_galvanizada = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0.20"),
        help_text=(
            "% de incremento general para chapa galvanizada, como fracción (0.20 = 20%). "
            "En el Excel esta chapa no usa el esquema de recargo por cliente de DD/Negra — "
            "cada espesor/ancho tiene su propio costo en U$S/kg (ver ChapaGalvanizada) y se le "
            "aplica este incremento único, igual que a los tubos. Valor inicial estimado a partir "
            "del Excel — confirmar/ajustar en Configuración."
        ),
    )

    DOLAR_MODO_AUTOMATICO = "automatico"
    DOLAR_MODO_MANUAL = "manual"
    DOLAR_MODO_CHOICES = [
        (DOLAR_MODO_AUTOMATICO, "Automático (cotización online)"),
        (DOLAR_MODO_MANUAL, "Manual (forzado)"),
    ]
    dolar_modo = models.CharField(
        max_length=10, choices=DOLAR_MODO_CHOICES, default=DOLAR_MODO_AUTOMATICO,
        help_text=(
            "Si está en 'manual', los cálculos usan la última cotización cargada a mano "
            "en vez de la oficial online, hasta que se vuelva a modo automático."
        ),
    )
    incremento_gruesas = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0.20"),
        help_text=(
            "% de incremento general para chapa gruesa, como fracción (0.20 = 20%). "
            "Mismo esquema que incremento_galvanizada: costo propio en U$S/kg por espesor/ancho "
            "más este incremento único (en vez del % sobre precio base de DD/Negra)."
        ),
    )
    email_remitente = models.EmailField(
        blank=True, default="",
        help_text=(
            "Cuenta de Gmail desde la que se mandan los presupuestos por email. "
            "Vacío = usa la configuración fija del .env (EMAIL_HOST_USER)."
        ),
    )
    email_password = models.CharField(
        max_length=255, blank=True, default="",
        help_text=(
            "Contraseña de aplicación de Gmail para email_remitente (16 caracteres, "
            "no la contraseña normal de la cuenta) — generada en myaccount.google.com/apppasswords."
        ),
    )
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración global"
        verbose_name_plural = "Configuración global"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # no se permite borrar el singleton

    @classmethod
    def actual(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Configuración global de precios"


class CotizacionDolar(models.Model):
    """
    Histórico de cotizaciones del dólar. Cada vez que se consulta la API externa
    (o se carga manualmente) se guarda un registro nuevo, así queda trazabilidad
    de qué cotización se usó para cada cálculo.
    """

    FUENTE_OFICIAL = "oficial"
    FUENTE_MANUAL = "manual"
    FUENTE_CHOICES = [
        (FUENTE_OFICIAL, "Dólar oficial (API)"),
        (FUENTE_MANUAL, "Carga manual"),
    ]

    compra = models.DecimalField(max_digits=10, decimal_places=2)
    venta = models.DecimalField(max_digits=10, decimal_places=2)
    fuente = models.CharField(max_length=20, choices=FUENTE_CHOICES, default=FUENTE_OFICIAL)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "Cotización del dólar"
        verbose_name_plural = "Cotizaciones del dólar"

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} — venta ${self.venta}"


class Cliente(models.Model):
    """
    Un cliente (o grupo de alias comerciales, tal como estaban agrupados en el
    Excel: 'tato/rolando/alpes/javier/bassaro/El roble' es UN cliente).

    incremento_dd / incremento_negra son el '% Incremento' de las columnas F y L
    de la hoja INICIO (ej: 8 significa 8%, no 0.08).
    """

    numero = models.PositiveIntegerField(unique=True, help_text="Número de cliente (columna B del Excel)")
    nombre = models.CharField(max_length=500, help_text="Nombre o alias combinados, ej: 'FABRICAL' o 'tato/rolando/...'")
    email = models.EmailField(blank=True, default="", help_text="Para enviarle presupuestos por correo")
    telefono = models.CharField(
        max_length=30, blank=True, default="",
        help_text="Con código de país, ej: 5491122334455 (para enviar presupuestos por WhatsApp)",
    )
    incremento_dd = models.DecimalField(
        max_digits=6, decimal_places=3, validators=[MinValueValidator(Decimal("0"))],
        help_text="% de incremento sobre precio base DD (ej: 8 = 8%)",
    )
    incremento_negra = models.DecimalField(
        max_digits=6, decimal_places=3, validators=[MinValueValidator(Decimal("0"))],
        help_text="% de incremento sobre precio base Negra (ej: 5 = 5%)",
    )
    descuento_dd = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="% de descuento propio de este cliente sobre el precio de Laminado en Frío (0 = sin descuento)",
    )
    descuento_negra = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="% de descuento propio de este cliente sobre el precio de chapa Negra (0 = sin descuento)",
    )
    descuento_galvanizada = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="% de descuento propio de este cliente sobre el precio de chapa galvanizada (0 = sin descuento)",
    )
    activo = models.BooleanField(default=True)
    notas = models.TextField(blank=True, default="")
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["numero"]

    @property
    def coeficiente_dd(self) -> Decimal:
        """Equivalente a H = PRODUCT(F, 0.01) del Excel."""
        return self.incremento_dd / Decimal("100")

    @property
    def coeficiente_negra(self) -> Decimal:
        return self.incremento_negra / Decimal("100")

    def __str__(self):
        return f"{self.numero} — {self.nombre}"


class MarkupEspesorChapa(models.Model):
    """
    Recargo por espesor/ancho de chapa, tal como aparece en la hoja de cada
    cliente (ej: base + 7%, base + 4%, etc). En el Excel original estos
    porcentajes eran los mismos para todos los clientes, por eso acá son una
    tabla global en vez de repetirse por cliente.
    """

    TIPO_DD = "DD"
    TIPO_NEGRA = "NEGRA"
    TIPO_CHOICES = [(TIPO_DD, "Laminado en Frío"), (TIPO_NEGRA, "Negra")]

    tipo = models.CharField(max_length=5, choices=TIPO_CHOICES)
    espesor = models.CharField(max_length=30, help_text="Código de espesor, ej: '16', '18', '12,14 y 20'")
    ancho_mm = models.CharField(max_length=20, help_text="Ancho de la chapa en mm, ej: '1000', '1220', '1500'")
    porcentaje = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True,
        help_text="Recargo como fracción sobre la base (0.07 = 7%). Vacío = no disponible (era 'XXX' en el Excel)",
    )
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True, help_text="Si está inactivo, no aparece en la lista de precios del cliente")

    class Meta:
        unique_together = ("tipo", "espesor", "ancho_mm")
        ordering = ["tipo", "orden"]
        verbose_name = "Markup de espesor (chapa)"
        verbose_name_plural = "Markups de espesor (chapa)"

    def __str__(self):
        pct = f"{self.porcentaje*100:.2f}%" if self.porcentaje is not None else "N/D"
        return f"{self.tipo} · espesor {self.espesor} · {self.ancho_mm}mm · {pct}"


class ChapaGalvanizada(models.Model):
    """
    Chapa galvanizada, por espesor/ancho. A diferencia de DD/Negra (que
    aplican un % de recargo sobre un precio base compartido entre todos los
    clientes), en el Excel esta chapa tiene un COSTO EN U$S/KG propio para
    cada combinación de espesor y ancho — el mismo esquema que ya usamos para
    Tubo (costo de compra + incremento_galvanizada global), pero acá
    organizado por espesor/ancho en vez de por dimensión de tubo.

    En el Excel había además un intento de precio por cliente para esta
    chapa, pero esos datos estaban mayormente vacíos o con fórmulas rotas
    (referencias a celdas sin valor) — no una fuente confiable — así que acá
    queda como un catálogo global, igual que Tubo.
    """

    espesor = models.CharField(max_length=30, help_text="Código de espesor, ej: '16', '18', '12,14 y 20'")
    ancho_mm = models.CharField(max_length=20, help_text="Ancho de la chapa en mm, ej: '1000', '1220'")
    costo_usd_kg = models.DecimalField(max_digits=10, decimal_places=4, help_text="Costo de compra en U$S/kg")
    activo = models.BooleanField(default=True, help_text="Si está inactivo, no aparece en la lista de precios del cliente")
    usar_incremento_general = models.BooleanField(
        default=True,
        help_text=(
            "Si está destildado, esta chapa se vende directo al costo (sin aplicar "
            "incremento_galvanizada) — para cuando un espesor/ancho puntual no debe llevar recargo."
        ),
    )
    orden = models.PositiveIntegerField(default=0)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("espesor", "ancho_mm")
        ordering = ["orden", "espesor"]
        verbose_name = "Chapa galvanizada"
        verbose_name_plural = "Chapas galvanizadas"

    def __str__(self):
        return f"Galvanizada · espesor {self.espesor} · {self.ancho_mm}mm"


class ChapaGruesa(models.Model):
    """
    Chapa gruesa, por espesor/ancho — mismo esquema que ChapaGalvanizada:
    costo propio en U$S/kg por combinación de espesor/ancho, más el
    incremento_gruesas global (en vez de un % sobre un precio base
    compartido, como DD/Negra).
    """

    espesor = models.CharField(max_length=30, help_text="Código de espesor, ej: '16', '18', '12,14 y 20'")
    ancho_mm = models.CharField(max_length=20, help_text="Ancho de la chapa en mm, ej: '1000', '1220'")
    costo_usd_kg = models.DecimalField(max_digits=10, decimal_places=4, help_text="Costo de compra en U$S/kg")
    activo = models.BooleanField(default=True, help_text="Si está inactivo, no aparece en la lista de precios del cliente")
    usar_incremento_general = models.BooleanField(
        default=True,
        help_text=(
            "Si está destildado, esta chapa se vende directo al costo (sin aplicar "
            "incremento_gruesas) — para cuando un espesor/ancho puntual no debe llevar recargo."
        ),
    )
    orden = models.PositiveIntegerField(default=0)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("espesor", "ancho_mm")
        ordering = ["orden", "espesor"]
        verbose_name = "Chapa gruesa"
        verbose_name_plural = "Chapas gruesas"

    def __str__(self):
        return f"Gruesa · espesor {self.espesor} · {self.ancho_mm}mm"


class Tubo(models.Model):
    """
    Catálogo de tubos estructurales. Réplica de las tablas 'Peso Teorico Tubo'
    de la hoja INICIO. El costo está en U$S/kg (según factura del proveedor) y
    el precio de venta se calcula aplicando el incremento_tubos global.
    """

    dimensiones = models.CharField(max_length=50, help_text="Ej: '30 50 0,9' o '20x20x1.6'")
    espesor_mm = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    peso_unitario_kg = models.DecimalField(
        max_digits=10, decimal_places=4,
        help_text="Peso teórico del tubo (kg), usado para pasar de precio/kg a precio/tubo",
    )
    costo_usd_kg = models.DecimalField(max_digits=10, decimal_places=4, help_text="Costo de compra en U$S/kg")
    largo_barra_m = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("6"))
    activo = models.BooleanField(default=True)
    descuento_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("2.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="% de descuento por defecto sobre el precio de venta (ej: 2 = 2%)",
    )
    descuento_habilitado = models.BooleanField(
        default=True,
        help_text="Si está activo, el descuento se aplica por defecto al agregar este tubo a un presupuesto",
    )
    orden = models.PositiveIntegerField(default=0)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["orden", "dimensiones"]

    def precio_venta_usd_kg(self, incremento_tubos: Decimal) -> Decimal:
        return self.costo_usd_kg * (Decimal("1") + incremento_tubos)

    def precio_venta_usd_tubo(self, incremento_tubos: Decimal) -> Decimal:
        return self.precio_venta_usd_kg(incremento_tubos) * self.peso_unitario_kg

    def precio_venta_pesos_tubo(self, incremento_tubos: Decimal, cotizacion: Decimal) -> Decimal:
        return self.precio_venta_usd_tubo(incremento_tubos) * cotizacion

    def __str__(self):
        return f"Tubo {self.dimensiones}"


class Presupuesto(models.Model):
    """
    Un presupuesto armado para un cliente a partir del carrito del frontend.
    Los precios de cada ítem quedan "congelados" al momento de crear el
    presupuesto (no se recalculan después, aunque cambie el dólar o el
    coeficiente del cliente) — así el presupuesto enviado no cambia solo.
    """

    ESTADO_BORRADOR = "borrador"
    ESTADO_ENVIADO = "enviado"
    ESTADO_CHOICES = [(ESTADO_BORRADOR, "Borrador"), (ESTADO_ENVIADO, "Enviado")]

    IMPUESTO_10_5 = Decimal("10.5")
    IMPUESTO_21 = Decimal("21")
    IMPUESTO_CHOICES = [(IMPUESTO_10_5, "10,5%"), (IMPUESTO_21, "21%")]

    numero = models.PositiveIntegerField(unique=True, editable=False)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="presupuestos")
    cotizacion_dolar = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Cotización del dólar usada al armar el presupuesto (congelada)",
    )
    impuesto_pct = models.DecimalField(
        max_digits=4, decimal_places=1, choices=IMPUESTO_CHOICES, null=True, blank=True,
        help_text="10,5 o 21 — se tiene que elegir antes de ver/descargar/mandar el PDF",
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_BORRADOR)
    notas = models.TextField(blank=True, default="")
    token_publico = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="presupuestos"
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado"]

    def save(self, *args, **kwargs):
        if not self.numero:
            # select_for_update evita que dos requests concurrentes lean el
            # mismo "último número" y choquen contra el unique=True al guardar.
            with transaction.atomic():
                ultimo = Presupuesto.objects.select_for_update().order_by("-numero").first()
                self.numero = (ultimo.numero + 1) if ultimo else 1000
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    @property
    def total_pesos(self) -> Decimal:
        return sum((item.total_con_extras_pesos for item in self.items.all()), Decimal("0"))

    @property
    def codigo(self) -> str:
        return f"LAU-{self.numero}"

    def __str__(self):
        return f"Presupuesto {self.codigo} — {self.cliente.nombre}"


class PresupuestoItem(models.Model):
    TIPO_CHAPA = "CHAPA"
    TIPO_TUBO = "TUBO"
    TIPO_OTRO = "OTRO"
    TIPO_CHOICES = [(TIPO_CHAPA, "Chapa"), (TIPO_TUBO, "Tubo"), (TIPO_OTRO, "Otro")]

    presupuesto = models.ForeignKey(Presupuesto, on_delete=models.CASCADE, related_name="items")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default=TIPO_OTRO)
    descripcion = models.CharField(max_length=300, help_text="Ej: 'Chapa DD · espesor 16 · ancho 1000mm'")
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("1"))
    unidad = models.CharField(max_length=20, default="kg", help_text="kg, unidad, barra, etc.")
    precio_unitario_pesos = models.DecimalField(max_digits=14, decimal_places=2)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["orden", "id"]

    @property
    def subtotal_pesos(self) -> Decimal:
        """Cantidad x precio unitario, SIN los extras (eso se muestra aparte)."""
        return (self.cantidad * self.precio_unitario_pesos).quantize(Decimal("0.01"))

    @property
    def total_extras_pesos(self) -> Decimal:
        return sum((e.precio_pesos for e in self.extras.all()), Decimal("0"))

    @property
    def total_con_extras_pesos(self) -> Decimal:
        """Lo que este ítem aporta de verdad al total del presupuesto (subtotal + extras)."""
        return (self.subtotal_pesos + self.total_extras_pesos).quantize(Decimal("0.01"))

    def __str__(self):
        return f"{self.descripcion} x{self.cantidad}"


class PresupuestoItemExtra(models.Model):
    """Un agregado manual sobre un ítem ya creado (ej: flete, corte especial)."""

    item = models.ForeignKey(PresupuestoItem, on_delete=models.CASCADE, related_name="extras")
    descripcion = models.CharField(max_length=200)
    precio_pesos = models.DecimalField(max_digits=14, decimal_places=2)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado", "id"]

    def __str__(self):
        return f"{self.descripcion} (+${self.precio_pesos})"

