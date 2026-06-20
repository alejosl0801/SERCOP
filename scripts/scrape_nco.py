#!/usr/bin/env python3
"""
Scraper NCO con Playwright — renderiza JavaScript para obtener datos reales.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone

DETAIL_BASE = "https://compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/NCORegistroDetalle.cpe"
NCO_URL = "https://compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/FrmNCOListado.cpe"

KEYWORDS = ["extintor", "extintores", "recarga", "incendio"]
GUAYAS_TERMS = [
    "GUAYAS", "GUAYAQUIL", "SAMBORONDON", "DAULE", "MILAGRO",
    "DURAN", "DURÁN", "YAGUACHI", "NARANJAL", "PLAYAS", "EL TRIUNFO",
    "NOBOL", "PEDRO CARBO", "BALZAR", "SANTA LUCIA", "SANTA LUCÍA"
]

def clean(text):
    text = re.sub(r"<[^>]+>", " ", str(text))
    return re.sub(r"\s+", " ", text).strip()

def is_guayas(text):
    t = text.upper()
    return any(g in t for g in GUAYAS_TERMS)

def is_extintor(text):
    t = text.lower()
    return any(k in t for k in KEYWORDS)

def scrape_with_playwright():
    from playwright.sync_api import sync_playwright

    resultados = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="es-EC",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Abriendo página NCO...", file=sys.stderr)
        page.goto(NCO_URL, wait_until="networkidle", timeout=30000)

        # Buscar "extintor" en el filtro
        print("Buscando 'extintor'...", file=sys.stderr)
        search_input = page.locator("input[type='search'], input[placeholder*='Descripci'], #descripcionProducto, input.form-control").first
        if search_input.count() > 0:
            search_input.fill("extintor")
            search_input.press("Enter")
        else:
            # Buscar el campo por texto cercano
            page.fill("input[type='text']:last-of-type", "extintor")
            page.keyboard.press("Enter")

        # Esperar que cargue la tabla
        page.wait_for_timeout(3000)

        # Extraer todas las filas de la tabla
        print("Extrayendo filas...", file=sys.stderr)
        rows = page.locator("table tbody tr").all()
        print(f"Filas encontradas: {len(rows)}", file=sys.stderr)

        for row in rows:
            cells = row.locator("td").all()
            if len(cells) < 6:
                continue

            texts = [c.inner_text().strip() for c in cells]
            tipo          = texts[0] if len(texts) > 0 else ""
            codigo        = texts[1] if len(texts) > 1 else ""
            fecha_pub     = texts[2] if len(texts) > 2 else ""
            prov_canton   = texts[3] if len(texts) > 3 else ""
            descripcion   = texts[4] if len(texts) > 4 else ""
            estado        = texts[5] if len(texts) > 5 else ""
            fecha_limite  = texts[6] if len(texts) > 6 else ""
            entidad       = texts[7] if len(texts) > 7 else ""

            if not is_guayas(prov_canton) and not is_guayas(entidad):
                continue
            if not is_extintor(descripcion):
                continue

            # Obtener ID del enlace en la celda de código
            link = cells[1].locator("a").first
            href = link.get_attribute("href") if link.count() > 0 else ""
            nco_id = ""
            if href:
                m = re.search(r"id=([^&]+)", href)
                if m:
                    nco_id = m.group(1)

            # Obtener detalle (ítems, email, funcionario)
            items, email, funcionario = [], "", ""
            if nco_id:
                try:
                    detail_page = context.new_page()
                    detail_page.goto(f"{DETAIL_BASE}?id={nco_id}", wait_until="networkidle", timeout=20000)
                    detail_html = detail_page.content()
                    detail_page.close()

                    # Extraer ítems
                    item_rows = re.findall(r"<tr[^>]*>(.*?)</tr>", detail_html, re.DOTALL)
                    for ir in item_rows:
                        tds = re.findall(r"<td[^>]*>(.*?)</td>", ir, re.DOTALL)
                        if len(tds) >= 4:
                            desc = clean(tds[1]) if len(tds) > 1 else ""
                            if any(k in desc.lower() for k in KEYWORDS + ["cpc", "servicio"]):
                                items.append({
                                    "cpc": clean(tds[0]),
                                    "descripcion": desc,
                                    "unidad": clean(tds[2]) if len(tds) > 2 else "",
                                    "cantidad": clean(tds[3]) if len(tds) > 3 else "",
                                })

                    email_m = re.search(r"[\w.\-]+@[\w.\-]+\.\w{2,}", detail_html)
                    if email_m:
                        email = email_m.group(0)

                    func_m = re.search(r"Funcionario Encargado[:\s]*([^<\n\r]{3,80})", detail_html)
                    if func_m:
                        funcionario = func_m.group(1).strip()

                except Exception as e:
                    print(f"Error obteniendo detalle {nco_id}: {e}", file=sys.stderr)

            resultados.append({
                "id": nco_id,
                "codigo": codigo,
                "tipo": tipo,
                "fecha_publicacion": fecha_pub,
                "provincia_canton": prov_canton,
                "descripcion": descripcion,
                "estado": estado,
                "fecha_limite": fecha_limite,
                "entidad": entidad,
                "funcionario": funcionario,
                "email": email,
                "items": items,
                "url_detalle": f"{DETAIL_BASE}?id={nco_id}" if nco_id else "",
            })
            print(f"✅ {codigo} — {entidad} — {prov_canton}", file=sys.stderr)

        browser.close()

    return resultados


def main():
    print("=== NCO Scraper con Playwright ===", file=sys.stderr)
    resultados = scrape_with_playwright()
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
