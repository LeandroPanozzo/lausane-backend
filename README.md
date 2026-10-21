# Lista de Precios — Chapa y Tubo (Django REST Framework)

Backend que reemplaza el Excel `LISTA_UNIFICADA` (hoja INICIO + hojas por
cliente): mismos cálculos, pero con API, base de datos, cotización del dólar
en tiempo real y sin límite de 100 clientes en filas fijas.

## Cómo se corresponde con el Excel

| Excel | Acá |
|---|---|
| `INICIO!C6` (PRECIO BASE DD) | `ConfiguracionGlobal.precio_base_dd` |
| `INICIO!C8` (PRECIO BASE NEGRA) | `ConfiguracionGlobal.precio_base_negra` |
| `INICIO!J8` (Dólar Definido, a mano) | `CotizacionDolar` (se trae sola de una API, ver abajo) |
| Fila `% Incremento` de tubos (0.26) | `ConfiguracionGlobal.incremento_tubos` |
| Tabla de clientes (col B, D, F, L) | modelo `Cliente` |
| Grilla de % por espesor en hoja de cada cliente | modelo `MarkupEspesorChapa` (es la misma tabla para todos los clientes, como en el Excel original) |
| Tablas "Peso Teorico Tubo" | modelo `Tubo` |

La lógica de cálculo (coeficiente → resultado → base U$S → base $, y precio
por espesor) está en `precios/services/calculo_precios.py`, comentada línea
por línea contra las fórmulas originales del Excel. **Fue verificada contra
los valores reales del archivo** (cliente 1, tubo "30 50 0,9", markup de
espesor 16) y da exactamente los mismos números.

## Cotización del dólar en tiempo real

Se usa la API pública `https://dolarapi.com/v1/dolares/oficial` (dólar
oficial, el mismo tipo que se linkeaba a bna.com.ar en el Excel). Configurable
por `.env` (`DOLAR_API_URL`).

- Se cachea por `DOLAR_CACHE_MINUTOS` (default 10) para no golpear la API en
  cada request.
- Si la API externa falla, se usa la última cotización guardada en vez de
  romper los cálculos (con un log de warning).
- Hay un endpoint para cargar la cotización a mano (`POST /api/dolar/manual/`)
  como respaldo si la API está caída por un tiempo largo.
- Para mantenerla siempre fresca sin depender de que alguien abra la app,
  corré `python manage.py actualizar_dolar` en un cron cada 5-10 minutos.

## Instalación

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env           # y ajustá SECRET_KEY, etc.

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Importar el Excel existente

Para no perder la data que ya tenés, importá el Excel original (o uno con el
mismo formato de hoja `INICIO`):

```bash
python manage.py importar_excel /ruta/a/LISTA_UNIFICADA_dic.xlsx
```

Esto crea/actualiza: configuración global, los 100 clientes, la tabla de
markups por espesor (tomada de la hoja `"1"` como referencia — son iguales
para todos los clientes en el Excel original) y el catálogo de tubos.

Es solo por línea de comandos (no hay endpoint de API ni opción en el
frontend) — un reimport masivo pisa datos cargados a mano, así que queda
limitado a quien tenga acceso directo al servidor.

## Autenticación

JWT. Primero pedís el token:

```bash
curl -X POST http://localhost:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "tu_usuario", "password": "tu_clave"}'
```

Y lo mandás en cada request:

```
Authorization: Bearer <access_token>
```

El access token dura 8hs; `POST /api/auth/token/refresh/` con el
`refresh_token` te da uno nuevo.

## Endpoints principales

| Método | Endpoint | Qué hace |
|---|---|---|
| GET/POST | `/api/clientes/` | Listar / crear clientes |
| GET/PUT/PATCH/DELETE | `/api/clientes/{id}/` | Ver, modificar, dar de baja un cliente |
| GET | `/api/clientes/{id}/precios/` | Lista de precios de chapa (DD y Negra) ya calculada con el dólar actual |
| GET/POST | `/api/tubos/` | Listar / crear tubos |
| GET | `/api/tubos/lista-precios/` | Todos los tubos con precio ya calculado |
| GET | `/api/tubos/{id}/precio/` | Precio de un tubo puntual |
| GET/POST | `/api/markups-chapa/` | Tabla de recargos por espesor (chapa) |
| GET/PUT/PATCH | `/api/configuracion/` | Precios base DD/Negra e incremento de tubos |
| GET | `/api/dolar/actual/` | Cotización en uso (agregá `?forzar=true` para forzar consulta a la API externa) |
| POST | `/api/dolar/manual/` | Cargar cotización a mano y forzarla en los cálculos |
| POST | `/api/dolar/volver-oficial/` | Sacar el forzado manual y volver a la cotización oficial online |

### Ejemplo: agregar un cliente nuevo

```bash
curl -X POST http://localhost:8000/api/clientes/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"numero": 101, "nombre": "NUEVO CLIENTE SRL", "incremento_dd": 10, "incremento_negra": 6}'
```

`incremento_dd`/`incremento_negra` son el % tal cual estaba en las columnas F
y L del Excel (10 = 10%, no 0.10).

### Ejemplo: ver la lista de precios de un cliente

```bash
curl http://localhost:8000/api/clientes/101/precios/ -H "Authorization: Bearer <token>"
```

Devuelve la cotización del dólar usada, la base en U$S/pesos para DD y
Negra, y el precio final abierto por cada espesor/ancho.

## Admin de Django

`/admin/` — útil para editar la tabla de markups por espesor o revisar
clientes/tubos sin pegarle directo a la API.

## Presupuestos (carrito, PDF, Excel, email, WhatsApp)

El frontend arma un carrito por cliente y lo manda de una vez a
`POST /api/presupuestos/` con todos los ítems. A partir de ahí:

| Endpoint | Qué hace |
|---|---|
| `POST /api/presupuestos/` | Crea el presupuesto con sus ítems (todo el carrito en un solo request) |
| `GET /api/presupuestos/` | Historial (liviano, sin ítems) |
| `GET /api/presupuestos/{id}/` | Detalle completo con ítems |
| `GET /api/presupuestos/{id}/pdf/` | Descarga el PDF con la identidad de Lausane |
| `GET /api/presupuestos/{id}/excel/` | Descarga el Excel |
| `POST /api/presupuestos/{id}/enviar-email/` | Envía el PDF adjunto por correo (marca el presupuesto como "enviado") |
| `POST /api/presupuestos/{id}/marcar-enviado/` | Marca como enviado manualmente (se usa después de compartir por WhatsApp) |
| `GET /api/presupuestos-publico/{token}/pdf/` | **Sin login** — el link que se manda por WhatsApp/email para que el cliente vea su presupuesto sin loguearse |

Los precios de cada ítem quedan **congelados** al crear el presupuesto (no
cambian después, aunque cambie el dólar o el % del cliente).

### Configurar el envío de emails reales

Por defecto, `EMAIL_BACKEND` está en modo "console": los emails se imprimen
en la terminal del servidor en vez de mandarse de verdad — así podés probar
todo el flujo sin configurar nada. Para mandar emails reales, en el `.env`:

```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=tu_cuenta@gmail.com
EMAIL_HOST_PASSWORD=tu_contraseña_de_aplicación
DEFAULT_FROM_EMAIL=Lausane S.A.C. <tu_cuenta@gmail.com>
```

Si usás Gmail, `EMAIL_HOST_PASSWORD` tiene que ser una ["contraseña de
aplicación"](https://myaccount.google.com/apppasswords), no la contraseña
normal de la cuenta.

### WhatsApp

No hay una API gratuita "oficial" para mandar WhatsApp desde el backend sin
una cuenta de WhatsApp Business API. Por eso el envío por WhatsApp lo hace
el **frontend**: abre un link `wa.me/<teléfono>?text=...` con el mensaje y
el link público del presupuesto — el usuario solo tiene que confirmar el
envío desde su WhatsApp Web o la app. El teléfono se toma del campo
`telefono` del cliente (con código de país, sin espacios ni signos).

## Notas y limitaciones a tener en cuenta

- La tabla de recargos por espesor (`MarkupEspesorChapa`) es **global**, no
  por cliente — así estaba en el Excel original (los mismos % en todas las
  hojas de cliente que se revisaron). Si en tu operación algún cliente
  necesita un recargo por espesor distinto al resto, hay que extender el
  modelo para que sea por cliente.
- El importador de tubos es heurístico: el Excel tiene varios bloques con
  layouts levemente distintos (peso teórico, unidad, espesor en el string de
  dimensiones). Se validó contra varios valores reales y coincide, pero
  convendría revisar la lista de tubos importada una vez (`GET
  /api/tubos/lista-precios/` o el admin) antes de usarla en producción.
- No se migró la lógica de "S/MEL" ni algunas celdas sueltas con notas
  manuales que había en las hojas de cliente (ej. "herrero 10%", "pagola
  10%") porque no seguían un patrón consistente entre hojas — si esos
  recargos puntuales por cliente son importantes, decime y los agrego como
  un campo extra en `Cliente`.
- `DEBUG=True` y SQLite son para desarrollo. Para producción: `DEBUG=False`,
  `ALLOWED_HOSTS` con tu dominio real, Postgres (ya está el soporte en
  `settings.py`, solo hay que completar las variables `DB_*` del `.env`), y
  servir con gunicorn/uwsgi detrás de nginx.
# lausane-backend
