#!/usr/bin/env python3
"""
Convierte el HTML de la proforma a PDF y lo firma digitalmente con el certificado .p12.
Uso: python3 firmar.py
"""
import sys
import os
from pathlib import Path

P12_PATH = "/root/.claude/uploads/62158717-1a5c-565b-9ca5-eaa58166a747/73c7eb7f-14775814_identity_0952773976.p12"
P12_PASS = os.environ.get("P12_PASS", "").encode()
HTML_FILE = "/home/user/SERCOP/proforma_NIC-0998610151001-2026-00028.html"
PDF_UNSIGNED = "/home/user/SERCOP/proforma_NIC-0998610151001-2026-00028_unsigned.pdf"
PDF_SIGNED   = "/home/user/SERCOP/Proforma — NIC-0998610151001-2026-00028 — PREVIFUEGO-signed.pdf"

# 1. HTML → PDF
print("Convirtiendo HTML a PDF...")
from weasyprint import HTML
HTML(filename=HTML_FILE).write_pdf(PDF_UNSIGNED)
print(f"  PDF generado: {PDF_UNSIGNED}")

# 2. Firmar con pyhanko
print("Firmando PDF con certificado .p12...")
from pyhanko.sign import signers, fields
from pyhanko.sign.fields import SigFieldSpec
from pyhanko import stamp
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata

signer = signers.SimpleSigner.load_pkcs12(
    pfx_file=P12_PATH,
    passphrase=P12_PASS
)

with open(PDF_UNSIGNED, "rb") as inf:
    writer = IncrementalPdfFileWriter(inf)
    fields.append_signature_field(
        writer,
        SigFieldSpec(
            sig_field_name="Firma",
            on_page=1,          # página 2 (0-indexed) = carta anti-lavado
            box=(70, 80, 370, 180)
        )
    )
    meta = PdfSignatureMetadata(
        field_name="Firma",
        reason="Firma electrónica del proveedor PREVIFUEGO",
        location="Guayaquil, Ecuador",
        name="Alejandro Alberto López Mejía"
    )
    with open(PDF_SIGNED, "wb") as outf:
        signers.sign_pdf(writer, meta, signer=signer, output=outf)

print(f"  PDF firmado: {PDF_SIGNED}")
print("Listo.")
