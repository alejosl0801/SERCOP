#!/usr/bin/env python3
"""
Convierte HTML a PDF y lo firma con sello QR estilo FirmaEC.
Uso: P12_PASS=<clave> python3 firmar.py
"""
import os
from weasyprint import HTML as WP_HTML
from pyhanko.sign import signers, fields
from pyhanko.sign.fields import SigFieldSpec
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata
from pyhanko.stamp import QRStampStyle

P12_PATH = "/root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747/73c7eb7f-14775814_identity_0952773976.p12"
P12_PASS = os.environ.get("P12_PASS", "").encode()
HTML_FILE = "/home/user/SERCOP/proforma_NIC-0998610151001-2026-00028.html"
PDF_UNSIGNED = "/home/user/SERCOP/proforma_NIC-0998610151001-2026-00028_unsigned.pdf"
PDF_SIGNED   = "/home/user/SERCOP/Proforma — NIC-0998610151001-2026-00028 — PREVIFUEGO-signed.pdf"

# 1. HTML → PDF
print("1. Convirtiendo HTML a PDF...")
WP_HTML(filename=HTML_FILE).write_pdf(PDF_UNSIGNED)
print(f"   OK")

# 2. Firmar con QR estilo FirmaEC
print("2. Firmando con sello QR...")

signer = signers.SimpleSigner.load_pkcs12(
    pfx_file=P12_PATH,
    passphrase=P12_PASS
)

style = QRStampStyle(
    stamp_text=(
        "Validar únicamente en FirmaEC.\n"
        "Firmado electrónicamente por:\n"
        "ALEJANDRO ALBERTO LOPEZ MEJIA\n"
        "Fecha: %(ts)s"
    ),
    background_opacity=1,
    timestamp_format="%Y-%m-%d %H:%M:%S UTC",
)

# Página 3 (índice 2) = carta anti-lavado
# Coordenadas medidas del PDF renderizado por WeasyPrint (top-down):
#   - Firma box: y=460 a y=595, x=90 a x=450
# Convertido a PDF bottom-up (página 841.9pt):
#   y_bottom = 841.9 - 595 = 247,  y_top = 841.9 - 460 = 382
STAMP_BOX = (90, 275, 407, 373)  # x1, y1, x2, y2 (bottom-up) — medido del PDF

with open(PDF_UNSIGNED, "rb") as inf:
    writer = IncrementalPdfFileWriter(inf)
    fields.append_signature_field(
        writer,
        SigFieldSpec(
            sig_field_name="Firma",
            on_page=2,
            box=STAMP_BOX
        )
    )
    meta = PdfSignatureMetadata(
        field_name="Firma",
        reason="Firma electrónica del proveedor PREVIFUEGO",
        location="Guayaquil, Ecuador",
        name="Alejandro Alberto López Mejía"
    )
    pdf_signer = signers.PdfSigner(
        signature_meta=meta,
        signer=signer,
        stamp_style=style,
    )
    with open(PDF_SIGNED, "wb") as outf:
        pdf_signer.sign_pdf(
            writer,
            appearance_text_params={"url": "https://www.firmadigital.gob.ec"},
            output=outf
        )

print(f"   OK: {PDF_SIGNED}")
print("Listo.")
