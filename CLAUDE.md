# PREVIFUEGO — Sistema Automático SERCOP

> Sistema de monitoreo y respuesta automática al portal de compras públicas de Ecuador.
> Todo corre en GitHub Actions sin intervención manual.

---

## Índice

1. [Qué hace este sistema](#qué-hace-este-sistema)
2. [Dueño del sistema](#dueño-del-sistema)
3. [Seguridad — NUNCA tocar esto](#seguridad--nunca-tocar-esto)
4. [Arquitectura general](#arquitectura-general)
5. [Flujo completo de un NCO nuevo](#flujo-completo-de-un-nco-nuevo)
6. [nco-guayas.json — base de datos](#nco-guayasjson--base-de-datos)
7. [precios.json — catálogo de precios](#preciosjson--catálogo-de-precios)
8. [generar_proforma.py — script principal](#generar_proformapy--script-principal)
9. [scripts/scrape_nco.py — scraper](#scriptscrape_ncopy--scraper)
10. [scripts/upload_proforma.py — subida al portal](#scriptsupload_proformapy--subida-al-portal)
11. [monitor.py — orquestador local](#monitorpy--orquestador-local)
12. [firmar.py — firma standalone](#firmarpy--firma-standalone)
13. [PWA — index.html + sw.js + manifest.json](#pwa--indexhtml--swjs--manifestjson)
14. [GitHub Actions — workflows](#github-actions--workflows)
15. [GitHub Secrets requeridos](#github-secrets-requeridos)
16. [Catálogo de precios actual](#catálogo-de-precios-actual)
17. [Cómo cambiar la fecha de una proforma existente](#cómo-cambiar-la-fecha-de-una-proforma-existente)
18. [Cómo agregar un nuevo tipo de extintor](#cómo-agregar-un-nuevo-tipo-de-extintor)
19. [Troubleshooting — errores comunes](#troubleshooting--errores-comunes)
20. [Dependencias completas](#dependencias-completas)
21. [Estructura de directorios](#estructura-de-directorios)
22. [Iniciar sesión local](#iniciar-sesión-local)

---

## Qué hace este sistema

PREVIFUEGO participa en procesos de Ínfima Cuantía (NCO) del portal de compras públicas de Ecuador — SERCOP. Cuando una entidad pública de Guayas solicita extintores o recargas, el sistema detecta el proceso, genera automáticamente una proforma en PDF con firma digital válida FirmaEC, y la sube al portal. Todo sin intervención humana.

**Flujo en 5 pasos:**

1. El scraper (`scrape_nco.py`) corre cada hora y monitorea el portal SERCOP buscando NCOs de extintores en Guayas.
2. Si encuentra uno nuevo, actualiza `nco-guayas.json` y hace commit en GitHub.
3. Ese commit dispara `proforma.yml`, que genera el PDF y lo firma electrónicamente con el certificado FirmaEC de Alejandro López.
4. El mismo workflow sube el PDF al portal SERCOP automáticamente con Playwright.
5. Se envía un email de alerta y se muestra notificación en la PWA.

---

## Dueño del sistema

| Campo | Valor |
|---|---|
| **Empresa** | PREVIFUEGO |
| **RUC** | 0952773976001 |
| **Representante** | Alejandro Alberto López Mejía |
| **C.I.** | 0952773976 |
| **Email** | alejosl0801@gmail.com |
| **Teléfono** | 0983583325 |
| **Dirección** | Portete 3007, Gallegos Lara y Leonidas Plaza, Guayaquil |
| **Portal SERCOP** | compraspublicas.gob.ec — usuario: `0952773976001` |

---

## Seguridad — NUNCA tocar esto

### Regla de oro

**Ningún secreto va en el código ni en el repositorio. Todo vive en variables de entorno o GitHub Secrets.**

| Variable | Dónde vive | Qué es | Nunca hacer |
|---|---|---|---|
| `P12_PASS` | Env var + GitHub Secret | Contraseña del certificado digital | Nunca escribir `"Alejo123"` en código |
| `P12_CERT_B64` | Solo GitHub Secret | Certificado P12 en base64 | Nunca commitear el archivo `.p12` |
| `SERCOP_USER` | Env var + GitHub Secret | RUC del proveedor (0952773976001) | Nunca hardcodear en código |
| `SERCOP_PASS` | Env var + GitHub Secret | Clave del portal SERCOP | Nunca en código |
| `GMAIL_USER` | Env var + GitHub Secret | Email del proveedor | Nunca en código |
| `GMAIL_APP_PASS` | Env var + GitHub Secret | App password de Gmail | Nunca en código |

### El certificado P12

El archivo se llama `14775814_identity_0952773976.p12`. Es el certificado FirmaEC de Alejandro López emitido por el BCE (Banco Central del Ecuador).

**Ruta hardcodeada** (en `generar_proforma.py` línea 33 y en `firmar.py`):
```
/root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747/73c7eb7f-14775814_identity_0952773976.p12
```

**Por qué está hardcodeada:** Cuando se creó el sistema, el cert se subió por interfaz de Claude Code a esa ruta. Se dejó fija para que los workflows de GitHub Actions puedan restaurarla exactamente ahí.

**Para obtener `P12_CERT_B64`** (comando a correr una sola vez localmente):
```bash
base64 -w 0 14775814_identity_0952773976.p12
```
Pegar ese resultado como valor del secret `P12_CERT_B64` en GitHub.

**Cómo GitHub Actions restaura el certificado** (en `proforma.yml`):
```bash
mkdir -p /root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747
echo "$P12_B64" | base64 -d > /root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747/73c7eb7f-14775814_identity_0952773976.p12
```

### Archivos excluidos de git (`.gitignore`)
```
output/           # PDFs generados — no commitear
nco-vistos.json   # Registro local de emails enviados
procesados.json   # Registro de NCOs procesados
monitor.log       # Logs del monitor local
*.p12             # EL CERTIFICADO — JAMÁS commitear
```

---

## Arquitectura general

```
┌─────────────────────────────────────────────────────────────────┐
│                       GitHub Actions                            │
│                                                                 │
│  scraper.yml          proforma.yml          pages.yml           │
│  (cada hora L-V)  →   (push a main)    →   (push a main)        │
│       │                    │                    │               │
│       ▼                    ▼                    ▼               │
│  scrape_nco.py    generar_proforma.py    GitHub Pages           │
│  Playwright       WeasyPrint + pyHanko   PWA pública            │
│  SERCOP portal    Certificado FirmaEC    https://alejosl0801    │
│       │                    │             .github.io/SERCOP/    │
│       ▼                    ▼                                    │
│  nco-guayas.json  upload_proforma.py                            │
│  (commit)         Playwright → SERCOP                           │
└─────────────────────────────────────────────────────────────────┘

┌──────────────── Uso Local ──────────────────────────────────────┐
│  monitor.py --loop                                              │
│  └─► scrape_nco.py                                              │
│  └─► generar_proforma.py (--auto-proforma)                      │
│  └─► upload_proforma.py (--auto-upload)                         │
│  └─► enviar_email (Gmail SMTP SSL)                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Flujo completo de un NCO nuevo

```
SERCOP portal (compraspublicas.gob.ec)
  │
  │  [cada hora L-V 6am-9pm Ecuador]
  ▼
scraper.yml
  ├─ instala Playwright + Chromium
  ├─ corre scripts/scrape_nco.py
  │     ├─ abre FrmNCOListado.cpe
  │     ├─ busca "extintor" en filtro
  │     ├─ filtra por cantones de Guayas
  │     ├─ para cada NCO nuevo:
  │     │     ├─ navega al detalle
  │     │     ├─ extrae ítems del HTML
  │     │     └─ si no hay ítems → descarga TDR PDF → PyMuPDF regex
  │     └─ actualiza nco-guayas.json
  ├─ si nco-guayas.json cambió → git commit + push
  └─ si hay NCOs nuevos → email de alerta (monitor.build_email_ncos)

  [push dispara proforma.yml]
  ▼
proforma.yml
  ├─ apt-get: libpango, libcairo, fonts-noto (WeasyPrint)
  ├─ pip: weasyprint, pyhanko, pymupdf, playwright
  ├─ restaura certificado P12 desde P12_CERT_B64 secret
  ├─ corre generar_proforma.py --todos
  │     ├─ lee nco-guayas.json
  │     ├─ para cada NCO no procesado:
  │     │     ├─ calcular_precio() por cada ítem
  │     │     │     ├─ si tiene precio_unitario → usarlo directo
  │     │     │     ├─ si es recarga PQS/CO2 → tarifa × lbs
  │     │     │     └─ si es adquisición → buscar en catálogo
  │     │     ├─ render_html() → HTML completo
  │     │     ├─ WeasyPrint → PDF sin firmar
  │     │     └─ firmar_pdf() → pyHanko → PDF firmado
  │     │           ├─ detecta cajas de firma automáticamente
  │     │           ├─ Firma1 (página 2, proforma)
  │     │           └─ Firma2 (página 3, carta anti-lavado)
  │     └─ guarda en output/Proforma_<codigo>_PREVIFUEGO_signed.pdf
  ├─ para cada PDF firmado:
  │     └─ corre upload_proforma.py
  │           ├─ login en epLoginProveedor.cpe
  │           ├─ navega al NCO específico
  │           └─ sube PDF en campo de oferta
  ├─ sube PDFs como artefactos GitHub Actions (retención 30 días)
  └─ commit procesados.json actualizado
```

---

## nco-guayas.json — base de datos

Archivo central. El scraper lo actualiza automáticamente. Contiene todos los procesos NCO encontrados.

**Estructura completa con todos los campos posibles:**
```json
{
  "actualizado": "2026-08-04T00:00:00.000000+00:00",
  "total": 1,
  "procesos": [
    {
      "id": "",
      "codigo": "NIC-0998610151001-2026-00028",
      "tipo": "Ínfimas Cuantías",
      "fecha_publicacion": "2026-06-17 08:50:00",
      "provincia_canton": "GUAYAS - DAULE",
      "descripcion": "ADQUISICIÓN Y RECARGA DE EXTINTORES PORTÁTILES PARA LAS DIFERENTES ÁREAS DE LA EMPRESA PÚBLICA MUNICIPAL DE TRANSITO Y MOVILIDAD DE DAULE EP",
      "estado": "En Curso",
      "fecha_limite": "2026-06-22 08:56:00",
      "entidad": "EMPRESA PUBLICA MUNICIPAL DE TRÁNSITO Y MOVILIDAD DE DAULE EP",
      "funcionario": "Ing. Johanna Salinas",
      "email": "compraspublicas@atmdaule.gob.ec",
      "url_detalle": "",
      "items": [
        {
          "descripcion": "Recarga de Extintor 10 lbs PQS",
          "agente": "recarga_PQS",
          "capacidad": "10 lbs",
          "unidad": "Unidad",
          "cantidad": 29,
          "precio_unitario": 8.00
        },
        {
          "descripcion": "Adquisición de Extintor 10 lbs CO2",
          "agente": "extintor_CO2",
          "capacidad": "10 lbs",
          "unidad": "Unidad",
          "cantidad": 14,
          "precio_unitario": 39.00
        }
      ]
    }
  ]
}
```

**Campos del proceso:**

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | string | ID interno del portal SERCOP (puede estar vacío) |
| `codigo` | string | Código único del NCO — `NIC-<RUC_entidad>-<año>-<secuencia>` |
| `tipo` | string | Siempre `"Ínfimas Cuantías"` para NCO |
| `fecha_publicacion` | string | Fecha/hora de publicación en el portal |
| `provincia_canton` | string | `"GUAYAS - DAULE"` etc. |
| `descripcion` | string | Descripción del proceso en mayúsculas |
| `estado` | string | `"En Curso"`, `"Cancelado"`, `"Finalizado"` |
| `fecha_limite` | string | Fecha/hora límite para presentar oferta |
| `entidad` | string | Nombre completo de la entidad pública |
| `funcionario` | string | Nombre del responsable del proceso |
| `email` | string | Email de contacto de la entidad |
| `url_detalle` | string | URL del detalle en el portal (puede estar vacío) |
| `items` | array | Lista de ítems del proceso |

**Campos de cada ítem:**

| Campo | Tipo | Descripción |
|---|---|---|
| `descripcion` | string | Descripción del ítem tal como aparece en el TDR |
| `agente` | string | Tipo de agente: `recarga_PQS`, `recarga_CO2`, `extintor_PQS`, `extintor_CO2`, etc. |
| `capacidad` | string | Capacidad en texto: `"10 lbs"`, `"20 lbs"`, etc. |
| `unidad` | string | Unidad de medida: `"Unidad"`, `"Global"`, etc. |
| `cantidad` | number | Cantidad solicitada |
| `precio_unitario` | number | **OPCIONAL** — Si está presente, sobreescribe el cálculo automático |

**Regla de precios (prioridad):**
1. Si el ítem tiene `"precio_unitario"` → se usa ese valor exacto. Esto permite fijar precios manualmente para un proceso específico sin tocar `precios.json`.
2. Si no tiene `"precio_unitario"` → `calcular_precio()` lo calcula automáticamente desde `precios.json`.

---

## precios.json — catálogo de precios

Catálogo maestro. Contiene datos del proveedor (insertados en todas las proformas) y la tabla de precios.

**Estructura completa:**
```json
{
  "version": "2.0",
  "moneda": "USD",
  "proveedor": {
    "nombre": "PREVIFUEGO",
    "ruc": "0952773976001",
    "representante": "Alejandro Alberto López Mejía",
    "ci": "0952773976",
    "email": "alejosl0801@gmail.com",
    "telefono": "",
    "direccion": "Guayaquil, Ecuador"
  },
  "tarifas_por_libra": {
    "recarga_PQS": 0.70,
    "recarga_CO2": 0.70
  },
  "adquisiciones": [
    {
      "id": "adq_pqs_10",
      "agente": "PQS",
      "capacidad_lbs": 10,
      "descripcion": "Extintor PQS 10 lbs (nuevo)",
      "precio_unitario": 16.00,
      "notas": "Con manómetro, certificado UL/FM"
    },
    {
      "id": "adq_pqs_20",
      "agente": "PQS",
      "capacidad_lbs": 20,
      "precio_unitario": 22.00,
      "notas": "Con manómetro, certificado UL/FM"
    },
    {
      "id": "adq_pqs_50",
      "agente": "PQS",
      "capacidad_lbs": 50,
      "precio_unitario": 168.00,
      "notas": "Con manómetro, certificado UL/FM"
    },
    {
      "id": "adq_pqs_150",
      "agente": "PQS",
      "capacidad_lbs": 150,
      "precio_unitario": 220.00,
      "notas": "Con manómetro, certificado UL/FM"
    },
    {
      "id": "adq_co2_10",
      "agente": "CO2",
      "capacidad_lbs": 10,
      "precio_unitario": 39.00,
      "notas": "Sin manómetro — agente CO2"
    },
    {
      "id": "adq_co2_20",
      "agente": "CO2",
      "capacidad_lbs": 20,
      "precio_unitario": 88.00,
      "notas": "Sin manómetro — agente CO2"
    },
    {
      "id": "adq_co2_50",
      "agente": "CO2",
      "capacidad_lbs": 50,
      "precio_unitario": 320.00,
      "notas": "Sin manómetro — agente CO2"
    }
  ]
}
```

**Sección `proveedor`:** Datos que se insertan en el encabezado y en la carta anti-lavado de todas las proformas. Si cambia el RUC, email o dirección, solo hay que actualizar aquí.

**Sección `tarifas_por_libra`:** Precio en USD por libra para recargas. La fórmula es simple: `precio = tarifa × capacidad_lbs`. Ejemplo: recarga PQS 50 lbs = `$0.70 × 50 = $35.00`.

**Sección `adquisiciones`:** Lista de extintores nuevos con precio fijo. El motor de precios busca por `agente` (string exacto: `"PQS"`, `"CO2"`, `"AFFF"`, `"AGUA"`, `"HALON"`) y `capacidad_lbs` (número).

---

## generar_proforma.py — script principal

Es el corazón del sistema. Transforma los datos de `nco-guayas.json` en un PDF profesional con firma digital válida.

### Uso desde CLI

```bash
# Generar una proforma específica (firma incluida)
P12_PASS=Alejo123 python3 generar_proforma.py --nco NIC-0998610151001-2026-00028

# Generar todas las pendientes (las no listadas en procesados.json)
P12_PASS=Alejo123 python3 generar_proforma.py --todos

# Forzar regeneración aunque ya esté en procesados.json
P12_PASS=Alejo123 python3 generar_proforma.py --nco NIC-xxx --forzar

# Solo HTML + PDF sin firma (para probar diseño o cuando no tienes el cert)
python3 generar_proforma.py --nco NIC-xxx --sin-firmar
```

**Salida:** `output/Proforma_<codigo>_PREVIFUEGO_signed.pdf`  
(o `output/proforma_<codigo>_unsigned.pdf` si se usó `--sin-firmar`)

### Constantes y rutas

```python
BASE_DIR     = Path(__file__).parent          # raíz del proyecto
PRECIOS_JSON = BASE_DIR / "precios.json"
NCO_JSON     = BASE_DIR / "nco-guayas.json"
PROCESADOS   = BASE_DIR / "procesados.json"   # gitignored
LOGO_PATH    = BASE_DIR / "logo.png.jpeg"
OUTPUT_DIR   = BASE_DIR / "output"            # gitignored
P12_PATH     = "/root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747/73c7eb7f-14775814_identity_0952773976.p12"
P12_PASS     = os.environ.get("P12_PASS", "").encode()
IVA_RATE     = 0.15   # 15% IVA Ecuador
```

### Funciones de detección de texto

Estas funciones analizan la descripción del ítem para determinar tipo, agente y capacidad:

#### `detect_tipo(text) → str`
Devuelve `"recarga"` o `"adquisicion"` (o `"desconocido"`).

- **Recarga:** palabras clave: `recarga`, `recargar`, `recargue`, `recargas`
- **Adquisición:** palabras clave: `adquisicion`, `adquisición`, `compra`, `suministro`, `nuevo`, `nueva`, `provision`, `provisión`

```python
detect_tipo("Recarga de Extintor 10 lbs PQS")    # → "recarga"
detect_tipo("Adquisición de Extintor 10 lbs CO2") # → "adquisicion"
detect_tipo("Extintor 10 lbs CO2")                # → "desconocido"
```

#### `detect_agente(text) → str | None`
Devuelve el agente extinguidor: `"CO2"`, `"PQS"`, `"AFFF"`, `"AGUA"`, `"HALON"`, o `None`.

| Agente | Palabras clave detectadas |
|---|---|
| `CO2` | CO2, CO₂, DIOXIDO, DIÓXIDO, CARBÓNICO, CARBONICO |
| `PQS` | PQS, POLVO, QUIMICO, QUÍMICO |
| `AFFF` | AFFF, ESPUMA, FOAM |
| `AGUA` | AGUA, WATER |
| `HALON` | HALON, HALÓN, HALOTRON |

#### `extract_lbs(text) → float | None`
Extrae la capacidad en libras usando regex. Soporta formatos:
- `"10 lbs"` → `10.0`
- `"50lb"` → `50.0`
- `"20 libras"` → `20.0`
- `"2.5 lbs"` → `2.5`

```python
extract_lbs("Recarga de Extintor 10 lbs PQS")   # → 10.0
extract_lbs("Extintor CO2 20 lb")                # → 20.0
extract_lbs("Extintor PQS")                      # → None
```

#### `parse_float(s) → float`
Limpia y convierte strings a float. Maneja comas como separadores decimales. Retorna `0.0` si falla.

### Motor de precios — `calcular_precio(item) → ResultadoMatch`

**Árbol de decisión (en orden de prioridad):**

```
¿Tiene "precio_unitario" en el JSON?
  → SÍ: usar ese valor directo (sin recalcular)
  → NO: continuar ↓

¿Es tipo "recarga" Y agente es PQS o CO2 Y se detectaron lbs?
  → SÍ: precio = tarifas_por_libra[agente] × lbs
  → NO: continuar ↓

¿Es tipo "adquisicion" Y hay agente Y hay lbs?
  → SÍ: buscar en adquisiciones[] por agente + capacidad_lbs
       ¿Encontrado? → usar precio_unitario de esa entrada
       ¿No encontrado? → PENDIENTE (agente/lbs no están en catálogo)
  → NO: continuar ↓

¿Es tipo "recarga" pero falta agente o lbs?
  → PENDIENTE (con motivo específico)

¿Es tipo "desconocido"?
  → PENDIENTE (ítem no reconocido)
```

**Clase `ResultadoMatch`:**
```python
class ResultadoMatch:
    descripcion: str      # descripción del ítem (limpia o del JSON)
    unidad: str           # "Unidad", "Global", etc.
    cantidad: float       # cantidad solicitada
    precio_unitario: float # precio por unidad (0.0 si pendiente)
    subtotal: float        # cantidad × precio_unitario
    notas: str            # notas técnicas o mensaje de error
    matched: bool         # True = tiene precio, False = pendiente
    pendiente_tipo: str   # descripción del problema (para el email)
```

### `render_html(nco, filas) → str`

Genera el HTML completo listo para WeasyPrint. Produce **dos secciones** en el mismo HTML:

1. **Página 1 — Proforma Comercial** (`class="page"`):
   - Encabezado con logo + nombre empresa + código NCO + fecha
   - Tabla: Datos de la entidad contratante
   - Tabla: Datos del proveedor (RUC, representante, email)
   - Tabla de ítems con columnas: N°, Descripción, Unidad, Cant., P.Unitario, Subtotal
   - Totales: SUBTOTAL + IVA 15% + TOTAL USD
   - Condiciones comerciales: forma de pago, plazo entrega, validez oferta
   - Garantía y especificaciones técnicas
   - Caja de firma electrónica (`.firma-box`)

2. **Página 2 — Carta Anti-Lavado** (`class="page carta-page"`, con `page-break-before: always`):
   - Encabezado con logo
   - Título: "CARTA DE DECLARACIÓN — Prevención de Lavado de Activos..."
   - Fecha y destinatario (nombre de la entidad)
   - Declaración jurada en 5 puntos
   - Referencia a LOPDEDLAFT y normativa UAFE
   - Caja de firma electrónica

**CSS relevante:**
```css
@page { size: A4; margin: 10mm 12mm; }
.carta-page { page-break-before: always; }
.firma-box { border: 1px solid #555; min-height: 110px; }
.items th { background: #1a3a5c; color: #fff; }
```

**Aviso de ítems pendientes:** Si algún ítem no tiene precio, se muestra un banner rojo en la proforma indicando que no debe enviarse.

### `firmar_pdf(pdf_unsigned, pdf_signed)`

Firma el PDF con pyHanko usando el certificado FirmaEC. Realiza **dos pasadas de firma**:

**Pasada 1 — Firma1 (proforma, página 2):**
- Crea campo `Firma1` en la página 2 (índice 1)
- Firma con `certify=True` y `MDPPerm.FILL_FORMS` — esto es firma MDP (máxima integridad del documento)
- Guarda en archivo temporal `.pass1.pdf`

**Pasada 2 — Firma2 (carta, página 3):**
- Crea campo `Firma2` en la página 3 (índice 2)
- Firma sin certificar (segunda firma)
- Guarda en el archivo final `_signed.pdf`
- Elimina el temporal `.pass1.pdf`

**Detección automática de cajas de firma:**
```python
def firma_box(page_idx, default):
    pg = doc[page_idx]
    drawings = pg.get_drawings()
    # Busca rectángulos dibujados que sean:
    # - anchos > 100 pts
    # - altos > 50 pts
    # - área < 50% de la página (para no tomar el borde completo)
    valid = [d["rect"] for d in drawings
             if (d["rect"].x1-d["rect"].x0) > 100
             and (d["rect"].y1-d["rect"].y0) > 50
             and área < 0.5 × área_página]
    if not valid:
        return default  # coordenadas por defecto
    r = max(valid, key=lambda r: r.y0)  # el más abajo en la página
    return (r.x0, h - r.y1, r.x1, h - r.y0)  # convertir a coords PDF
```

**Sello QR:**
```
Validar únicamente en FirmaEC.
Firmado electrónicamente por:
ALEJANDRO ALBERTO LOPEZ MEJIA
Fecha: YYYY-MM-DD HH:MM:SS UTC
```

**Coordenadas por defecto** (si no detecta cajas):
- Firma1: `(38, 480, 300, 590)` — mitad inferior izquierda página 2
- Firma2: `(34, 280, 360, 390)` — mitad inferior izquierda página 3

### `procesar_nco(nco, firmar=True, forzar=False) → dict`

Orquesta todo el proceso para un NCO:

1. Verifica si ya está en `procesados.json` (sale si sí, a menos que `forzar=True`)
2. Calcula precios con `build_filas()`
3. Identifica ítems pendientes y envía email de alerta si los hay
4. Genera HTML con `render_html()`
5. Convierte a PDF sin firmar con WeasyPrint
6. Si `firmar=True` y no hay pendientes → llama a `firmar_pdf()`
7. Registra el código en `procesados.json`
8. Retorna dict con: `codigo`, `pdf`, `subtotal`, `iva`, `total`, `items_pendientes`

### `enviar_alerta(codigo, entidad, pendientes)`

Envía email via SMTP Gmail SSL (puerto 465) cuando hay ítems sin precio. Usa `GMAIL_USER` y `GMAIL_APP_PASS` de variables de entorno. El email incluye:
- Lista de ítems sin precio con el motivo específico de cada uno
- Instrucciones para resolverlo (agregar a `precios.json` y re-correr)

### `cargar_procesados() / guardar_procesado(codigo)`

`procesados.json` es un array JSON de strings (códigos NCO). Se lee al inicio y se escribe al final de cada procesamiento exitoso. Está en `.gitignore` para evitar conflictos entre ejecuciones locales y en CI.

### Función `fecha_es(d=None) → str`

Convierte una fecha a formato español:
```python
fecha_es()                        # → "6 de agosto de 2026"
fecha_es(date(2026, 6, 20))       # → "20 de junio de 2026"
```

---

## scripts/scrape_nco.py — scraper

Automatiza la navegación del portal SERCOP para extraer procesos de extintores en Guayas.

### Constantes

```python
NCO_URL     = "https://compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/FrmNCOListado.cpe"
DETAIL_BASE = "https://compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/NCORegistroDetalle.cpe"

KEYWORDS = ["extintor", "extintores", "recarga", "incendio"]

GUAYAS_TERMS = [
    "GUAYAS", "GUAYAQUIL", "SAMBORONDON", "DAULE", "MILAGRO",
    "DURAN", "DURÁN", "YAGUACHI", "NARANJAL", "PLAYAS", "EL TRIUNFO",
    "NOBOL", "PEDRO CARBO", "BALZAR", "SANTA LUCIA", "SANTA LUCÍA"
]
```

### Flujo del scraper

```
1. Abrir FrmNCOListado.cpe con Playwright (Chromium headless)
   - User agent: Chrome 120 Windows para evitar bloqueos
   - Locale: es-EC

2. Buscar "extintor" en el campo de búsqueda de la tabla

3. Cambiar paginación a 100 entradas
   - Busca select con opciones "100" o "-1" (todos)

4. Para cada fila de la tabla:
   a. Extraer: tipo, codigo, fecha_pub, provincia_canton,
               descripcion, estado, fecha_limite, entidad
   b. Filtrar: ¿es de Guayas? ¿menciona extintor?
   c. Si pasa filtros:
      - Extraer ID del NCO del href del link
      - Abrir página de detalle (nueva pestaña)
      - Extraer: ítems, email del funcionario, nombre del funcionario
      - Si no hay ítems en HTML → buscar PDF adjunto (TDR)
        → descargar PDF → extraer_items_pdf()

5. Actualizar nco-guayas.json con todos los resultados
```

### Extracción de ítems del TDR PDF — `extraer_items_pdf(pdf_bytes)`

Cuando la tabla HTML no tiene ítems detallados (común en muchos NCOs), el scraper descarga el PDF del TDR (Términos de Referencia) y aplica dos patrones regex:

**Patrón 1** — líneas estructuradas `N° DESCRIPCIÓN CANTIDAD UNIDAD`:
```python
pat1 = re.compile(
    r"^\s*(\d+)[.\s]+([^\n]{10,120}?)\s{2,}(\d+(?:[.,]\d+)?)\s{1,}"
    r"(unidad|u\b|global|servicio|mes|día|hora|kg|lb|lbs|galon|litro)s?",
    re.IGNORECASE | re.MULTILINE
)
```

**Patrón 2** — bloques donde la descripción y la cantidad están en líneas separadas:
- Busca líneas que mencionen extintor (`is_extintor()`)
- Busca cantidad en las 5 líneas siguientes con regex `^\d+\s*(unidad|lbs?...)?`

**Deduplicación:** Filtra ítems con misma descripción (case insensitive).

### Funciones de filtro

```python
is_guayas(text)  # True si el texto contiene algún término de GUAYAS_TERMS
is_extintor(text) # True si el texto contiene alguna palabra de KEYWORDS
clean(text)       # Elimina tags HTML y normaliza espacios
```

---

## scripts/upload_proforma.py — subida al portal

Automatiza la subida del PDF firmado al portal SERCOP usando Playwright.

### Uso

```bash
SERCOP_USER=0952773976001 SERCOP_PASS=<clave_portal> \
  python3 scripts/upload_proforma.py \
  --nco NIC-0998610151001-2026-00028 \
  --pdf output/Proforma_NIC-0998610151001-2026-00028_PREVIFUEGO_signed.pdf
```

### Códigos de salida

| Código | Significado |
|---|---|
| `exit 0` | Subida exitosa |
| `exit 1` | Error de login, PDF no encontrado, u otro error |
| `exit 2` | El proceso requiere subida manual (estado no permite automatización) |

### Flujo interno

```
1. Validar que SERCOP_USER y SERCOP_PASS estén definidos
2. Validar que el PDF existe en disco

3. Abrir Chromium headless
   - User agent: Chrome 120 Windows

4. Login en epLoginProveedor.cpe
   - Intentar múltiples selectores para el campo RUC:
     #rucEmpresa, #usuario, #ruc, input[name='rucEmpresa'], input[type='text']
   - Intentar múltiples selectores para contraseña:
     #contrasena, #password, #clave, input[type='password']
   - Click en botón Ingresar (múltiples selectores)
   - Verificar login: si URL contiene "login" → falló

5. Aceptar cookies si aparece el banner

6. Navegar a FrmNCOListado.cpe
   - Buscar el NCO en el campo de filtro
   - Encontrar la fila con el código exacto
   - Click en el link para ir al detalle

7. Adjuntar el PDF
   - Buscar botón/input de carga: "Adjuntar", "Subir", "Proforma", input[type='file']
   - Si es input[type='file'] → set_input_files(pdf_path)
   - Si es botón → click → esperar dialog de archivo → seleccionar
   - Confirmar/guardar la carga

8. Verificar éxito → exit 0
   Si el estado no permite adjuntar → exit 2
```

### URLs del portal SERCOP

```python
LOGIN_URL = "https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/EP/epLoginProveedor.cpe"
NCO_LIST  = "https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/FrmNCOListado.cpe"
```

---

## monitor.py — orquestador local

Para correr el sistema manualmente desde tu PC sin GitHub Actions.

### Uso

```bash
# Una verificación única
GMAIL_USER=alejosl0801@gmail.com GMAIL_APP_PASS=<app_pass> python3 monitor.py

# Loop continuo cada 2 horas
GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py --loop --intervalo 120

# Con generación automática de proforma al detectar NCO nuevo
P12_PASS=Alejo123 GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py --auto-proforma

# Con generación Y subida automática al portal
P12_PASS=Alejo123 GMAIL_USER=... GMAIL_APP_PASS=... \
  SERCOP_USER=0952773976001 SERCOP_PASS=... \
  python3 monitor.py --auto-proforma --auto-upload
```

### Archivos que usa

| Archivo | Descripción | En git |
|---|---|---|
| `nco-vistos.json` | Códigos NCO ya notificados por email (local) | NO (gitignored) |
| `monitor.log` | Log con timestamps UTC | NO (gitignored) |

### Funciones exportadas (usadas por `scraper.yml`)

#### `build_email_ncos(nuevos) → (asunto, html, texto)`

Construye el email de alerta para nuevos NCOs. Devuelve una tupla de 3 strings:
- `asunto`: línea de asunto del email
- `html`: cuerpo en HTML con tabla de procesos
- `texto`: versión en texto plano

#### `enviar_email(asunto, html, texto)`

Envía el email via SMTP Gmail SSL en puerto 465. Requiere `GMAIL_USER` y `GMAIL_APP_PASS` como variables de entorno.

```python
# Ejemplo de uso desde scraper.yml:
from monitor import build_email_ncos, enviar_email
asunto, html, texto = build_email_ncos(nuevos)
enviar_email(asunto, html, texto)
```

---

## firmar.py — firma standalone

Script standalone para firma manual/debug. Contiene rutas hardcodeadas al HTML y PDF del NCO de Daule.

**No usar en producción.** La función `firmar_pdf()` en `generar_proforma.py` tiene la misma lógica pero mejorada con detección automática de cajas de firma.

**Cuándo usar `firmar.py`:** Solo para debugging rápido cuando necesitas re-firmar un PDF específico sin pasar por todo el flujo de `generar_proforma.py`.

---

## PWA — index.html + sw.js + manifest.json

Aplicación web progresiva desplegada en GitHub Pages.

**URL:** `https://alejosl0801.github.io/SERCOP/`

### `index.html`

Interfaz de monitoreo. Funcionalidades:
- Fetch de `nco-guayas.json` desde GitHub Pages
- Muestra lista de procesos NCO con estado, entidad, fecha límite
- Botón para registrar el dispositivo para notificaciones push
- Funciona offline (caché del Service Worker)
- Instalable como app nativa en Android/iOS

### `sw.js` — Service Worker

Tres eventos manejados:

**`install`:**
```javascript
// Cachea estos assets estáticos en el install:
// ['/', '/index.html', '/manifest.json']
// Usa Promise.allSettled para no fallar si alguno falla
```

**`fetch`:**
```javascript
// Solo intercepta URLs HTTP/HTTPS (no chrome-extension:// ni otros)
// Strategy: Cache First → Network Fallback
if (!event.request.url.startsWith('http')) return; // guardia de seguridad
```

**`push`:**
```javascript
// Muestra notificación con:
// - título: data.title
// - cuerpo: data.body
// - icono: /manifest.json icon
// Envuelto en try/catch para no crashear el SW
```

### `manifest.json`

Configuración de la PWA:
```json
{
  "name": "PREVIFUEGO Monitor",
  "short_name": "PREVIFUEGO",
  "start_url": "/SERCOP/",
  "display": "standalone",
  "background_color": "#1a3a5c",
  "theme_color": "#1a3a5c"
}
```

---

## GitHub Actions — workflows

### `scraper.yml` — NCO Scraper

**Archivo:** `.github/workflows/scraper.yml`

**Triggers:**
- Schedule: `0 11-23,0-2 * * 1-5` (cada hora L-V 6am–9pm Ecuador, UTC-5 → UTC 11-02)
- `workflow_dispatch` (manual)

**Permisos:** `contents: write` (para poder hacer commit)

**Pasos:**

| Paso | Descripción |
|---|---|
| Checkout | `actions/checkout@v4` con token |
| Setup Python | 3.11 con cache de pip |
| Instalar dependencias | `playwright pymupdf` + Chromium |
| Correr scraper | `python3 scripts/scrape_nco.py` (timeout 10 min) |
| Commit si cambió | `git add nco-guayas.json` → commit → push (solo si hay diff) |
| Notificar por email | Compara con `nco-vistos-ci.json`, si hay nuevos → llama a `monitor.build_email_ncos` → `enviar_email` |

**Secrets usados:** `GMAIL_USER`, `GMAIL_APP_PASS`, `GITHUB_TOKEN` (automático)

**Mensaje de commit automático:** `"bot: actualizar nco-guayas.json 2026-08-04 15:30 UTC"`

---

### `proforma.yml` — Generar, Firmar y Subir

**Archivo:** `.github/workflows/proforma.yml`

**Triggers:**
- Push a `main`/`master` cuando cambia `nco-guayas.json`
- `workflow_dispatch` con inputs:
  - `nco` (string): código NCO específico, vacío = todos
  - `forzar` (boolean): reprocesar aunque ya esté en `procesados.json`

**Permisos:** `contents: write`

**Pasos detallados:**

```yaml
1. Checkout (actions/checkout@v4)

2. Setup Python 3.11

3. apt-get install (para WeasyPrint):
   libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b
   libfontconfig1 libcairo2 libgdk-pixbuf2.0-0
   fonts-liberation fonts-noto

4. pip install:
   weasyprint pyhanko pyhanko-certvalidator pymupdf playwright
   + playwright install chromium --with-deps

5. Restaurar certificado P12:
   mkdir -p /root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747
   echo "$P12_B64" | base64 -d > <ruta_hardcodeada>

6. Generar y firmar proformas:
   python3 generar_proforma.py --todos
   (o --nco <codigo> si se especificó en el input)
   (+ --forzar si se activó)

7. Subir al portal SERCOP:
   Para cada PDF firmado en output/:
     python3 scripts/upload_proforma.py --nco <codigo> --pdf <path>

8. Artefactos GitHub Actions:
   Sube output/Proforma_*_signed.pdf
   Retención: 30 días
   Nombre: proformas-<run_number>

9. Commit procesados.json:
   git add procesados.json nco-vistos-ci.json
   git commit -m "bot: actualizar procesados.json ..."
   git push
```

**Secrets usados:** `P12_PASS`, `P12_CERT_B64`, `GMAIL_USER`, `GMAIL_APP_PASS`, `SERCOP_USER`, `SERCOP_PASS`

---

### `pages.yml` — Deploy PWA

**Archivo:** `.github/workflows/pages.yml`

**Trigger:** Push a `main` cuando cambia `index.html`, `sw.js`, `manifest.json` o assets.

**Qué hace:** Despliega la PWA en GitHub Pages usando el workflow estándar `actions/deploy-pages`.

**Resultado:** La app queda disponible en `https://alejosl0801.github.io/SERCOP/`

---

### `enable-pages.yml` — Activar GitHub Pages (una sola vez)

**Archivo:** `.github/workflows/enable-pages.yml`

Solo se usa una vez para activar GitHub Pages via API. Después ya no es necesario.

**Cómo activar:**
1. Ir a `https://github.com/alejosl0801/SERCOP/actions/workflows/enable-pages.yml`
2. Click en "Run workflow"

**Alternativa manual:** Settings → Pages → Source → GitHub Actions

---

## GitHub Secrets requeridos

Configurar en: `https://github.com/alejosl0801/SERCOP/settings/secrets/actions`

| Secret | Valor | Descripción |
|---|---|---|
| `GMAIL_USER` | `alejosl0801@gmail.com` | Email remitente para alertas |
| `GMAIL_APP_PASS` | `xxxx xxxx xxxx xxxx` | App password de Gmail (16 chars, sin espacios). Generar en: Google Account → Seguridad → Verificación en 2 pasos → Contraseñas de aplicaciones |
| `P12_PASS` | `Alejo123` | Contraseña del certificado digital FirmaEC |
| `P12_CERT_B64` | (larga cadena base64) | Certificado P12 en base64. Obtener con: `base64 -w 0 14775814_identity_0952773976.p12` |
| `SERCOP_USER` | `0952773976001` | RUC del proveedor (usuario del portal SERCOP) |
| `SERCOP_PASS` | (clave del portal) | Contraseña del portal compraspublicas.gob.ec |

**Para generar el App Password de Gmail:**
1. Ir a myaccount.google.com → Seguridad
2. Activar verificación en 2 pasos si no está activa
3. Buscar "Contraseñas de aplicaciones"
4. Crear una nueva → seleccionar "Correo" y "Windows" → Generar
5. Copiar los 16 caracteres (sin espacios) al secret `GMAIL_APP_PASS`

---

## Catálogo de precios actual

### Recargas (precio calculado por libra)

| Agente | Tarifa/lb | Ejemplo 10 lbs | Ejemplo 50 lbs |
|---|---|---|---|
| PQS | $0.70/lb | $7.00 | $35.00 |
| CO2 | $0.70/lb | $7.00 | $35.00 |

### Adquisiciones (precio fijo)

| Agente | Capacidad | Precio unitario | Notas |
|---|---|---|---|
| PQS | 10 lbs | $16.00 | Con manómetro, cert. UL/FM |
| PQS | 20 lbs | $22.00 | Con manómetro, cert. UL/FM |
| PQS | 50 lbs | $168.00 | Con manómetro, cert. UL/FM |
| PQS | 150 lbs | $220.00 | Con manómetro, cert. UL/FM |
| CO2 | 10 lbs | $39.00 | Sin manómetro — agente CO2 |
| CO2 | 20 lbs | $88.00 | Sin manómetro — agente CO2 |
| CO2 | 50 lbs | $320.00 | Sin manómetro — agente CO2 |
| AGUA | 2.5 gal | $45.00 | — |
| AFFF | 2.5 gal | $55.00 | — |

**IVA:** 15% sobre el subtotal (constante `IVA_RATE = 0.15` en `generar_proforma.py`)

---

## Cómo cambiar la fecha de una proforma existente

**CRÍTICO: NO regenerar desde cero.** Si el PDF ya tiene el formato correcto (especialmente si fue editado manualmente o viene de una versión diferente de la plantilla), regenerar desde cero puede producir un formato diferente. Siempre editar el PDF existente con PyMuPDF.

### Procedimiento completo

```python
import fitz
import sys
sys.path.insert(0, '/home/user/SERCOP')  # ajustar según la ruta
from pathlib import Path

pdf_original = Path("output/Proforma_NIC-xxx_PREVIFUEGO_signed.pdf")
pdf_editado  = Path("output/proforma_editado.pdf")
pdf_limpio   = Path("output/proforma_sin_acroform.pdf")
pdf_final    = Path("output/Proforma_NIC-xxx_PREVIFUEGO_4ago_signed.pdf")

fecha_vieja = "20 de junio de 2026"
fecha_nueva = "4 de agosto de 2026"

# ── PASO 1: Reemplazar la fecha con redacción ──────────────────────────────
doc = fitz.open(str(pdf_original))

for page in doc:
    hits = page.search_for(fecha_vieja)
    if not hits:
        continue
    # Guardar coordenadas ANTES de redactar
    coords = [(r.x0, r.y1 - 1, r) for r in hits]
    # Tapar con blanco
    for r in hits:
        page.add_redact_annot(r, fill=(1, 1, 1))
    page.apply_redactions()
    # Insertar texto nuevo en la misma posición
    for x0, y1, r in coords:
        page.insert_text(
            (x0, y1),
            fecha_nueva,
            fontsize=10,
            color=(0, 0, 0)
        )

# IMPORTANTE: guardar en archivo NUEVO, no sobreescribir
doc.save(str(pdf_editado))
doc.close()
print(f"Fecha reemplazada → {pdf_editado.name}")

# ── PASO 2: Eliminar AcroForm (campos de firma del PDF original) ───────────
# Los campos de firma existentes bloquean que pyHanko agregue firmas nuevas.
# Hay que eliminar el AcroForm antes de re-firmar.
doc2 = fitz.open(str(pdf_editado))
catalog_xref = doc2.pdf_catalog()
doc2.xref_set_key(catalog_xref, "AcroForm", "null")

# También eliminar anotaciones de firma de cada página
for page in doc2:
    annots = list(page.annots())
    for annot in annots:
        if annot.type[0] in (17, 19):  # Widget y Signature
            page.delete_annot(annot)

doc2.save(str(pdf_limpio))
doc2.close()
print(f"AcroForm eliminado → {pdf_limpio.name}")

# ── PASO 3: Re-firmar con pyHanko ──────────────────────────────────────────
import os
os.environ["P12_PASS"] = "Alejo123"  # o leer desde env var

from generar_proforma import firmar_pdf
firmar_pdf(pdf_limpio, pdf_final)
print(f"Re-firmado → {pdf_final.name}")
```

### Por qué hay que eliminar el AcroForm

El PDF firmado originalmente tiene un `AcroForm` con los campos `Firma1` y `Firma2`. pyHanko al intentar agregar nuevos campos de firma detecta que ya existen y lanza:
```
SigningError: Signature field with name Firma1 appears to be filled already
```

Al eliminar el `AcroForm` del catálogo del PDF, se borra esa referencia y pyHanko puede crear campos nuevos sin conflicto.

### Por qué no sobreescribir el original

PyMuPDF lanza este error al intentar guardar en el mismo archivo:
```
ValueError: save to original must be incremental
```
El guardado incremental preserva la firma original (que ya no queremos). Siempre guardar en un archivo nuevo.

---

## Cómo agregar un nuevo tipo de extintor

### Caso 1: Nuevo tamaño de extintor existente (ej: CO2 de 30 lbs)

Editar `precios.json`, agregar en el array `adquisiciones`:
```json
{
  "id": "adq_co2_30",
  "agente": "CO2",
  "capacidad_lbs": 30,
  "descripcion": "Extintor CO2 30 lbs (nuevo)",
  "precio_unitario": 150.00,
  "notas": "Sin manómetro — agente CO2"
}
```

El campo `agente` debe ser exactamente `"CO2"` (así lo retorna `detect_agente()`).

### Caso 2: Nuevo agente extintor (ej: AFFF en libras)

**Paso 1:** Si es una recarga, agregar tarifa en `precios.json`:
```json
"tarifas_por_libra": {
  "recarga_PQS": 0.70,
  "recarga_CO2": 0.70,
  "recarga_AFFF": 1.20
}
```

**Paso 2:** Si el agente no es reconocido por `detect_agente()`, actualizar esa función en `generar_proforma.py`:
```python
def detect_agente(text: str) -> str | None:
    t = text.upper()
    ...
    if "AFFF" in t or "ESPUMA" in t or "FOAM" in t:
        return "AFFF"
    # Agregar nuevo agente:
    if "NUEVO_AGENTE" in t or "KEYWORD" in t:
        return "NUEVO_AGENTE"
```

**Agentes ya soportados:** `PQS`, `CO2`, `AFFF`, `AGUA`, `HALON`

### Caso 3: Precio fijo para un proceso específico (sin tocar el catálogo)

Editar `nco-guayas.json` y agregar `"precio_unitario"` directamente al ítem:
```json
{
  "descripcion": "Recarga de Extintor 30 lbs CO2",
  "agente": "recarga_CO2",
  "capacidad": "30 lbs",
  "unidad": "Unidad",
  "cantidad": 2,
  "precio_unitario": 25.00
}
```
Este precio sobreescribe cualquier cálculo automático.

---

## Troubleshooting — errores comunes

### `ModuleNotFoundError: No module named 'qrcode'`
```bash
pip install qrcode
```

### `ModuleNotFoundError: No module named 'fitz'`
```bash
pip install pymupdf
```

### `ModuleNotFoundError: No module named 'weasyprint'`
```bash
# Ubuntu/Debian primero:
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
  libfontconfig1 libcairo2 libgdk-pixbuf2.0-0 fonts-liberation fonts-noto
# Luego pip:
pip install weasyprint
```

### `SigningError: Signature field with name Firma1 appears to be filled already`
El PDF ya tiene firmas. Hay que eliminar el AcroForm antes de re-firmar. Ver sección "Cómo cambiar la fecha de una proforma existente" — Paso 2.

### `ValueError: save to original must be incremental` (PyMuPDF)
Estás intentando guardar en el mismo archivo que abriste con `fitz.open()`. Siempre usar un path diferente para el archivo de salida:
```python
doc.save("nuevo_archivo.pdf")  # ✅
doc.save("mismo_archivo.pdf")  # ❌ si ese archivo es el que abriste
```

### `P12_PASS no definido — PDF no firmado`
La variable de entorno no está seteada. Correr con:
```bash
P12_PASS=Alejo123 python3 generar_proforma.py --nco NIC-xxx
```

### `ERROR: NIC-xxx no encontrado`
El código NCO no está en `nco-guayas.json`. Verificar que el scraper haya corrido y que el código sea exacto:
```bash
python3 -c "import json; [print(p['codigo']) for p in json.load(open('nco-guayas.json'))['procesos']]"
```

### `GMAIL_USER/GMAIL_APP_PASS no configurados — alerta no enviada`
Variables de entorno no definidas. Para modo de prueba usar `--sin-firmar` y no importa. Para producción, definir las variables.

### Playwright timeout al scraper
El portal SERCOP puede tardar. El timeout está en 30s por defecto. Si falla consistentemente, puede ser que el portal esté caído o que cambió la estructura HTML. Revisar manualmente la URL del portal.

### Login fallido en upload_proforma.py
- Verificar `SERCOP_USER` (debe ser el RUC: `0952773976001`) y `SERCOP_PASS`
- El portal puede haber cambiado los selectores del form de login
- Probar en modo no-headless agregando `headless=False` al llamar `upload()`

### `exit 2` en upload_proforma.py
El NCO ya pasó su fecha límite o tiene un estado que no permite adjuntar proformas. Requiere intervención manual en el portal.

### WeasyPrint genera PDF con 4 páginas en vez de 3
La tabla de ítems es muy larga y se corta en dos páginas. Soluciones:
- Reducir `font-size` en `.items td { font-size: 8px; }`
- Reducir `padding` en `table td, table th { padding: 2px 3px; }`
- Usar `page-break-inside: avoid` en `tr`

### El PDF firmado se ve distinto al original
Esto pasa cuando se regenera desde cero en vez de editar el original. La plantilla HTML actual en `generar_proforma.py` genera un formato diferente al que tenía el PDF original de junio 2026. Para preservar el formato original, siempre editar con PyMuPDF en vez de regenerar.

---

## Dependencias completas

### Python
```bash
pip install weasyprint pyhanko pyhanko-certvalidator pymupdf playwright qrcode
playwright install chromium --with-deps
```

| Paquete | Versión mínima | Para qué |
|---|---|---|
| `weasyprint` | cualquiera reciente | HTML → PDF |
| `pyhanko` | cualquiera reciente | Firma digital PDF |
| `pyhanko-certvalidator` | cualquiera reciente | Validación del certificado |
| `pymupdf` | cualquiera reciente | Edición de PDFs, extracción de texto |
| `playwright` | cualquiera reciente | Automatización del navegador |
| `qrcode` | cualquiera reciente | Generación del QR en el sello de firma |

### Sistema (Ubuntu/Debian — requeridas por WeasyPrint)
```bash
sudo apt-get install -y \
  libpango-1.0-0 \
  libpangoft2-1.0-0 \
  libharfbuzz0b \
  libfontconfig1 \
  libcairo2 \
  libgdk-pixbuf2.0-0 \
  fonts-liberation \
  fonts-noto
```

### Para sesión local en Claude Code
```bash
git clone https://github.com/alejosl0801/SERCOP.git
cd SERCOP
pip install weasyprint pyhanko pyhanko-certvalidator pymupdf playwright qrcode
playwright install chromium --with-deps
```

---

## Estructura de directorios

```
SERCOP/
│
├── generar_proforma.py      # Script principal: JSON → HTML → PDF → firma
├── firmar.py                # Firma standalone (uso manual/debug solamente)
├── monitor.py               # Orquestador local + funciones de email
├── precios.json             # Catálogo de precios + datos del proveedor
├── nco-guayas.json          # Base de datos de procesos NCO (auto-actualizada por scraper)
├── logo.png.jpeg            # Logo PREVIFUEGO (se incrusta en base64 en el HTML)
│
├── index.html               # PWA: interfaz de monitoreo
├── sw.js                    # Service Worker: caché offline + notificaciones push
├── manifest.json            # PWA manifest: nombre, iconos, colores
│
├── scripts/
│   ├── scrape_nco.py        # Scraper Playwright del portal SERCOP
│   └── upload_proforma.py   # Uploader Playwright al portal SERCOP
│
├── .github/
│   └── workflows/
│       ├── scraper.yml       # Cron: scraper cada hora L-V
│       ├── proforma.yml      # Trigger: generar+firmar+subir cuando cambia nco-guayas.json
│       ├── pages.yml         # Deploy PWA en GitHub Pages
│       ├── enable-pages.yml  # One-time: activar GitHub Pages via API
│       └── nco-monitor.yml   # Monitor adicional (ver contenido con cat)
│
├── CLAUDE.md                # Este archivo — documentación del sistema
│
├── output/                  # PDFs generados — GITIGNORED
│   └── Proforma_<codigo>_PREVIFUEGO_signed.pdf
│
├── procesados.json          # Registro de NCOs ya procesados — GITIGNORED
├── nco-vistos.json          # NCOs ya notificados por email (local) — GITIGNORED
├── nco-vistos-ci.json       # NCOs ya notificados en CI — en git
└── monitor.log              # Log del monitor local — GITIGNORED
```

---

## Iniciar sesión local

### Clonar y configurar

```bash
git clone https://github.com/alejosl0801/SERCOP.git
cd SERCOP
pip install weasyprint pyhanko pyhanko-certvalidator pymupdf playwright qrcode
playwright install chromium --with-deps
```

### Iniciar Claude Code

```bash
claude
```

### Prompt de inicio recomendado

```
Lee el archivo CLAUDE.md y todos los archivos del repositorio.
Entiende el sistema completo: scraper, generación de proformas, firma digital,
subida al portal SERCOP, workflows de GitHub Actions y la PWA.
Cuando termines, confirma que entendiste todo y dime qué hace falta configurar
para que el sistema corra completamente automático.
```

### Variables de entorno para uso local

```bash
export P12_PASS=Alejo123
export GMAIL_USER=alejosl0801@gmail.com
export GMAIL_APP_PASS=<app_password_16_chars>
export SERCOP_USER=0952773976001
export SERCOP_PASS=<clave_portal>
```

O en un archivo `.env` (que NO se commitea — agregar a `.gitignore`):
```
P12_PASS=Alejo123
GMAIL_USER=alejosl0801@gmail.com
GMAIL_APP_PASS=xxxx xxxx xxxx xxxx
SERCOP_USER=0952773976001
SERCOP_PASS=mi_clave_portal
```
Y cargarlo con:
```bash
export $(cat .env | xargs)
```

### Certificado P12 en sesión local

Cada sesión local empieza desde cero. Si el certificado no está en la ruta hardcodeada, la firma fallará. Hay dos opciones:

**Opción A — Subir el cert por interfaz de Claude Code:**
Arrastrarlo en el chat. Claude Code lo guarda en `/root/.claude/uploads/<session_id>/<uuid>-<nombre>.p12`.
Si la ruta no coincide con la hardcodeada, actualizar `P12_PATH` en `generar_proforma.py`.

**Opción B — Copiarlo manualmente:**
```bash
mkdir -p /root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747
cp 14775814_identity_0952773976.p12 \
  /root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747/73c7eb7f-14775814_identity_0952773976.p12
```

### Comandos rápidos de verificación

```bash
# Ver qué NCOs hay cargados
python3 -c "import json; [print(p['codigo'], '-', p['entidad']) for p in json.load(open('nco-guayas.json'))['procesos']]"

# Ver precios calculados para un NCO
python3 -c "
import json
from generar_proforma import build_filas
data = json.load(open('nco-guayas.json'))
nco = data['procesos'][0]
for f in build_filas(nco['items']):
    status = '✅' if f.matched else '⚠'
    print(f'{status} {f.descripcion}: x{int(f.cantidad)} × \${f.precio_unitario:.2f} = \${f.subtotal:.2f}')
"

# Generar proforma sin firma (para revisar el PDF)
python3 generar_proforma.py --nco NIC-0998610151001-2026-00028 --sin-firmar

# Generar proforma con firma
P12_PASS=Alejo123 python3 generar_proforma.py --nco NIC-0998610151001-2026-00028

# Correr scraper una vez
python3 scripts/scrape_nco.py
```
