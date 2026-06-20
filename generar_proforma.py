#!/usr/bin/env python3
"""
Genera proforma HTML + PDF firmado para cada NCO en nco-guayas.json.
Uso: P12_PASS=<clave> python3 generar_proforma.py [--nco NIC-xxx]
     P12_PASS=<clave> python3 generar_proforma.py --todos
"""
import argparse
import base64
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# ── Rutas ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
PRECIOS_JSON = BASE_DIR / "precios.json"
NCO_JSON     = BASE_DIR / "nco-guayas.json"
LOGO_PATH    = BASE_DIR / "logo.png.jpeg"
OUTPUT_DIR   = BASE_DIR / "output"
P12_PATH     = "/root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747/73c7eb7f-14775814_identity_0952773976.p12"
P12_PASS     = os.environ.get("P12_PASS", "").encode()

OUTPUT_DIR.mkdir(exist_ok=True)

# ── Carga catálogo y NCOs ────────────────────────────────────────────────────
with open(PRECIOS_JSON, encoding="utf-8") as f:
    catalogo_data = json.load(f)

PROVEEDOR = catalogo_data["proveedor"]
CATALOGO  = catalogo_data["catalogo"]
IVA_RATE  = 0.15


def logo_b64() -> str:
    if LOGO_PATH.exists():
        data = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        ext  = "jpeg" if LOGO_PATH.suffix.lower() in (".jpg", ".jpeg") else "png"
        return f"data:image/{ext};base64,{data}"
    return ""


# ── Matching de ítems NCO → catálogo ────────────────────────────────────────

def score_match(item_desc: str, entry: dict) -> int:
    """Puntaje de coincidencia entre descripción del NCO y entrada del catálogo."""
    desc = item_desc.lower()
    score = 0
    for kw in entry["keywords"]:
        if kw.lower() in desc:
            score += 1
    return score


def match_item(item_desc: str, cantidad: str, unidad: str) -> dict | None:
    """Devuelve la entrada del catálogo que mejor coincide, o None."""
    best_score = 0
    best_entry = None
    for entry in CATALOGO:
        s = score_match(item_desc, entry)
        if s > best_score:
            best_score = s
            best_entry = entry
    if best_score < 2:
        return None
    return best_entry


def parse_cantidad(s: str) -> float:
    s = re.sub(r"[^\d.,]", "", s.replace(",", "."))
    try:
        return float(s) if s else 1.0
    except ValueError:
        return 1.0


# ── Generación de tabla de ítems ─────────────────────────────────────────────

def build_items_rows(nco_items: list) -> tuple[list, list]:
    """
    Devuelve (filas_conocidas, filas_desconocidas).
    Cada fila: dict con descripcion, unidad, cantidad, precio_unitario, subtotal, notas, matched
    """
    conocidas   = []
    desconocidas = []

    for it in nco_items:
        desc     = it.get("descripcion", "")
        cantidad_str = it.get("cantidad", "1")
        unidad   = it.get("unidad", "Unidad")
        cantidad = parse_cantidad(cantidad_str)

        match = match_item(desc, cantidad_str, unidad)
        if match:
            precio = match["precio_unitario"]
            conocidas.append({
                "descripcion":    match["descripcion"],
                "unidad":         match.get("unidad", unidad),
                "cantidad":       cantidad,
                "precio_unitario": precio,
                "subtotal":       round(cantidad * precio, 2),
                "notas":          match.get("notas", ""),
                "matched":        True,
            })
        else:
            desconocidas.append({
                "descripcion":    desc,
                "unidad":         unidad,
                "cantidad":       cantidad,
                "precio_unitario": 0.0,
                "subtotal":       0.0,
                "notas":          "⚠ PRECIO PENDIENTE",
                "matched":        False,
            })

    return conocidas, desconocidas


# ── Fecha en español ──────────────────────────────────────────────────────────
MESES = ["enero","febrero","marzo","abril","mayo","junio",
         "julio","agosto","septiembre","octubre","noviembre","diciembre"]

def fecha_es(d: date = None) -> str:
    d = d or date.today()
    return f"{d.day} de {MESES[d.month-1]} de {d.year}"


# ── Plantilla HTML ────────────────────────────────────────────────────────────

def render_html(nco: dict, filas: list, subtotal: float, iva: float, total: float) -> str:
    logo = logo_b64()
    logo_tag = f'<img src="{logo}" alt="PREVIFUEGO" style="width:80px;height:80px;object-fit:contain;">' if logo else '<span style="font-weight:bold;font-size:16px;">PREVIFUEGO</span>'

    entidad  = nco.get("entidad", "")
    codigo   = nco.get("codigo", "")
    fecha    = fecha_es()
    today_iso = date.today().isoformat()

    # Tabla de ítems
    rows_html = ""
    for i, f in enumerate(filas, 1):
        precio_str = f"${f['precio_unitario']:.2f}" if f["matched"] else '<span style="color:red;font-weight:bold;">PENDIENTE</span>'
        sub_str    = f"${f['subtotal']:.2f}"        if f["matched"] else '<span style="color:red;">—</span>'
        warn       = f'<br><small style="color:#c00;">{f["notas"]}</small>' if not f["matched"] else (f'<br><small style="color:#555;">{f["notas"]}</small>' if f["notas"] else "")
        rows_html += f"""
        <tr>
          <td style="text-align:center;">{i}</td>
          <td>{f['descripcion']}{warn}</td>
          <td style="text-align:center;">{f['unidad']}</td>
          <td style="text-align:center;">{int(f['cantidad']) if f['cantidad'] == int(f['cantidad']) else f['cantidad']}</td>
          <td style="text-align:right;">{precio_str}</td>
          <td style="text-align:right;">{sub_str}</td>
        </tr>"""

    prov = PROVEEDOR
    has_unknowns = any(not f["matched"] for f in filas)
    aviso_html = ""
    if has_unknowns:
        aviso_html = '<p style="color:red;font-weight:bold;margin-top:8px;">⚠ Esta proforma tiene ítems sin precio. Completa los valores antes de firmar y enviar.</p>'

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
    .items th {{ font-size: 9px; }}
    .items td {{ font-size: 9px; }}
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

  <!-- Encabezado -->
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

  <!-- Datos entidad -->
  <div class="section-title">DATOS DE LA ENTIDAD CONTRATANTE</div>
  <table style="margin-bottom:6px;">
    <tr>
      <td style="border:1px solid #555;width:50%;"><span class="ref">Entidad:</span><strong>{entidad}</strong></td>
      <td style="border:1px solid #555;width:50%;"><span class="ref">Proceso:</span>{codigo}</td>
    </tr>
  </table>

  <!-- Datos proveedor -->
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

  <!-- Ítems -->
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

  <!-- Totales -->
  <table class="totals" style="margin-bottom:8px;">
    <tr><td class="label">SUBTOTAL:</td><td class="value">${subtotal:.2f}</td></tr>
    <tr><td class="label">IVA 15%:</td><td class="value">${iva:.2f}</td></tr>
    <tr><td class="label" style="font-size:12px;">TOTAL USD:</td><td class="value" style="font-size:12px;font-weight:bold;">${total:.2f}</td></tr>
  </table>

  <!-- Condiciones -->
  <div class="section-title">CONDICIONES COMERCIALES</div>
  <table style="margin-bottom:6px;">
    <tr>
      <td style="border:1px solid #555;width:33%;"><span class="ref">Forma de pago:</span>Contra entrega</td>
      <td style="border:1px solid #555;width:33%;"><span class="ref">Plazo entrega:</span>5 días hábiles</td>
      <td style="border:1px solid #555;width:34%;"><span class="ref">Validez oferta:</span>30 días</td>
    </tr>
  </table>

  <!-- Garantía -->
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

  <!-- Firma proforma -->
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

</div><!-- fin página 1 proforma -->

<!-- ═══════════════════════════════════════════════════════════
     PÁGINA 2 — CARTA DE DECLARACIÓN ANTI-LAVADO DE ACTIVOS
     ═══════════════════════════════════════════════════════════ -->
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

  <p style="font-size:10px;margin-bottom:8px;">
    Guayaquil, {fecha}
  </p>

  <p style="font-size:10px;margin-bottom:8px;">
    Señores<br>
    <strong>{entidad}</strong><br>
    Presente.
  </p>

  <p style="font-size:10px;margin-bottom:8px;text-align:justify;">
    Yo, <strong>{prov['representante']}</strong>, con C.I. <strong>{prov['ci']}</strong>, en calidad de
    representante / proveedor de <strong>{prov['nombre']}</strong>, RUC <strong>{prov['ruc']}</strong>,
    en pleno uso de mis facultades legales, declaro bajo juramento que:
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
    del Delito de Lavado de Activos y del Financiamiento de Delitos (LOPDEDLAFT) y sus reglamentos, así
    como de la normativa emitida por la UAFE.
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

</div><!-- fin página carta -->
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
    import fitz  # PyMuPDF

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

    # Medir cajas de firma con PyMuPDF
    doc = fitz.open(str(pdf_unsigned))
    n_pages = len(doc)

    def find_firma_box(page_idx: int):
        if page_idx >= n_pages:
            return None
        pg = doc[page_idx]
        h  = pg.rect.height
        # Buscar el primer rectángulo de borde simple en la mitad inferior de la página
        drawings = pg.get_drawings()
        candidates = []
        for d in drawings:
            r = d["rect"]
            width  = r.x1 - r.x0
            height = r.y1 - r.y0
            if width > 100 and height > 50:
                candidates.append(r)
        if not candidates:
            return None
        # Tomar el más alto (mayor y0 en coordenadas top-down = más abajo en página)
        # Excluir cajas que sean toda la página
        page_area = pg.rect.width * pg.rect.height
        valid = [c for c in candidates if (c.x1-c.x0)*(c.y1-c.y0) < page_area * 0.5]
        if not valid:
            return None
        best = max(valid, key=lambda r: r.y0)
        # Convertir top-down → bottom-up (PyHanko)
        x0 = best.x0
        y0_bu = h - best.y1
        x1 = best.x1
        y1_bu = h - best.y0
        return (x0, y0_bu, x1, y1_bu)

    box_p2 = find_firma_box(1) or (38, 480, 300, 590)
    box_p3 = find_firma_box(2) or (34, 280, 360, 390)
    doc.close()

    signer_obj = signers.SimpleSigner.load_pkcs12(pfx_file=P12_PATH, passphrase=P12_PASS)
    pdf_pass1  = pdf_signed.with_suffix(".pass1.pdf")

    # Paso 1: certify + Firma1
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

    # Paso 2: Firma2
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


# ── Generar proforma para un NCO ──────────────────────────────────────────────

def procesar_nco(nco: dict, firmar: bool = True):
    codigo   = nco.get("codigo", "SIN-CODIGO")
    entidad  = nco.get("entidad", "Entidad desconocida")
    nco_items = nco.get("items", [])

    print(f"\n{'='*60}")
    print(f"NCO: {codigo} — {entidad}")

    if not nco_items:
        print("  ⚠ Sin ítems detectados. Verifica el TDR manualmente.")
        filas = []
    else:
        conocidas, desconocidas = build_items_rows(nco_items)
        filas = conocidas + desconocidas
        print(f"  Ítems: {len(conocidas)} con precio, {len(desconocidas)} pendientes")

    subtotal = sum(f["subtotal"] for f in filas)
    iva      = round(subtotal * IVA_RATE, 2)
    total    = round(subtotal + iva, 2)

    html_content = render_html(nco, filas, subtotal, iva, total)

    safe_codigo = re.sub(r"[^\w\-]", "_", codigo)
    html_out = OUTPUT_DIR / f"proforma_{safe_codigo}.html"
    pdf_unsigned = OUTPUT_DIR / f"proforma_{safe_codigo}_unsigned.pdf"
    pdf_signed   = OUTPUT_DIR / f"Proforma_{safe_codigo}_PREVIFUEGO_signed.pdf"

    html_out.write_text(html_content, encoding="utf-8")
    print(f"  HTML: {html_out.name}")

    # HTML → PDF
    print("  Convirtiendo a PDF...")
    from weasyprint import HTML as WP_HTML
    WP_HTML(filename=str(html_out)).write_pdf(str(pdf_unsigned))
    print(f"  PDF unsigned: {pdf_unsigned.name}")

    if firmar:
        print("  Firmando PDF...")
        try:
            firmar_pdf(pdf_unsigned, pdf_signed)
        except Exception as e:
            print(f"  ⚠ Error al firmar: {e}", file=sys.stderr)
    else:
        print("  (Sin firma — usa --firmar para activar)")

    return {
        "codigo": codigo,
        "html":   str(html_out),
        "pdf":    str(pdf_signed) if firmar else str(pdf_unsigned),
        "subtotal": subtotal,
        "iva": iva,
        "total": total,
        "items_pendientes": sum(1 for f in filas if not f["matched"]),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Genera proformas para NCOs de SERCOP")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--nco",   help="Código NCO específico (ej: NIC-0998610151001-2026-00028)")
    grp.add_argument("--todos", action="store_true", help="Procesar todos los NCOs en nco-guayas.json")
    parser.add_argument("--sin-firmar", action="store_true", help="Generar HTML/PDF sin firma digital")
    args = parser.parse_args()

    firmar = not args.sin_firmar

    if not NCO_JSON.exists():
        print(f"ERROR: No se encontró {NCO_JSON}. Ejecuta primero scrape_nco.py", file=sys.stderr)
        sys.exit(1)

    with open(NCO_JSON, encoding="utf-8") as f:
        data = json.load(f)

    procesos = data.get("procesos", [])
    print(f"NCOs disponibles: {len(procesos)}")

    if args.todos:
        resultados = [procesar_nco(n, firmar) for n in procesos]
    else:
        target = [n for n in procesos if n.get("codigo") == args.nco]
        if not target:
            print(f"ERROR: NCO '{args.nco}' no encontrado en {NCO_JSON}", file=sys.stderr)
            print("Códigos disponibles:", [n.get("codigo") for n in procesos])
            sys.exit(1)
        resultados = [procesar_nco(target[0], firmar)]

    print(f"\n{'='*60}")
    print(f"Resumen — {len(resultados)} proforma(s) generada(s):")
    for r in resultados:
        status = f"⚠ {r['items_pendientes']} pendiente(s)" if r["items_pendientes"] else "✅ completa"
        print(f"  {r['codigo']}: Total ${r['total']:.2f} — {status}")
        print(f"    → {r['pdf']}")


if __name__ == "__main__":
    main()
