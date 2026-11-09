# -*- coding: utf-8 -*-
"""Genera y firma (FirmaEC) el Formulario de Perfil de Integridad del Proveedor de un proceso.

Toma el texto del formulario TAL CUAL lo publica la entidad (en 'TEXTO COMPLETO DE LOS ANEXOS.txt'), rellena los
datos entre corchetes y lo firma electrónicamente. No es una declaración notarial ni juramentada.

Uso:  py anexo_integridad.py "<carpeta del proceso en ESTADO>"
"""
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import generar_proforma as gp  # noqa: E402

MARCA_INI = "FORMULARIO DE PERFIL DE INTEGRIDAD DEL PROVEEDOR Yo,"
MARCA_FIN = "[FIRMA DEL OFERENTE"


def texto_formulario(carpeta):
    t = re.sub(r"\s+", " ", (carpeta / "TEXTO COMPLETO DE LOS ANEXOS.txt").read_text(encoding="utf-8"))
    i = t.rfind(MARCA_INI)
    if i < 0:
        raise RuntimeError("No encontré el formulario en los anexos de la entidad.")
    j = t.find(MARCA_FIN, i)
    cuerpo = t[i + len("FORMULARIO DE PERFIL DE INTEGRIDAD DEL PROVEEDOR "): j]
    cuerpo = re.sub(r"#####[^#]*?pág/hoja \d+", " ", cuerpo)
    return re.sub(r"\s+", " ", cuerpo).strip()


def main(carpeta, firmar=True):
    carpeta = Path(carpeta)
    d = json.loads((carpeta / "datos_proceso.json").read_text(encoding="utf-8"))
    objeto = d["descripcion"]
    entidad = d["entidad"]
    codigo = d["codigo"]
    cuerpo = texto_formulario(carpeta)
    cuerpo = cuerpo.replace("[Detallar Nombre Completo, Razón social] [Detallar por sus propios derechos, si es persona natural/ Detallar Representante Legal o apoderado si es persona jurídica; Procurador Común si se trata de consorcio]",
                            "ALEJANDRO ALBERTO LÓPEZ MEJÍA, por mis propios derechos (razón social LOPEZ MEJIA ALEJANDRO ALBERTO, nombre comercial PREVIFUEGO)")
    cuerpo = cuerpo.replace("[Detallar RUC]", "0952773976001")
    cuerpo = cuerpo.replace("[Detallar Nombre de la Entidad Contratante]", entidad)
    cuerpo = cuerpo.replace("[Detallar el objeto de contratación]", objeto)
    cuerpo = cuerpo.replace("[Detallar Código del Procedimiento de Contratación]", codigo)
    if "[Detallar" in cuerpo:
        raise RuntimeError("Quedaron campos sin rellenar en el formulario.")
    # separa los numerales 1. 2. 3. 4. y el bloque de compromisos
    cuerpo = re.sub(r" (\d)\. (?=[A-ZÁÉÍÓÚ])", r"</p><p>\1. ", cuerpo)
    cuerpo = cuerpo.replace(" Así también me comprometo a:", "</p><p><b>Así también me comprometo a:</b>")
    hoy = gp.fecha_es() if hasattr(gp, "fecha_es") else str(date.today())
    logo = ""
    h = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Formulario de Perfil de Integridad - {html.escape(codigo)}</title>
<style>@page{{size:A4;margin:16mm 18mm}} body{{font-family:'Liberation Serif',Georgia,serif;font-size:11.2px;line-height:1.45;color:#000}}
h2{{text-align:center;font-size:14px;margin:0 0 2px}} .sub{{text-align:center;font-size:11px;margin-bottom:12px}}
p{{text-align:justify;margin:6px 0}} .firma-box{{border:1px solid #555;min-height:120px;margin-top:22px}}
.dat{{margin-top:8px;font-size:11px}}</style></head><body>
<h2>FORMULARIO DE PERFIL DE INTEGRIDAD DEL PROVEEDOR</h2>
<div class="sub">{html.escape(entidad)} — Proceso {html.escape(codigo)}</div>
<p>{cuerpo}</p>
<div class="firma-box"></div>
<div class="dat"><b>NOMBRE:</b> ALEJANDRO ALBERTO LÓPEZ MEJÍA<br><b>C.C. / RUC:</b> 0952773976 / 0952773976001<br>
<b>Lugar y fecha:</b> Guayaquil, {html.escape(hoy)}</div>
</body></html>"""
    pdf_u = carpeta / "ANEXO I - Perfil de Integridad (sin firmar).pdf"
    pdf_s = carpeta / "ANEXO I - Perfil de Integridad FIRMADO.pdf"
    from weasyprint import HTML
    HTML(string=h).write_pdf(str(pdf_u))
    if not firmar:
        return pdf_u
    gp.firmar_pdf(pdf_u, pdf_s)
    pdf_u.unlink(missing_ok=True)
    print(pdf_s)
    return pdf_s


if __name__ == "__main__":
    main(sys.argv[1])
