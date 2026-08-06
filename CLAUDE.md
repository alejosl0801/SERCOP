# PREVIFUEGO — Sistema Automático SERCOP

## Qué hace este sistema

Monitorea el portal de compras públicas de Ecuador (SERCOP) buscando procesos de Ínfima Cuantía (NCO) de extintores en la provincia de Guayas. Cuando encuentra un proceso nuevo:

1. Lo guarda en `nco-guayas.json`
2. Genera una proforma PDF firmada electrónicamente
3. La sube al portal SERCOP automáticamente
4. Envía email de alerta
5. Muestra notificación push en la app PWA

Todo corre en GitHub Actions sin intervención manual.

---

## Dueño del sistema

- **Empresa:** PREVIFUEGO
- **RUC:** 0952773976001
- **Representante:** Alejandro Alberto López Mejía — C.I. 0952773976
- **Email:** alejosl0801@gmail.com
- **Teléfono:** 0983583325
- **Dirección:** Portete 3007, Gallegos Lara y Leonidas Plaza, Guayaquil

---

## Seguridad — NUNCA tocar esto

| Variable | Dónde vive | Nunca hacer |
|---|---|---|
| `P12_PASS` | Solo como env var o GitHub Secret | Nunca escribir en código |
| `P12_CERT_B64` | Solo GitHub Secret | Nunca commitear el .p12 |
| `SERCOP_USER` / `SERCOP_PASS` | Solo env var o GitHub Secret | Nunca en código |
| `GMAIL_USER` / `GMAIL_APP_PASS` | Solo env var o GitHub Secret | Nunca en código |

El certificado `.p12` se llama `14775814_identity_0952773976.p12`. En GitHub Actions se restaura desde `P12_CERT_B64` (base64) a esta ruta que está **hardcodeada** en `generar_proforma.py` y `firmar.py`:

```
/root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747/73c7eb7f-14775814_identity_0952773976.p12
```

Para obtener `P12_CERT_B64`: `base64 -w 0 14775814_identity_0952773976.p12`

---

## Archivos principales

### `nco-guayas.json`

Base de datos de todos los procesos NCO encontrados por el scraper. Se actualiza automáticamente en cada ejecución del scraper.

**Estructura completa:**
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
      "descripcion": "ADQUISICIÓN Y RECARGA DE EXTINTORES...",
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
        }
      ]
    }
  ]
}
```

**Regla de precios en ítems:**
- Si el ítem tiene `"precio_unitario"` → se usa ese valor exacto sin recalcular.
- Si no tiene `"precio_unitario"` → `calcular_precio()` en `generar_proforma.py` lo calcula automáticamente usando `precios.json`.

---

### `precios.json`

Catálogo maestro de precios. Contiene también los datos del proveedor que se insertan en todas las proformas.

**Estructura:**
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
    }
  ]
}
```

**Para agregar un precio nuevo:**
- Recargas: ajustar `tarifas_por_libra.recarga_PQS` o `recarga_CO2` (el precio se multiplica por los lbs del extintor).
- Adquisiciones: agregar un objeto en el array `adquisiciones` con `agente`, `capacidad_lbs` y `precio_unitario`.
- Agentes soportados: `PQS`, `CO2`, `AFFF`, `AGUA`, `HALON`.

---

### `generar_proforma.py`

Script principal. Flujo: `nco-guayas.json` → HTML → PDF (WeasyPrint) → firma digital (pyHanko). Genera dos páginas: la proforma comercial y la carta de declaración anti-lavado de activos.

**Uso:**
```bash
# Generar una proforma específica
P12_PASS=Alejo123 python3 generar_proforma.py --nco NIC-0998610151001-2026-00028

# Generar todas las pendientes (las no listadas en procesados.json)
P12_PASS=Alejo123 python3 generar_proforma.py --todos

# Forzar regeneración aunque ya esté en procesados.json
P12_PASS=Alejo123 python3 generar_proforma.py --nco NIC-xxx --forzar

# Solo HTML + PDF sin firma (para probar / revisar diseño)
python3 generar_proforma.py --nco NIC-xxx --sin-firmar

# Sin credenciales de Gmail (evitar error de email)
python3 generar_proforma.py --nco NIC-xxx --sin-firmar
```

**Salida:** `output/Proforma_<codigo>_PREVIFUEGO_signed.pdf`

**Funciones clave:**

| Función | Qué hace |
|---|---|
| `calcular_precio(item)` | Detecta tipo/agente/lbs y devuelve precio. Respeta `precio_unitario` si existe en el JSON. |
| `detect_tipo(text)` | Detecta si es `"recarga"` o `"adquisicion"` según palabras clave. |
| `detect_agente(text)` | Detecta agente extintor: `PQS`, `CO2`, `AFFF`, `AGUA`, `HALON`. |
| `extract_lbs(text)` | Extrae capacidad en libras de texto tipo `"10 lbs"`, `"50lb"`, `"20 libras"`. |
| `render_html(nco, filas)` | Genera el HTML completo (proforma + carta anti-lavado) para WeasyPrint. |
| `firmar_pdf(pdf_u, pdf_s)` | Firma el PDF con pyHanko. Detecta automáticamente las cajas de firma por dibujos en el PDF. Hace 2 pasadas: Firma1 (proforma) y Firma2 (carta). |
| `procesar_nco(nco, firmar, forzar)` | Orquesta todo: calcula precios → genera HTML → PDF → firma → registra en `procesados.json`. |
| `enviar_alerta(codigo, entidad, pendientes)` | Envía email si hay ítems sin precio en el catálogo. |

**Lógica de precios (en orden de prioridad):**
1. Si `"precio_unitario"` presente en el ítem JSON → usar ese valor directo.
2. Si es recarga PQS/CO2 con lbs detectables → `tarifa_por_libra × lbs`.
3. Si es adquisición → buscar en `adquisiciones` por `agente + capacidad_lbs`.
4. Si no matchea nada → marcar como PENDIENTE, enviar email de alerta, no firmar.

**Firma digital:**
- Usa pyHanko con certificado FirmaEC (PKCS#12).
- El sello QR dice "Validar únicamente en FirmaEC" con timestamp UTC.
- La firma se certifica con `MDPPerm.FILL_FORMS` (modo MDP — máxima integridad).
- Firma1 en página 2 (proforma), Firma2 en página 3 (carta anti-lavado).
- Las cajas de firma se detectan automáticamente buscando rectángulos dibujados en el PDF. Si no encuentra, usa coordenadas por defecto.

**IVA:** 15% (constante `IVA_RATE = 0.15`).

---

### `precios.json` — catálogo actual de adquisiciones

| Agente | lbs | Precio |
|---|---|---|
| PQS | 10 | $16.00 |
| PQS | 20 | $22.00 |
| PQS | 50 | $168.00 |
| PQS | 150 | $220.00 |
| CO2 | 10 | $39.00 |
| CO2 | 20 | $88.00 |
| CO2 | 50 | $320.00 |
| AGUA | 2.5 gal | $45.00 |
| AFFF | 2.5 gal | $55.00 |

Recargas PQS y CO2: $0.70/lb (ej: recarga 10 lbs = $7.00, recarga 50 lbs = $35.00).

---

### `scripts/scrape_nco.py`

Scraper con Playwright (Chromium headless). Navega el portal SERCOP, filtra por Guayas + palabras clave de extintores, y extrae los datos de cada proceso.

**URLs del portal:**
- Listado NCO: `https://compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/FrmNCOListado.cpe`
- Detalle: `https://compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/NCORegistroDetalle.cpe`

**Palabras clave buscadas:** `extintor`, `extintores`, `recarga`, `incendio`

**Cantones de Guayas monitoreados:** GUAYAQUIL, DAULE, SAMBORONDON, MILAGRO, DURAN, YAGUACHI, NARANJAL, PLAYAS, EL TRIUNFO, NOBOL, PEDRO CARBO, BALZAR, SANTA LUCIA

**Extracción de ítems:** Si la página HTML no tiene ítems detallados, descarga el TDR en PDF adjunto y usa PyMuPDF (`fitz`) para extraer la tabla de ítems con patrones regex.

**Salida:** Actualiza `nco-guayas.json` con los procesos encontrados.

---

### `scripts/upload_proforma.py`

Sube el PDF firmado al portal compraspublicas.gob.ec usando Playwright. Requiere sesión activa del proveedor.

**Uso:**
```bash
SERCOP_USER=0952773976001 SERCOP_PASS=<clave_portal> \
  python3 scripts/upload_proforma.py \
  --nco NIC-0998610151001-2026-00028 \
  --pdf output/Proforma_NIC-0998610151001-2026-00028_PREVIFUEGO_signed.pdf
```

**Códigos de salida:**
- `exit 0` → subida exitosa
- `exit 2` → el proceso requiere subida manual (estado no permite automatización)
- `exit 1` → error de login u otro error

**Flujo interno:**
1. Login en `epLoginProveedor.cpe` con `SERCOP_USER` y `SERCOP_PASS`.
2. Acepta cookies si aparece el banner.
3. Navega al NCO específico.
4. Sube el PDF en el campo de oferta.

---

### `monitor.py`

Orquestador principal para correr localmente. Puede correr el scraper en loop, detectar NCOs nuevos, enviar email y opcionalmente generar y subir proformas.

**Uso:**
```bash
# Una sola verificación
GMAIL_USER=alejosl0801@gmail.com GMAIL_APP_PASS=<app_pass> python3 monitor.py

# Loop cada 2 horas
GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py --loop --intervalo 120

# Con generación automática de proforma al detectar NCO nuevo
P12_PASS=Alejo123 GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py --auto-proforma

# Con generación Y subida automática al portal
P12_PASS=Alejo123 GMAIL_USER=... GMAIL_APP_PASS=... \
  SERCOP_USER=0952773976001 SERCOP_PASS=... \
  python3 monitor.py --auto-proforma --auto-upload
```

**Archivos que usa:**
- `nco-vistos.json` → registro local de NCOs ya notificados (gitignored)
- `monitor.log` → log con timestamps UTC (gitignored)

**Funciones exportadas** (usadas por `scraper.yml`):
- `build_email_ncos(nuevos)` → construye el asunto, HTML y texto plano del email.
- `enviar_email(asunto, html, texto)` → envía via SMTP Gmail SSL puerto 465.

---

### `firmar.py`

Script standalone de firma para uso manual/debug. Tiene rutas hardcodeadas al HTML y PDF del NCO de Daule. Lo usa internamente `generar_proforma.py` (la lógica se duplicó ahí como función `firmar_pdf()`).

**No usar en producción** — usar `generar_proforma.py` que tiene la lógica más robusta con detección automática de cajas de firma.

---

### `index.html` + `sw.js` + `manifest.json`

La PWA (Progressive Web App) de monitoreo. Se despliega en GitHub Pages en:
`https://alejosl0801.github.io/SERCOP/`

**Funcionalidades:**
- Muestra los procesos NCO de `nco-guayas.json` (fetch desde el repo de GitHub Pages).
- Recibe notificaciones push cuando hay un NCO nuevo.
- Instalable en Android/iOS como app nativa.
- Funciona offline (caché del Service Worker).

**`sw.js` — Service Worker:**
- `install` → cachea assets estáticos.
- `fetch` → sirve desde caché si está disponible (solo URLs HTTP/HTTPS).
- `push` → muestra notificación push con título y cuerpo del NCO.
- Usa `Promise.allSettled` para no fallar si alguna caché falla.

---

## GitHub Actions (workflows)

### `scraper.yml` — NCO Scraper

**Cuándo corre:** Cada hora de lunes a viernes, 6am–9pm Ecuador (UTC-5). Cron: `0 11-23,0-2 * * 1-5`. También manualmente con `workflow_dispatch`.

**Qué hace:**
1. Instala Playwright + Chromium.
2. Corre `scripts/scrape_nco.py`.
3. Si `nco-guayas.json` cambió, hace commit y push.
4. Compara con `nco-vistos-ci.json` para detectar procesos nuevos.
5. Si hay nuevos, llama a `monitor.build_email_ncos()` y envía email de alerta.

**Secrets usados:** `GMAIL_USER`, `GMAIL_APP_PASS`, `GITHUB_TOKEN` (automático).

---

### `proforma.yml` — Generar, Firmar y Subir

**Cuándo corre:** Cuando `nco-guayas.json` cambia en `main`/`master`. También manualmente con parámetros opcionales:
- `nco`: código específico (vacío = todos los nuevos)
- `forzar`: boolean para reprocesar ya procesados

**Qué hace:**
1. Instala dependencias del sistema para WeasyPrint (libpango, libcairo, fonts-noto, etc.).
2. Instala dependencias Python: `weasyprint pyhanko pyhanko-certvalidator pymupdf playwright`.
3. **Restaura el certificado P12** desde `P12_CERT_B64` secret a la ruta hardcodeada.
4. Corre `generar_proforma.py --todos` (o `--nco <codigo>`).
5. Para cada PDF firmado generado, corre `upload_proforma.py`.
6. Sube los PDFs como artefactos de GitHub Actions (retención 30 días).
7. Hace commit de `procesados.json` actualizado.

**Secrets usados:** `P12_PASS`, `P12_CERT_B64`, `GMAIL_USER`, `GMAIL_APP_PASS`, `SERCOP_USER`, `SERCOP_PASS`.

---

### `pages.yml` — Deploy PWA

**Cuándo corre:** Cuando cambia `index.html`, `sw.js`, `manifest.json` o assets en `main`.

**Qué hace:** Despliega la PWA en GitHub Pages usando el workflow estándar de Pages.

---

### `nco-monitor.yml`

Workflow adicional de monitoreo (revisar contenido actual con `cat .github/workflows/nco-monitor.yml`).

---

## GitHub Secrets requeridos

Configurar en: `https://github.com/alejosl0801/SERCOP/settings/secrets/actions`

| Secret | Valor / Descripción |
|---|---|
| `GMAIL_USER` | `alejosl0801@gmail.com` |
| `GMAIL_APP_PASS` | Contraseña de app de Gmail (16 chars, sin espacios). Generar en: Google Account → Seguridad → Contraseñas de aplicación |
| `P12_PASS` | `Alejo123` |
| `P12_CERT_B64` | Resultado de `base64 -w 0 14775814_identity_0952773976.p12` |
| `SERCOP_USER` | `0952773976001` (RUC del proveedor) |
| `SERCOP_PASS` | Clave del portal compraspublicas.gob.ec |

---

## Cómo cambiar solo la fecha de una proforma existente

**IMPORTANTE: NO regenerar desde cero.** Si ya existe un PDF firmado y solo hay que cambiar la fecha, usar PyMuPDF para editar el PDF directamente:

```python
import fitz
import os

# 1. Abrir el PDF original
doc = fitz.open("proforma_original_signed.pdf")

fecha_vieja = "20 de junio de 2026"
fecha_nueva = "4 de agosto de 2026"

# 2. Reemplazar fecha en cada página
for page in doc:
    hits = page.search_for(fecha_vieja)
    for rect in hits:
        # Redactar (tapar con blanco) el texto viejo
        page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions()
    
    # Reinsertar el texto nuevo en la misma posición
    hits2 = page.search_for(fecha_vieja)  # ya no encontrará nada
    # Alternativa: calcular posición manualmente o usar las coords de 'hits'
    for rect in hits:  # usar coords guardadas antes de redactar
        page.insert_text(
            (rect.x0, rect.y1 - 1),
            fecha_nueva,
            fontsize=10,
            color=(0, 0, 0)
        )

# 3. Guardar a un archivo NUEVO (no sobreescribir el original)
doc.save("proforma_editada.pdf")
doc.close()

# 4. Eliminar AcroForm (campos de firma del PDF original) antes de re-firmar
import fitz
doc2 = fitz.open("proforma_editada.pdf")
catalog_xref = doc2.pdf_catalog()
doc2.xref_set_key(catalog_xref, "AcroForm", "null")
doc2.save("proforma_sin_acroform.pdf")
doc2.close()

# 5. Re-firmar con firmar_pdf() de generar_proforma.py
from generar_proforma import firmar_pdf
from pathlib import Path
firmar_pdf(Path("proforma_sin_acroform.pdf"), Path("proforma_refirmada_signed.pdf"))
```

**Por qué este proceso:** El PDF firmado tiene anotaciones de firma (`AcroForm`) que bloquean nuevas firmas. Hay que eliminarlas antes de volver a firmar.

---

## Cómo agregar un nuevo tipo de extintor al catálogo

1. Abrir `precios.json`.
2. Agregar una entrada en el array `adquisiciones`:
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
3. Para una recarga de agente nuevo, agregar en `tarifas_por_libra`:
```json
"recarga_AFFF": 1.20
```
4. También actualizar `detect_agente()` en `generar_proforma.py` si el agente no está reconocido aún (AFFF y HALON ya están soportados).

---

## Flujo completo de un NCO nuevo (automático)

```
scraper.yml (cada hora)
  └─► scrape_nco.py
        └─► nco-guayas.json actualizado
              └─► proforma.yml se dispara
                    ├─► generar_proforma.py --todos
                    │     ├─► calcular_precio() por cada ítem
                    │     ├─► render_html() → WeasyPrint → PDF
                    │     └─► firmar_pdf() → pyHanko → PDF firmado
                    ├─► upload_proforma.py (Playwright → portal SERCOP)
                    ├─► Artefacto PDF en GitHub Actions (30 días)
                    └─► commit procesados.json
```

---

## Estructura de directorios

```
SERCOP/
├── generar_proforma.py      # Script principal de generación + firma
├── firmar.py                # Script standalone de firma (uso manual)
├── monitor.py               # Monitoreo continuo + email
├── precios.json             # Catálogo de precios + datos del proveedor
├── nco-guayas.json          # Base de datos de procesos NCO (auto-actualizada)
├── logo.png.jpeg            # Logo PREVIFUEGO (base64 en la proforma)
├── index.html               # PWA frontend
├── sw.js                    # Service Worker de la PWA
├── manifest.json            # Manifest de la PWA
├── scripts/
│   ├── scrape_nco.py        # Scraper Playwright
│   └── upload_proforma.py   # Uploader Playwright al portal SERCOP
├── .github/workflows/
│   ├── scraper.yml          # Cron scraper (cada hora L-V)
│   ├── proforma.yml         # Genera + firma + sube proformas
│   ├── pages.yml            # Deploy PWA a GitHub Pages
│   └── nco-monitor.yml      # Monitor adicional
├── output/                  # PDFs generados (gitignored)
├── procesados.json          # Registro de NCOs ya procesados (gitignored)
├── nco-vistos.json          # NCOs ya notificados por email local (gitignored)
└── nco-vistos-ci.json       # NCOs ya notificados en CI (gitignored)
```

---

## Dependencias Python

```bash
pip install weasyprint pyhanko pyhanko-certvalidator pymupdf playwright qrcode
playwright install chromium --with-deps
```

## Dependencias sistema (Ubuntu/Debian — requeridas por WeasyPrint)

```bash
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
  libfontconfig1 libcairo2 libgdk-pixbuf2.0-0 fonts-liberation fonts-noto
```

---

## Archivos ignorados (no commitear)

Ver `.gitignore`:
- `output/` — PDFs generados
- `nco-vistos.json` — registro local de emails enviados
- `procesados.json` — registro de NCOs procesados
- `monitor.log` — logs del monitor
- `*.p12` — certificado digital

---

## Comando para iniciar sesión local

```bash
git clone https://github.com/alejosl0801/SERCOP.git
cd SERCOP
claude
```

Prompt inicial para la sesión local:
```
Lee el archivo CLAUDE.md y todos los archivos del repositorio.
Entiende el sistema completo: scraper, generación de proformas, firma digital,
subida al portal SERCOP, workflows de GitHub Actions y la PWA.
Cuando termines, confirma que entendiste todo y dime qué hace falta configurar
para que el sistema corra completamente automático.
```
