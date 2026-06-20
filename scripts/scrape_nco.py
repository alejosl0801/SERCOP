#!/usr/bin/env python3
"""
Scraper para Necesidades de Contratación (NCO) de SERCOP.
Busca procesos de extintores en Guayas y guarda en nco-guayas.json
"""
import json
import re
import sys
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import urllib.error

NCO_URL = "https://compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/FrmNCOListado.cpe"
DETAIL_URL = "https://compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/NCORegistroDetalle.cpe"

KEYWORDS = ["extintor", "extintores", "recarga", "incendio"]

GUAYAS_TERMS = [
    "GUAYAS", "GUAYAQUIL", "SAMBORONDON", "DAULE", "MILAGRO",
    "DURAN", "DURÁN", "YAGUACHI", "NARANJAL", "PLAYAS", "EL TRIUNFO",
    "NOBOL", "PEDRO CARBO", "BALZAR", "SANTA LUCIA", "SANTA LUCÍA"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-EC,es;q=0.9",
}


def fetch(url, data=None):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        if data:
            encoded = urllib.parse.urlencode(data).encode("utf-8")
            req = urllib.request.Request(url, data=encoded, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return ""


def find_between(text, start, end):
    s = text.find(start)
    if s == -1:
        return ""
    s += len(start)
    e = text.find(end, s)
    return text[s:e] if e != -1 else text[s:]


def strip_tags(html):
    return re.sub(r"<[^>]+>", " ", html).strip()


def clean(text):
    return re.sub(r"\s+", " ", strip_tags(text)).strip()


def parse_rows(html):
    """Extrae filas de la tabla NCO del HTML."""
    rows = []
    # Busca el tbody de la tabla principal
    tbody = find_between(html, "<tbody>", "</tbody>")
    if not tbody:
        return rows

    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody, re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
        if len(cells) < 7:
            continue
        rows.append(cells)
    return rows


def extract_id(cell_html):
    """Extrae el ID de necesidad del enlace en la primera celda."""
    m = re.search(r"id=([A-Za-z0-9_\-]+)", cell_html)
    return m.group(1) if m else ""


def parse_items_from_detail(html):
    """Extrae ítems (producto, cantidad, unidad) del detalle de la necesidad."""
    items = []
    # Busca la tabla de detalle de objeto de compra
    section = find_between(html, "Detalle del objeto de compra", "</table>")
    if not section:
        return items
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", section, re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
        if len(cells) >= 5:
            items.append({
                "cpc": clean(cells[1]),
                "descripcion": clean(cells[2]),
                "unidad": clean(cells[3]),
                "cantidad": clean(cells[4]),
            })
    return items


def is_guayas(provincia_canton):
    text = provincia_canton.upper()
    return any(t in text for t in GUAYAS_TERMS)


def is_extintor(descripcion):
    text = descripcion.lower()
    return any(k in text for k in KEYWORDS)


def scrape():
    print("Fetching NCO page...", file=sys.stderr)
    html = fetch(NCO_URL)
    if not html:
        print("No se pudo obtener la página NCO", file=sys.stderr)
        return []

    rows = parse_rows(html)
    print(f"Total filas encontradas: {len(rows)}", file=sys.stderr)

    resultados = []
    for cells in rows:
        try:
            tipo = clean(cells[0])
            codigo_html = cells[1]
            codigo = clean(codigo_html)
            nco_id = extract_id(codigo_html)
            fecha_pub = clean(cells[2])
            provincia_canton = clean(cells[3])
            descripcion = clean(cells[4])
            estado = clean(cells[5])
            fecha_limite = clean(cells[6])
            entidad = clean(cells[7]) if len(cells) > 7 else ""
            direccion = clean(cells[8]) if len(cells) > 8 else ""
            contacto = clean(cells[9]) if len(cells) > 9 else ""

            if not is_guayas(provincia_canton):
                continue
            if not is_extintor(descripcion):
                continue

            # Obtener detalle con ítems
            items = []
            email = ""
            funcionario = ""

            if nco_id:
                detail_html = fetch(f"{DETAIL_URL}?id={nco_id}")
                if detail_html:
                    items = parse_items_from_detail(detail_html)
                    # Extraer email y funcionario del detalle
                    m_email = re.search(r"[\w.\-]+@[\w.\-]+\.\w{2,}", detail_html)
                    if m_email:
                        email = m_email.group(0)
                    m_func = re.search(r"Funcionario Encargado[:\s]+([^<\n]+)", detail_html)
                    if m_func:
                        funcionario = m_func.group(1).strip()

            resultados.append({
                "id": nco_id,
                "codigo": codigo,
                "tipo": tipo,
                "fecha_publicacion": fecha_pub,
                "provincia_canton": provincia_canton,
                "descripcion": descripcion,
                "estado": estado,
                "fecha_limite": fecha_limite,
                "entidad": entidad,
                "direccion": direccion,
                "contacto": contacto,
                "funcionario": funcionario,
                "email": email,
                "items": items,
                "url_detalle": f"{DETAIL_URL}?id={nco_id}" if nco_id else "",
            })
            print(f"✅ {codigo} — {entidad} — {provincia_canton}", file=sys.stderr)

        except Exception as e:
            print(f"Error procesando fila: {e}", file=sys.stderr)
            continue

    return resultados


def main():
    resultados = scrape()
    output = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "total": len(resultados),
        "procesos": resultados,
    }
    with open("nco-guayas.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Guardados {len(resultados)} procesos en nco-guayas.json", file=sys.stderr)


if __name__ == "__main__":
    main()
