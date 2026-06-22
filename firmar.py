#!/usr/bin/env python3
"""
Firma el PDF de proforma con dos firmas electrónicas:
  - Firma1: página 2 (proforma)
  - Firma2: página 3 (carta anti-lavado)
Uso: P12_PASS=<clave> python3 firmar.py
"""
import os
from weasyprint import HTML as WP_HTML
from pyhanko.sign import signers, fields
from pyhanko.sign.fields import SigFieldSpec, MDPPerm
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata
from pyhanko.stamp import QRStampStyle

P12_PATH = "/root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747/73c7eb7f-14775814_identity_0952773976.p12"
P12_PASS = os.environ.get("P12_PASS", "").encode()
HTML_FILE    = "/home/user/SERCOP/proforma_NIC-0998610151001-2026-00028.html"
PDF_UNSIGNED = "/home/user/SERCOP/proforma_NIC-0998610151001-2026-00028_unsigned.pdf"
PDF_PASS1    = "/home/user/SERCOP/proforma_pass1.pdf"
PDF_SIGNED   = "/home/user/SERCOP/Proforma — NIC-0998610151001-2026-00028 — PREVIFUEGO-signed.pdf"

BOX_P2 = (38, 508, 294, 606)
BOX_P3 = (34, 303, 350, 401)

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

def load_signer():
    return signers.SimpleSigner.load_pkcs12(pfx_file=P12_PATH, passphrase=P12_PASS)

print("1. Convirtiendo HTML a PDF...")
WP_HTML(filename=HTML_FILE).write_pdf(PDF_UNSIGNED)
print("   OK")

print("2. Firmando página 2 (proforma)...")
signer = load_signer()
with open(PDF_UNSIGNED, "rb") as inf:
    writer = IncrementalPdfFileWriter(inf)
    fields.append_signature_field(writer, SigFieldSpec("Firma1", on_page=1, box=BOX_P2))
    fields.append_signature_field(writer, SigFieldSpec("Firma2", on_page=2, box=BOX_P3))
    meta1 = PdfSignatureMetadata(
        field_name="Firma1",
        reason="Firma electrónica del proveedor PREVIFUEGO",
        location="Guayaquil, Ecuador",
        name="Alejandro Alberto López Mejía",
        certify=True,
        docmdp_permissions=MDPPerm.FILL_FORMS,
    )
    ps1 = signers.PdfSigner(signature_meta=meta1, signer=signer, stamp_style=STYLE)
    with open(PDF_PASS1, "wb") as outf:
        ps1.sign_pdf(writer, appearance_text_params={"url": "https://www.firmadigital.gob.ec"}, output=outf)
print("   OK")

print("3. Firmando página 3 (carta anti-lavado)...")
signer = load_signer()
with open(PDF_PASS1, "rb") as inf:
    writer2 = IncrementalPdfFileWriter(inf)
    meta2 = PdfSignatureMetadata(
        field_name="Firma2",
        reason="Firma electrónica del proveedor PREVIFUEGO",
        location="Guayaquil, Ecuador",
        name="Alejandro Alberto López Mejía",
    )
    ps2 = signers.PdfSigner(signature_meta=meta2, signer=signer, stamp_style=STYLE)
    with open(PDF_SIGNED, "wb") as outf:
        ps2.sign_pdf(writer2, appearance_text_params={"url": "https://www.firmadigital.gob.ec"}, output=outf)
print("   OK")
print(f"\nListo: {PDF_SIGNED}")
