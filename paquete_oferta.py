# -*- coding: utf-8 -*-
"""Arma UN solo PDF con toda la oferta y lo firma (FirmaEC) en proforma y en Anexo I.

Orden: proforma · Anexo I (Perfil de Integridad) · RUC del SRI · fichas técnicas.
El portal solo admite un archivo obligatorio en PDF: así sube todo junto y con firmas válidas.

Uso:  py paquete_oferta.py "<carpeta del proceso en ESTADO>" [--ficha RUTA.pdf ...]
Requiere que la carpeta tenga datos_proceso.json (lo deja preparar_proceso.py) y que la proforma no tenga ítems sin precio.
"""
import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import generar_proforma as gp  # noqa: E402
import anexo_integridad as ai  # noqa: E402

FICHA_DEFECTO = Path(r"C:\Users\HP\Dropbox\Previfuego\FICHAS TECNICAS\FichaTecnica_Extintores_Pyroshield.pdf")
RUC_SRI = Path(r"C:\Users\HP\Dropbox\PROFORMAS PAGINA WEB\NO APROBADOS\005511_ThePoint\requisitos\Certificado_RUC_Lopez.pdf")


def caja_firma(pg):
    h = pg.rect.height
    area = pg.rect.width * h
    validas = [d["rect"] for d in pg.get_drawings()
               if (d["rect"].x1 - d["rect"].x0) > 100 and (d["rect"].y1 - d["rect"].y0) > 50
               and (d["rect"].x1 - d["rect"].x0) * (d["rect"].y1 - d["rect"].y0) < area * 0.5]
    if not validas:
        raise RuntimeError("No encontré la caja de firma en la página")
    r = max(validas, key=lambda r: r.y0)
    return (r.x0, h - r.y1, r.x1, h - r.y0)


def main(carpeta, fichas):
    import fitz
    from pyhanko.sign import signers, fields
    from pyhanko.sign.fields import SigFieldSpec, MDPPerm
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata
    from pyhanko.stamp import QRStampStyle

    carpeta = Path(carpeta)
    nco = json.loads((carpeta / "datos_proceso.json").read_text(encoding="utf-8"))
    nco["incluir_carta"] = False

    res = gp.procesar_nco(nco, firmar=False, forzar=True)
    if res.get("items_pendientes"):
        raise RuntimeError(f"La proforma tiene ítems sin precio: {res['items_pendientes']}")
    prof = Path(res["pdf"])

    # Anexo I sin firmar (se firma dentro del paquete)
    anexo_u = ai.main(carpeta, firmar=False)
    paquete = fitz.open()
    pa = fitz.open(str(prof))
    idx_prof = len(pa) - 1
    paquete.insert_pdf(pa)
    idx_anexo = len(paquete)
    paquete.insert_pdf(fitz.open(str(anexo_u)))
    for extra in [RUC_SRI] + list(fichas):
        if Path(extra).exists():
            paquete.insert_pdf(fitz.open(str(extra)))
    caja_p = caja_firma(paquete[idx_prof])
    caja_a = caja_firma(paquete[idx_anexo])
    base = carpeta / "OFERTA COMPLETA (sin firmar).pdf"
    paquete.save(str(base))
    paquete.close()

    signer = signers.SimpleSigner.load_pkcs12(pfx_file=gp.P12_PATH, passphrase=gp.P12_PASS)
    estilo = QRStampStyle(
        stamp_text="Validar únicamente en FirmaEC.\nFirmado electrónicamente por:\nALEJANDRO ALBERTO LOPEZ MEJIA\nFecha: %(ts)s",
        background_opacity=1, timestamp_format="%Y-%m-%d %H:%M:%S UTC")
    p1 = carpeta / "paso1.tmp.pdf"
    final = carpeta / "OFERTA COMPLETA - PROFORMA + ANEXO I + RUC + FICHAS (FIRMADA).pdf"
    with open(base, "rb") as f:
        w = IncrementalPdfFileWriter(f)
        fields.append_signature_field(w, SigFieldSpec("Firma1", on_page=idx_prof, box=caja_p))
        fields.append_signature_field(w, SigFieldSpec("Firma2", on_page=idx_anexo, box=caja_a))
        m1 = PdfSignatureMetadata(field_name="Firma1", reason="Firma electrónica del proveedor PREVIFUEGO",
                                  location="Guayaquil, Ecuador", name=gp.PROVEEDOR["representante"],
                                  certify=True, docmdp_permissions=MDPPerm.FILL_FORMS)
        with open(p1, "wb") as out:
            signers.PdfSigner(m1, signer=signer, stamp_style=estilo).sign_pdf(
                w, appearance_text_params={"url": "https://www.firmadigital.gob.ec"}, output=out)
    with open(p1, "rb") as f:
        w2 = IncrementalPdfFileWriter(f)
        m2 = PdfSignatureMetadata(field_name="Firma2", reason="Firma electrónica del proveedor PREVIFUEGO",
                                  location="Guayaquil, Ecuador", name=gp.PROVEEDOR["representante"])
        with open(final, "wb") as out:
            signers.PdfSigner(m2, signer=signer, stamp_style=estilo).sign_pdf(
                w2, appearance_text_params={"url": "https://www.firmadigital.gob.ec"}, output=out)
    p1.unlink(missing_ok=True)
    base.unlink(missing_ok=True)
    anexo_u.unlink(missing_ok=True)
    (carpeta / "SUBIR_ESTE.pdf").write_bytes(final.read_bytes())
    print(final)
    return final


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta")
    ap.add_argument("--ficha", action="append", default=None)
    a = ap.parse_args()
    main(a.carpeta, a.ficha if a.ficha is not None else [FICHA_DEFECTO])
