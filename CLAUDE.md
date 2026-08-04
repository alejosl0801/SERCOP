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

El certificado `.p12` se llama `14775814_identity_0952773976.p12`. En GitHub Actions se restaura desde `P12_CERT_B64` (base64) a la ruta hardcodeada en `generar_proforma.py`:
```
/root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747/73c7eb7f-14775814_identity_0952773976.p12
```

---

## Archivos principales

### `nco-guayas.json`
Base de datos de procesos encontrados. El scraper lo actualiza. Estructura:
```json
{
  "actualizado": "2026-08-04T...",
  "total": 1,
  "procesos": [{
    "codigo": "NIC-0998610151001-2026-00028",
    "entidad": "...",
    "funcionario": "Ing. Johanna Salinas",
    "email": "compraspublicas@atmdaule.gob.ec",
    "items": [
      {"descripcion": "...", "cantidad": 29, "precio_unitario": 8.00}
    ]
  }]
}
```
> Si un ítem tiene `"precio_unitario"` explícito, se usa ese. Si no, se calcula automáticamente ($0.70/lb para recargas).

### `precios.json`
Catálogo de precios. Dos secciones:
- `tarifas_por_libra`: precio/lb para recargas PQS y CO2 (actualmente $0.70)
- `adquisiciones`: precios fijos por extintor nuevo según agente y capacidad

### `generar_proforma.py`
Script principal. Genera HTML → PDF → firma con pyHanko.
```bash
# Generar una proforma específica
P12_PASS=Alejo123 python3 generar_proforma.py --nco NIC-xxx

# Generar todas las pendientes
P12_PASS=Alejo123 python3 generar_proforma.py --todos

# Forzar regeneración aunque ya esté procesada
P12_PASS=Alejo123 python3 generar_proforma.py --nco NIC-xxx --forzar

# Sin firma (para probar)
python3 generar_proforma.py --nco NIC-xxx --sin-firmar
```
Los PDFs se guardan en `output/Proforma_<codigo>_PREVIFUEGO_signed.pdf`.

### `scripts/scrape_nco.py`
Scraper con Playwright. Busca NCOs en SERCOP filtrando por Guayas + palabras clave de extintores. Extrae ítems del TDR en PDF si la página HTML no los tiene.

### `scripts/upload_proforma.py`
Sube el PDF firmado al portal compraspublicas.gob.ec usando Playwright.
```bash
SERCOP_USER=0952773976001 SERCOP_PASS=xxx python3 scripts/upload_proforma.py \
  --nco NIC-xxx --pdf output/Proforma_NIC-xxx_PREVIFUEGO_signed.pdf
```
- `exit 0` = subida exitosa
- `exit 2` = requiere subida manual
- `exit 1` = error

### `monitor.py`
Corre el scraper, detecta NCOs nuevos, envía email y opcionalmente genera proforma y sube.
```bash
GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py
GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py --loop --intervalo 120
P12_PASS=... python3 monitor.py --auto-proforma --auto-upload
```

### `firmar.py`
Script standalone de firma. Lo usa `generar_proforma.py` internamente.

### `index.html` + `sw.js` + `manifest.json`
La PWA. Se despliega en GitHub Pages en:
`https://alejosl0801.github.io/SERCOP/`

---

## GitHub Actions (workflows)

| Archivo | Cuándo corre | Qué hace |
|---|---|---|
| `scraper.yml` | Cada hora L-V 6am-9pm Ecuador | Scraper NCO, commit si hay nuevos, email de alerta |
| `proforma.yml` | Cuando cambia `nco-guayas.json` en main | Genera + firma + sube proformas al portal |
| `pages.yml` | Cuando cambia `index.html`, `sw.js`, etc. | Despliega PWA en GitHub Pages |
| `enable-pages.yml` | Manual (Run workflow) | Activa GitHub Pages una sola vez |

---

## GitHub Secrets requeridos

Ir a: `https://github.com/alejosl0801/SERCOP/settings/secrets/actions`

| Secret | Descripción |
|---|---|
| `GMAIL_USER` | `alejosl0801@gmail.com` |
| `GMAIL_APP_PASS` | Contraseña de app de Gmail (16 chars) |
| `P12_PASS` | `Alejo123` |
| `P12_CERT_B64` | `base64 -w 0 14775814_identity_0952773976.p12` |
| `SERCOP_USER` | `0952773976001` |
| `SERCOP_PASS` | Clave del portal compraspublicas.gob.ec |

---

## Cómo cambiar solo la fecha de una proforma existente

**NO regenerar desde cero.** Usar PyMuPDF para editar el PDF original:
```python
import fitz
doc = fitz.open("proforma_original_signed.pdf")
# Para cada página: search_for("fecha vieja") → add_redact_annot → apply_redactions
# Luego reinsertar texto nuevo con insert_text
# Guardar, eliminar AcroForm, re-firmar con firmar_pdf()
```

---

## Dependencias Python
```bash
pip install weasyprint pyhanko pyhanko-certvalidator pymupdf playwright qrcode
playwright install chromium --with-deps
```

## Dependencias sistema (Ubuntu/Debian)
```bash
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
  libfontconfig1 libcairo2 libgdk-pixbuf2.0-0 fonts-liberation fonts-noto
```

---

## Archivos ignorados (no commitear)
Ver `.gitignore`: `output/`, `nco-vistos.json`, `procesados.json`, `monitor.log`, `*.p12`
