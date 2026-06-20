#!/usr/bin/env python3
"""
Scraper para Necesidades de Contratación (NCO) de SERCOP.
La página usa DataTables con carga AJAX — buscamos el endpoint correcto.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import urllib.error

BASE = "https://compraspublicas.gob.ec/ProcesoContratacion/compras"
NCO_URL = f"{BASE}/NCO/FrmNCOListado.cpe"
DETAIL_BASE = f"{BASE}/NCO/NCORegistroDetalle.cpe"

KEYWORDS = ["extintor", "extintores", "recarga", "incendio"]
GUAYAS_TERMS = [
    "GUAYAS", "GUAYAQUIL", "SAMBORONDON", "DAULE", "MILAGRO",
    "DURAN", "DURÁN", "YAGUACHI", "NARANJAL", "PLAYAS", "EL TRIUNFO",
    "NOBOL", "PEDRO CARBO", "BALZAR", "SANTA LUCIA", "SANTA LUCÍA"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "es-EC,es;q=0.9,en;q=0.8",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

def fetch_html(url):
    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-EC,es;q=0.9",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return raw.decode("utf-8", errors="replace"), dict(resp.headers)
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return "", {}

def fetch_post(url, data, extra_headers=None):
    try:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        h = dict(HEADERS)
        if extra_headers:
            h.update(extra_headers)
        req = urllib.request.Request(url, data=encoded, headers=h)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"Error POST {url}: {e}", file=sys.stderr)
        return ""

def clean(text):
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def is_guayas(text):
    t = text.upper()
    return any(g in t for g in GUAYAS_TERMS)

def is_extintor(text):
    t = text.lower()
    return any(k in t for k in KEYWORDS)

def try_datatables(session_cookie=""):
    """Intenta obtener datos via DataTables AJAX (búsqueda server-side)."""
    # DataTables típicamente envía estos parámetros
    # Probamos buscar "extintor" directamente
    extra = {}
    if session_cookie:
        extra["Cookie"] = session_cookie

    params = {
        "draw": "1",
        "start": "0",
        "length": "100",
        "search[value]": "extintor",
        "search[regex]": "false",
        "order[0][column]": "2",
        "order[0][dir]": "desc",
    }

    # Intentar el endpoint principal con POST
    result = fetch_post(NCO_URL, params, extra)
    if result:
        try:
            data = json.loads(result)
            if "data" in data:
                print(f"✅ DataTables respondió con {len(data['data'])} filas", file=sys.stderr)
                return data["data"]
        except json.JSONDecodeError:
            pass

    # Intentar endpoint Ajax alternativo
    for ajax_url in [
        f"{BASE}/NCO/FrmNCOListadoAjax.cpe",
        f"{BASE}/NCO/NCOListadoAjax.cpe",
        f"{BASE}/NCO/FrmNCOBusqueda.cpe",
    ]:
        result = fetch_post(ajax_url, params, extra)
        if result and len(result) > 10:
            try:
                data = json.loads(result)
                if "data" in data:
                    print(f"✅ Ajax endpoint {ajax_url}: {len(data['data'])} filas", file=sys.stderr)
                    return data["data"]
            except:
                pass

    return None

def parse_html_table(html):
    """Parsea la tabla HTML directamente si está en el DOM."""
    rows = []
    # Busca tanto tbody como tr directamente
    tbody_match = re.search(r"<tbody[^>]*>(.*?)</tbody>", html, re.DOTALL)
    tbody = tbody_match.group(1) if tbody_match else html

    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody, re.DOTALL | re.IGNORECASE):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL | re.IGNORECASE)
        if len(cells) >= 6:
            rows.append(cells)

    print(f"HTML table rows: {len(rows)}", file=sys.stderr)
    return rows

def extract_id_from_cell(cell_html):
    m = re.search(r"id=([A-Za-z0-9_\=\+\/\-]+)", cell_html)
    if m:
        return urllib.parse.unquote(m.group(1))
    # También busca en href
    m2 = re.search(r"href=['\"].*?[?&]id=([^'\"&]+)", cell_html)
    if m2:
        return urllib.parse.unquote(m2.group(1))
    return ""

def get_detail(nco_id):
    if not nco_id:
        return [], "", ""
    url = f"{DETAIL_BASE}?id={urllib.parse.quote(nco_id)}"
    html, _ = fetch_html(url)
    if not html:
        return [], "", ""

    items = []
    # Busca tabla de ítems
    section_match = re.search(r"Detalle del objeto.*?<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)
    if section_match:
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", section_match.group(1), re.DOTALL):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            if len(cells) >= 4:
                items.append({
                    "cpc": clean(cells[0]) if len(cells) > 0 else "",
                    "descripcion": clean(cells[1]) if len(cells) > 1 else "",
                    "unidad": clean(cells[2]) if len(cells) > 2 else "",
                    "cantidad": clean(cells[3]) if len(cells) > 3 else "",
                })

    email_m = re.search(r"[\w.\-]+@[\w.\-]+\.\w{2,}", html)
    email = email_m.group(0) if email_m else ""

    func_m = re.search(r"Funcionario Encargado[:\s]*([^<\n\r]{3,80})", html)
    funcionario = func_m.group(1).strip() if func_m else ""

    return items, email, funcionario

def scrape():
    print("=== Iniciando scraper NCO ===", file=sys.stderr)

    # 1. Cargar página principal para obtener cookies/session
    print("Cargando página principal...", file=sys.stderr)
    html, resp_headers = fetch_html(NCO_URL)
    print(f"HTML recibido: {len(html)} chars", file=sys.stderr)

    # Extraer cookie de sesión si existe
    session_cookie = ""
    cookie_header = resp_headers.get("Set-Cookie", "")
    if cookie_header:
        session_cookie = cookie_header.split(";")[0]
        print(f"Cookie: {session_cookie[:50]}...", file=sys.stderr)

    # Mostrar primeros 500 chars del HTML para debug
    print(f"HTML preview: {html[:500]}", file=sys.stderr)

    # 2. Buscar el endpoint DataTables en el HTML
    ajax_url_match = re.search(r'["\']([^"\']*NCO[^"\']*(?:Ajax|ajax|data|Data)[^"\']*)["\']', html)
    if ajax_url_match:
        print(f"Ajax URL encontrada en HTML: {ajax_url_match.group(1)}", file=sys.stderr)

    # 3. Intentar DataTables
    dt_data = try_datatables(session_cookie)

    resultados = []

    if dt_data:
        # Procesar datos de DataTables (formato array de arrays o array de objetos)
        for row in dt_data:
            if isinstance(row, list) and len(row) >= 6:
                tipo = clean(row[0])
                codigo = clean(row[1])
                fecha_pub = clean(row[2])
                provincia_canton = clean(row[3])
                descripcion = clean(row[4])
                estado = clean(row[5])
                fecha_limite = clean(row[6]) if len(row) > 6 else ""
                entidad = clean(row[7]) if len(row) > 7 else ""

                if not is_guayas(provincia_canton) and not is_guayas(entidad):
                    continue
                if not is_extintor(descripcion):
                    continue

                nco_id = extract_id_from_cell(str(row[1]))
                items, email, funcionario = get_detail(nco_id)

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
                    "funcionario": funcionario,
                    "email": email,
                    "items": items,
                    "url_detalle": f"{DETAIL_BASE}?id={nco_id}" if nco_id else "",
                })
                print(f"✅ {codigo} — {entidad}", file=sys.stderr)

    else:
        # 4. Fallback: parsear HTML directamente
        print("DataTables falló — intentando parsear HTML...", file=sys.stderr)
        rows = parse_html_table(html)

        for cells in rows:
            try:
                tipo = clean(cells[0])
                codigo_html = cells[1]
                codigo = clean(codigo_html)
                fecha_pub = clean(cells[2])
                provincia_canton = clean(cells[3])
                descripcion = clean(cells[4])
                estado = clean(cells[5]) if len(cells) > 5 else ""
                fecha_limite = clean(cells[6]) if len(cells) > 6 else ""
                entidad = clean(cells[7]) if len(cells) > 7 else ""

                if not is_guayas(provincia_canton) and not is_guayas(entidad):
                    continue
                if not is_extintor(descripcion):
                    continue

                nco_id = extract_id_from_cell(codigo_html)
                items, email, funcionario = get_detail(nco_id)

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
                    "funcionario": funcionario,
                    "email": email,
                    "items": items,
                    "url_detalle": f"{DETAIL_BASE}?id={nco_id}" if nco_id else "",
                })
                print(f"✅ {codigo} — {entidad}", file=sys.stderr)
            except Exception as e:
                print(f"Error en fila: {e}", file=sys.stderr)

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
