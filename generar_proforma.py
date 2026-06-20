#!/usr/bin/env python3
"""
Genera proforma HTML + PDF firmado para cada NCO en nco-guayas.json.

Uso:
  P12_PASS=<clave> python3 generar_proforma.py --nco NIC-0998610151001-2026-00028
  P12_PASS=<clave> python3 generar_proforma.py --todos
  python3 generar_proforma.py --nco NIC-xxx --sin-firmar

Las recargas PQS y CO2 se calculan automáticamente: precio_por_libra × capacidad.
Las adquisiciones usan precio fijo del catálogo.
Los ítems sin match se reportan como PENDIENTES y se envía alerta por email.
"""
import argparse
import base64
import json
import os
import re
import smtplib
import sys
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── Rutas ────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
PRECIOS_JSON = BASE_DIR / "precios.json"
NCO_JSON     = BASE_DIR / "nco-guayas.json"
PROCESADOS   = BASE_DIR / "procesados.json"
LOGO_PATH    = BASE_DIR / "logo.png.jpeg"
OUTPUT_DIR   = BASE_DIR / "output"
P12_PATH     = "/root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747/73c7eb7f-14775814_identity_0952773976.p12"
P12_PASS     = os.environ.get("P12_PASS", "").encode()

OUTPUT_DIR.mkdir(exist_ok=True)

# ── Carga catálogo ────────────────────────────────────────────────────────────
with open(PRECIOS_JSON, encoding="utf-8") as f:
    _cat = json.load(f)

PROVEEDOR       = _cat["proveedor"]
TARIFAS_LB      = _cat["tarifas_por_libra"]      # {"recarga_PQS": 0.70, "recarga_CO2": 0.70}
ADQ_CATALOG     = _cat["adquisiciones"]           # lista con precio fijo por agente+capacidad
IVA_RATE        = 0.15

# ── Registro de procesados ────────────────────────────────────────────────────

def cargar_procesados() -> set:
    if PROCESADOS.exists():
        return set(json.loads(PROCESADOS.read_text()))
    return set()

def guardar_procesado(codigo: str):
    p = cargar_procesados()
    p.add(codigo)
    PROCESADOS.write_text(json.dumps(sorted(p), ensure_ascii=False, indent=2))

# ── Logo base64 ───────────────────────────────────────────────────────────────

def logo_b64() -> str:
    if LOGO_PATH.exists():
        data = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        ext  = "jpeg" if LOGO_PATH.suffix.lower() in (".jpg", ".jpeg") else "png"
        return f"data:image/{ext};base64,{data}"
    return ""

# ── Parseo de texto ───────────────────────────────────────────────────────────

def parse_float(s: str) -> float:
    s = re.sub(r"[^\d.,]", "", str(s).replace(",", "."))
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0

def extract_lbs(text: str) -> float | None:
    """Extrae la capacidad en libras de un texto como '10 lbs', '50lb', '20 libras'."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:lbs?|libras?)", text, re.IGNORECASE)
    if m:
        return parse_float(m.group(1))
    return None

def detect_agente(text: str) -> str | None:
    t = text.upper()
    if "CO2" in t or "CO₂" in t or "DIOXIDO" in t or "DIÓXIDO" in t or "CARBÓNICO" in t or "CARBONICO" in t:
        return "CO2"
    if "PQS" in t or "POLVO" in t or "QUIMICO" in t or "QUÍMICO" in t:
        return "PQS"
    if "AFFF" in t or "ESPUMA" in t or "FOAM" in t:
        return "AFFF"
    if "AGUA" in t or "WATER" in t:
        return "AGUA"
    if "HALON" in t or "HALÓN" in t or "HALOTRON" in t:
        return "HALON"
    return None

def detect_tipo(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["recarga", "recargar", "recargue", "recargas"]):
        return "recarga"
    if any(w in t for w in ["adquisicion", "adquisición", "compra", "suministro",
                              "nuevo", "nueva", "provision", "provisión"]):
        return "adquisicion"
    return "desconocido"

# ── Motor de precios ──────────────────────────────────────────────────────────

class ResultadoMatch:
    def __init__(self, descripcion, unidad, cantidad, precio, notas, matched, pendiente_tipo=None):
        self.descripcion   = descripcion
        self.unidad        = unidad
        self.cantidad      = cantidad
        self.precio_unitario = precio
        self.subtotal      = round(cantidad * precio, 2) if matched else 0.0
        self.notas         = notas
        self.matched       = matched
        self.pendiente_tipo = pendiente_tipo  # descripción del problema para el aviso

def calcular_precio(item: dict) -> ResultadoMatch:
    desc     = item.get("descripcion", "")
    unidad   = item.get("unidad", "Unidad")
    cantidad = parse_float(item.get("cantidad", "1")) or 1.0

    tipo   = detect_tipo(desc)
    agente = detect_agente(desc)
    lbs    = extract_lbs(desc)

    # ── RECARGA con precio por libra ──────────────────────────────────────────
    if tipo == "recarga" and agente in ("PQS", "CO2") and lbs:
        tarifa_key = f"recarga_{agente}"
        tarifa     = TARIFAS_LB.get(tarifa_key, 0.70)
        precio     = round(tarifa * lbs, 2)
        desc_clean = f"Recarga de extintor {agente} {int(lbs) if lbs == int(lbs) else lbs} lbs"
        notas      = f"Tarifa: ${tarifa}/lb × {int(lbs) if lbs==int(lbs) else lbs} lbs"
        if agente == "CO2":
            notas += " | Sin manómetro — agente CO2"
        return ResultadoMatch(desc_clean, "Unidad", cantidad, precio, notas, True)

    # ── ADQUISICIÓN desde catálogo fijo ──────────────────────────────────────
    if tipo == "adquisicion" and agente and lbs:
        for entry in ADQ_CATALOG:
            if entry["agente"] == agente and entry["capacidad_lbs"] == lbs:
                return ResultadoMatch(
                    entry["descripcion"], "Unidad", cantidad,
                    entry["precio_unitario"], entry.get("notas", ""), True
                )
        # Agente y libras detectados pero no hay entrada en catálogo
        return ResultadoMatch(
            desc, unidad, cantidad, 0.0,
            f"⚠ Adquisición {agente} {lbs} lbs: no está en catálogo",
            False,
            pendiente_tipo=f"adquisicion_{agente}_{lbs}lbs"
        )

    # ── Recarga con agente desconocido o libras no detectadas ─────────────────
    if tipo == "recarga":
        if not agente:
            motivo = "Agente no identificado (¿PQS, CO2, AFFF?)"
        elif not lbs:
            motivo = f"Capacidad en lbs no detectada para recarga {agente}"
        else:
            motivo = f"Recarga {agente}: sin tarifa configurada"
        return ResultadoMatch(desc, unidad, cantidad, 0.0,
                              f"⚠ {motivo}", False, pendiente_tipo=motivo)

    # ── Ítem completamente desconocido ────────────────────────────────────────
    return ResultadoMatch(
        desc, unidad, cantidad, 0.0,
        "⚠ No reconocido — revisar y agregar a catálogo",
        False,
        pendiente_tipo=f"desconocido: {desc[:80]}"
    )

def build_filas(nco_items: list) -> list[ResultadoMatch]:
    return [calcular_precio(it) for it in nco_items]

# ── Alerta por email ──────────────────────────────────────────────────────────

def enviar_alerta(codigo: str, entidad: str, pendientes: list[ResultadoMatch]):
    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_pass = os.environ.get("GMAIL_APP_PASS", "")
    if not gmail_user or not gmail_pass:
        print("  ⚠ GMAIL_USER/GMAIL_APP_PASS no configurados — alerta no enviada.", file=sys.stderr)
        return

    body_items = "\n".join(
        f"  • {r.descripcion}\n    Motivo: {r.pendiente_tipo}" for r in pendientes
    )
    body = f"""Hola Alejandro,

Se detectó el NCO {codigo} ({entidad}) pero {len(pendientes)} ítem(s) no tienen precio:

{body_items}

Acciones requeridas:
1. Abre precios.json y agrega las entradas correspondientes en "adquisiciones"
2. Si es un agente nuevo (HALON, AFFF, etc.), agrega también la tarifa en "tarifas_por_libra"
3. Vuelve a correr: P12_PASS=... python3 generar_proforma.py --nco {codigo}

PREVIFUEGO — Sistema automático de proformas
"""
    msg = MIMEMultipart()
    msg["From"]    = gmail_user
    msg["To"]      = PROVEEDOR["email"]
    msg["Subject"] = f"⚠ PREVIFUEGO — NCO {codigo}: {len(pendientes)} ítem(s) pendientes de precio"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(gmail_user, gmail_pass)
            s.send_message(msg)
        print(f"  📧 Alerta enviada a {PROVEEDOR['email']}")
    except Exception as e:
        print(f"  ⚠ No se pudo enviar alerta: {e}", file=sys.stderr)

# ── Fecha en español ──────────────────────────────────────────────────────────
MESES = ["enero","febrero","marzo","abril","mayo","junio",
         "julio","agosto","septiembre","octubre","noviembre","diciembre"]

def fecha_es(d: date = None) -> str:
    d = d or date.today()
    return f"{d.day} de {MESES[d.month-1]} de {d.year}"

# ── Plantilla HTML ────────────────────────────────────────────────────────────

def render_html(nco: dict, filas: list[ResultadoMatch]) -> str:
    logo    = logo_b64()
    logo_tag = (f'<img src="{logo}" alt="PREVIFUEGO" '
                'style="width:80px;height:80px;object-fit:contain;">'
                if logo else '<span style="font-weight:bold;font-size:16px;">PREVIFUEGO</span>')

    entidad = nco.get("entidad", "")
    codigo  = nco.get("codigo", "")
    fecha   = fecha_es()

    subtotal = sum(f.subtotal for f in filas)
    iva      = round(subtotal * IVA_RATE, 2)
    total    = round(subtotal + iva, 2)

    rows_html = ""
    for i, f in enumerate(filas, 1):
        if f.matched:
            precio_str = f"${f.precio_unitario:.2f}"
            sub_str    = f"${f.subtotal:.2f}"
            nota_html  = f'<br><small style="color:#555;">{f.notas}</small>' if f.notas else ""
        else:
            precio_str = '<span style="color:red;font-weight:bold;">PENDIENTE</span>'
            sub_str    = '<span style="color:red;">—</span>'
            nota_html  = f'<br><small style="color:#c00;">{f.notas}</small>'

        cant_disp = int(f.cantidad) if f.cantidad == int(f.cantidad) else f.cantidad
        rows_html += f"""
        <tr>
          <td style="text-align:center;">{i}</td>
          <td>{f.descripcion}{nota_html}</td>
          <td style="text-align:center;">{f.unidad}</td>
          <td style="text-align:center;">{cant_disp}</td>
          <td style="text-align:right;">{precio_str}</td>
          <td style="text-align:right;">{sub_str}</td>
        </tr>"""

    prov = PROVEEDOR
    has_unknowns = any(not f.matched for f in filas)
    aviso_html = ""
    if has_unknowns:
        aviso_html = ('<p style="color:red;font-weight:bold;margin-top:8px;">'
                      '⚠ Esta proforma tiene ítems sin precio. '
                      'Revisa tu email y completa los valores antes de firmar y enviar.</p>')

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Proforma {codigo}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, Helvetica, sans-serif; font-size: 10px; color: #222; }}
  @page {{ size: A4; margin: 10mm 12mm; }}
  @media print {{
    body {{ font-size: 10px; }}
    .page {{ width: 100%; padding: 0; margin: 0; }}
    .no-print {{ display: none; }}
    .carta-page {{ page-break-before: always; }}
    .items th, .items td {{ font-size: 9px; }}
    table td, table th {{ padding: 3px 4px; }}
  }}
  .page {{ width: 210mm; max-width: 100%; padding: 0; margin: 0 auto; }}
  table {{ width: 100%; border-collapse: collapse; }}
  table td, table th {{ border: 1px solid #555; padding: 4px 5px; vertical-align: top; }}
  .items th {{ background: #1a3a5c; color: #fff; text-align: center; font-size: 9px; }}
  .items td {{ font-size: 9px; }}
  .section-title {{
    background: #1a3a5c; color: #fff;
    padding: 4px 8px; font-weight: bold; font-size: 11px;
    margin: 8px 0 4px;
  }}
  .firma-box {{
    border: 1px solid #555; min-height: 110px; margin-top: 4px;
    width: 100%; display: block;
  }}
  .logo-area img {{ width: 80px; height: 80px; max-width: 80px; max-height: 80px; object-fit: contain; }}
  h2 {{ font-size: 13px; color: #1a3a5c; text-align: center; margin-bottom: 6px; }}
  .ref {{ color: #555; font-size: 9px; padding-right: 2mm; }}
  .totals td {{ border: none; padding: 2px 4px; }}
  .totals .label {{ text-align: right; font-weight: bold; width: 70%; }}
  .totals .value {{ text-align: right; width: 30%; }}
</style>
</head>
<body>
<div class="page">

  <table style="margin-bottom:6px;">
    <tr>
      <td style="border:none;width:90px;vertical-align:middle;" class="logo-area">{logo_tag}</td>
      <td style="border:none;vertical-align:middle;text-align:center;">
        <h2>PROFORMA COMERCIAL</h2>
        <div style="font-size:10px;"><strong>PREVIFUEGO</strong> — RUC: {prov['ruc']}</div>
        <div style="font-size:9px;">{prov['direccion']} | {prov['email']}</div>
      </td>
      <td style="border:1px solid #555;width:120px;vertical-align:top;font-size:9px;padding:4px;">
        <strong>Código NCO:</strong><br>{codigo}<br><br>
        <strong>Fecha:</strong><br>Guayaquil, {fecha}
      </td>
    </tr>
  </table>

  <div class="section-title">DATOS DE LA ENTIDAD CONTRATANTE</div>
  <table style="margin-bottom:6px;">
    <tr>
      <td style="border:1px solid #555;width:50%;"><span class="ref">Entidad:</span><strong>{entidad}</strong></td>
      <td style="border:1px solid #555;width:50%;"><span class="ref">Proceso:</span>{codigo}</td>
    </tr>
  </table>

  <div class="section-title">DATOS DEL PROVEEDOR</div>
  <table style="margin-bottom:6px;">
    <tr>
      <td style="border:1px solid #555;"><span class="ref">Razón social / Nombre:</span>{prov['nombre']}</td>
      <td style="border:1px solid #555;width:35%;"><span class="ref">RUC/CI:</span>{prov['ruc']}</td>
    </tr>
    <tr>
      <td style="border:1px solid #555;"><span class="ref">Representante:</span>{prov['representante']}</td>
      <td style="border:1px solid #555;"><span class="ref">Email:</span>{prov['email']}</td>
    </tr>
  </table>

  <div class="section-title">DETALLE DE BIENES / SERVICIOS</div>
  <table class="items" style="margin-bottom:6px;">
    <thead>
      <tr>
        <th style="width:4%;">N°</th>
        <th style="width:42%;">Descripción</th>
        <th style="width:10%;">Unidad</th>
        <th style="width:8%;">Cant.</th>
        <th style="width:16%;">P. Unitario</th>
        <th style="width:20%;">Subtotal</th>
      </tr>
    </thead>
    <tbody>{rows_html}
    </tbody>
  </table>

  {aviso_html}

  <table class="totals" style="margin-bottom:8px;">
    <tr><td class="label">SUBTOTAL:</td><td class="value">${subtotal:.2f}</td></tr>
    <tr><td class="label">IVA 15%:</td><td class="value">${iva:.2f}</td></tr>
    <tr><td class="label" style="font-size:12px;">TOTAL USD:</td>
        <td class="value" style="font-size:12px;font-weight:bold;">${total:.2f}</td></tr>
  </table>

  <div class="section-title">CONDICIONES COMERCIALES</div>
  <table style="margin-bottom:6px;">
    <tr>
      <td style="border:1px solid #555;width:33%;"><span class="ref">Forma de pago:</span>Contra entrega</td>
      <td style="border:1px solid #555;width:33%;"><span class="ref">Plazo entrega:</span>5 días hábiles</td>
      <td style="border:1px solid #555;width:34%;"><span class="ref">Validez oferta:</span>30 días</td>
    </tr>
  </table>

  <div class="section-title">GARANTÍA Y ESPECIFICACIONES</div>
  <table style="margin-bottom:8px;">
    <tr>
      <td style="border:1px solid #555;">
        <ul style="margin:2px 0 2px 14px;padding:0;font-size:9px;">
          <li>Extintores PQS: cilindro de acero, válvula de seguridad, manómetro y manguera. Certificación UL/FM.</li>
          <li>Extintores CO2: cilindro de alta presión, sin manómetro (agente gaseoso). Certificación UL/FM.</li>
          <li>Recargas: incluyen prueba hidrostática, carga certificada y etiqueta vigente según INEN 739.</li>
          <li>Garantía técnica: 1 año contra defectos de fabricación.</li>
        </ul>
      </td>
    </tr>
  </table>

  <div class="section-title">FIRMA DE RESPONSABILIDAD</div>
  <table style="margin-bottom:6px;">
    <tr>
      <td style="border:1px solid #555;width:50%;padding:4px;">
        <div style="font-size:9px;margin-bottom:2px;">Proveedor: <strong>{prov['nombre']}</strong></div>
        <div style="font-size:9px;margin-bottom:2px;">RUC: {prov['ruc']} | C.I.: {prov['ci']}</div>
        <div class="firma-box">&nbsp;</div>
        <div style="font-size:8px;margin-top:2px;text-align:center;">Firma electrónica del proveedor</div>
      </td>
      <td style="border:none;width:50%;"></td>
    </tr>
  </table>

</div>

<!-- ═══════════ CARTA ANTI-LAVADO ═══════════ -->
<div class="page carta-page">

  <table style="margin-bottom:10px;">
    <tr>
      <td style="border:none;width:90px;vertical-align:middle;" class="logo-area">{logo_tag}</td>
      <td style="border:none;vertical-align:middle;text-align:center;">
        <h2>CARTA DE DECLARACIÓN</h2>
        <div style="font-size:10px;">Prevención de Lavado de Activos, Financiamiento del Terrorismo</div>
        <div style="font-size:9px;">y otros Delitos (LAFT/FPADM)</div>
      </td>
    </tr>
  </table>

  <p style="font-size:10px;margin-bottom:8px;">Guayaquil, {fecha}</p>

  <p style="font-size:10px;margin-bottom:8px;">
    Señores<br><strong>{entidad}</strong><br>Presente.
  </p>

  <p style="font-size:10px;margin-bottom:8px;text-align:justify;">
    Yo, <strong>{prov['representante']}</strong>, con C.I. <strong>{prov['ci']}</strong>,
    en calidad de representante / proveedor de <strong>{prov['nombre']}</strong>,
    RUC <strong>{prov['ruc']}</strong>, en pleno uso de mis facultades legales,
    declaro bajo juramento que:
  </p>

  <ol style="font-size:10px;margin:0 0 8px 18px;line-height:1.6;">
    <li>Los fondos utilizados en esta transacción provienen de actividades lícitas y legalmente reconocidas.</li>
    <li>No existen vínculos con organizaciones dedicadas al narcotráfico, terrorismo, corrupción ni ningún otro delito tipificado en la legislación ecuatoriana.</li>
    <li>La información personal y empresarial proporcionada es veraz, completa y verificable.</li>
    <li>Me comprometo a notificar de inmediato cualquier cambio en las circunstancias que pudiera afectar las declaraciones aquí efectuadas.</li>
    <li>Autorizo a la entidad contratante a verificar la información suministrada ante los organismos de control competentes.</li>
  </ol>

  <p style="font-size:10px;margin-bottom:16px;text-align:justify;">
    Esta declaración se emite en cumplimiento de la Ley Orgánica de Prevención, Detección y Erradicación
    del Delito de Lavado de Activos y del Financiamiento de Delitos (LOPDEDLAFT) y sus reglamentos,
    así como de la normativa emitida por la UAFE.
  </p>

  <table style="margin-top:10px;">
    <tr>
      <td style="border:1px solid #555;width:55%;padding:4px;">
        <div style="font-size:9px;margin-bottom:2px;">Declarante: <strong>{prov['representante']}</strong></div>
        <div style="font-size:9px;margin-bottom:2px;">C.I.: {prov['ci']} | RUC: {prov['ruc']}</div>
        <div class="firma-box">&nbsp;</div>
        <div style="font-size:8px;margin-top:2px;text-align:center;">Firma electrónica del declarante</div>
      </td>
      <td style="border:none;width:45%;"></td>
    </tr>
  </table>

</div>
</body>
</html>
"""

# ── Firma PDF ─────────────────────────────────────────────────────────────────

def firmar_pdf(pdf_unsigned: Path, pdf_signed: Path):
    from pyhanko.sign import signers, fields
    from pyhanko.sign.fields import SigFieldSpec, MDPPerm
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata
    from pyhanko.stamp import QRStampStyle
    import fitz

    if not P12_PASS:
        print("  ⚠ P12_PASS no definido — PDF no firmado.", file=sys.stderr)
        return

    STYLE = QRStampStyle(
        stamp_text=(
            "Validar únicamente en FirmaEC.\n"
            "Firmado electrónicamente por:\n"
            "ALEJANDRO ALBERTO LOPEZ MEJIA\n"
            "Fecha: %(ts)s"
        ),
        background_opacity=1,
        timestamp_format="%Y-%m-%d %H:%M:%S UTC",
    )

    doc = fitz.open(str(pdf_unsigned))
    n   = len(doc)

    def firma_box(page_idx: int, default: tuple) -> tuple:
        if page_idx >= n:
            return default
        pg = doc[page_idx]
        h  = pg.rect.height
        drawings = pg.get_drawings()
        area_pg  = pg.rect.width * h
        valid = [d["rect"] for d in drawings
                 if (d["rect"].x1-d["rect"].x0) > 100
                 and (d["rect"].y1-d["rect"].y0) > 50
                 and (d["rect"].x1-d["rect"].x0)*(d["rect"].y1-d["rect"].y0) < area_pg*0.5]
        if not valid:
            return default
        r = max(valid, key=lambda r: r.y0)
        return (r.x0, h - r.y1, r.x1, h - r.y0)

    box_p2 = firma_box(1, (38, 480, 300, 590))
    box_p3 = firma_box(2, (34, 280, 360, 390))
    doc.close()

    signer_obj = signers.SimpleSigner.load_pkcs12(pfx_file=P12_PATH, passphrase=P12_PASS)
    pdf_pass1  = pdf_signed.with_suffix(".pass1.pdf")

    with open(pdf_unsigned, "rb") as inf:
        w = IncrementalPdfFileWriter(inf)
        fields.append_signature_field(w, SigFieldSpec("Firma1", on_page=1, box=box_p2))
        fields.append_signature_field(w, SigFieldSpec("Firma2", on_page=2, box=box_p3))
        meta1 = PdfSignatureMetadata(
            field_name="Firma1",
            reason="Firma electrónica del proveedor PREVIFUEGO",
            location="Guayaquil, Ecuador",
            name=PROVEEDOR["representante"],
            certify=True,
            docmdp_permissions=MDPPerm.FILL_FORMS,
        )
        ps1 = signers.PdfSigner(signature_meta=meta1, signer=signer_obj, stamp_style=STYLE)
        with open(pdf_pass1, "wb") as outf:
            ps1.sign_pdf(w, appearance_text_params={"url": "https://www.firmadigital.gob.ec"}, output=outf)

    with open(pdf_pass1, "rb") as inf:
        w2 = IncrementalPdfFileWriter(inf)
        meta2 = PdfSignatureMetadata(
            field_name="Firma2",
            reason="Firma electrónica del proveedor PREVIFUEGO",
            location="Guayaquil, Ecuador",
            name=PROVEEDOR["representante"],
        )
        ps2 = signers.PdfSigner(signature_meta=meta2, signer=signer_obj, stamp_style=STYLE)
        with open(pdf_signed, "wb") as outf:
            ps2.sign_pdf(w2, appearance_text_params={"url": "https://www.firmadigital.gob.ec"}, output=outf)

    pdf_pass1.unlink(missing_ok=True)
    print(f"  ✅ Firmado: {pdf_signed.name}")

# ── Procesar un NCO ───────────────────────────────────────────────────────────

def procesar_nco(nco: dict, firmar: bool = True, forzar: bool = False) -> dict:
    codigo  = nco.get("codigo", "SIN-CODIGO")
    entidad = nco.get("entidad", "Entidad desconocida")

    print(f"\n{'='*60}")
    print(f"NCO: {codigo}")
    print(f"Entidad: {entidad}")

    procesados = cargar_procesados()
    if codigo in procesados and not forzar:
        print(f"  ⏭ Ya procesado anteriormente. Usa --forzar para regenerar.")
        return {"codigo": codigo, "omitido": True}

    nco_items = nco.get("items", [])
    if not nco_items:
        print("  ⚠ Sin ítems — verifica el TDR manualmente.")
        filas = []
    else:
        filas = build_filas(nco_items)
        n_ok  = sum(1 for f in filas if f.matched)
        n_err = sum(1 for f in filas if not f.matched)
        print(f"  Ítems: {n_ok} con precio automático, {n_err} pendientes")

    pendientes = [f for f in filas if not f.matched]
    if pendientes:
        print("  Ítems pendientes de precio:")
        for p in pendientes:
            print(f"    • {p.descripcion}")
            print(f"      Motivo: {p.pendiente_tipo}")
        enviar_alerta(codigo, entidad, pendientes)

    safe   = re.sub(r"[^\w\-]", "_", codigo)
    html_f = OUTPUT_DIR / f"proforma_{safe}.html"
    pdf_u  = OUTPUT_DIR / f"proforma_{safe}_unsigned.pdf"
    pdf_s  = OUTPUT_DIR / f"Proforma_{safe}_PREVIFUEGO_signed.pdf"

    html_f.write_text(render_html(nco, filas), encoding="utf-8")
    print(f"  HTML generado: {html_f.name}")

    from weasyprint import HTML as WP_HTML
    WP_HTML(filename=str(html_f)).write_pdf(str(pdf_u))
    print(f"  PDF unsigned: {pdf_u.name}")

    if firmar and not pendientes:
        firmar_pdf(pdf_u, pdf_s)
        guardar_procesado(codigo)
    elif firmar and pendientes:
        print("  ⏸ Firma omitida — hay ítems pendientes. Corrige y vuelve a correr.")
    else:
        guardar_procesado(codigo)

    subtotal = sum(f.subtotal for f in filas)
    iva      = round(subtotal * IVA_RATE, 2)
    total    = round(subtotal + iva, 2)

    return {
        "codigo":             codigo,
        "pdf":                str(pdf_s if (firmar and not pendientes) else pdf_u),
        "subtotal":           subtotal,
        "iva":                iva,
        "total":              total,
        "items_pendientes":   len(pendientes),
    }

# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Genera proformas para NCOs de SERCOP")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--nco",   help="Código NCO (ej: NIC-0998610151001-2026-00028)")
    grp.add_argument("--todos", action="store_true", help="Procesar todos los NCOs nuevos")
    parser.add_argument("--sin-firmar", action="store_true", help="Generar sin firma digital")
    parser.add_argument("--forzar",     action="store_true", help="Reprocesar aunque ya esté en registro")
    args = parser.parse_args()

    firmar = not args.sin_firmar

    if not NCO_JSON.exists():
        print(f"ERROR: {NCO_JSON} no existe. Corre primero scrape_nco.py", file=sys.stderr)
        sys.exit(1)

    with open(NCO_JSON, encoding="utf-8") as f:
        data = json.load(f)
    procesos = data.get("procesos", [])

    if args.todos:
        resultados = [procesar_nco(n, firmar, args.forzar) for n in procesos]
    else:
        target = next((n for n in procesos if n.get("codigo") == args.nco), None)
        if not target:
            print(f"ERROR: NCO '{args.nco}' no encontrado.", file=sys.stderr)
            print("Disponibles:", [n.get("codigo") for n in procesos])
            sys.exit(1)
        resultados = [procesar_nco(target, firmar, args.forzar)]

    print(f"\n{'='*60}")
    print(f"Resumen — {len(resultados)} NCO(s):")
    for r in resultados:
        if r.get("omitido"):
            print(f"  {r['codigo']}: omitido (ya procesado)")
        else:
            st = f"⚠ {r['items_pendientes']} pendiente(s)" if r["items_pendientes"] else "✅ completo"
            print(f"  {r['codigo']}: Total ${r['total']:.2f} — {st}")

if __name__ == "__main__":
    main()
