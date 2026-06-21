#!/usr/bin/env python3
"""
Scraper NCO con Playwright — renderiza JavaScript para obtener datos reales.
Descarga y parsea TDR PDFs adjuntos cuando la tabla no tiene ítems detallados.
"""
import io
import json
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

DETAIL_BASE = "https://compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/NCORegistroDetalle.cpe"
NCO_URL = "https://compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/FrmNCOListado.cpe"
BASE_DIR = Path(__file__).parent.parent

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


# ── Parseo de TDR PDF ─────────────────────────────────────────────────────────

def extraer_items_pdf(pdf_bytes: bytes) -> list[dict]:
    """
    Intenta extraer ítems (descripción, cantidad, unidad) de un TDR en PDF.
    Busca patrones de tabla comunes en documentos SERCOP.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("  PyMuPDF no instalado — omitiendo parseo de TDR", file=sys.stderr)
        return []

    items = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = "\n".join(page.get_text() for page in doc)
        doc.close()
    except Exception as e:
        print(f"  Error leyendo PDF: {e}", file=sys.stderr)
        return []

    # Patrón 1: líneas con número de ítem, descripción, cantidad y unidad
    # Ej: "1  Recarga extintor PQS 10 lbs  5  Unidad"
    pat1 = re.compile(
        r"^\s*(\d+)[.\s]+([^\n]{10,120}?)\s{2,}(\d+(?:[.,]\d+)?)\s{1,}(unidad|u\b|global|servicio|mes|día|hora|kg|lb|lbs|galon|litro)s?",
        re.IGNORECASE | re.MULTILINE
    )
    for m in pat1.finditer(full_text):
        desc = m.group(2).strip()
        if is_extintor(desc):
            items.append({
                "cpc": "",
                "descripcion": desc,
                "cantidad": m.group(3).replace(",", "."),
                "unidad": m.group(4).capitalize(),
            })

    # Patrón 2: bloques DESCRIPCIÓN / CANTIDAD / UNIDAD en columnas separadas por saltos
    if not items:
        lines = [l.strip() for l in full_text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if is_extintor(line) and len(line) > 8:
                # Buscar cantidad en las siguientes 5 líneas
                for j in range(i + 1, min(i + 6, len(lines))):
                    m_cant = re.match(r"^(\d+(?:[.,]\d+)?)\s*(unidad|u\b|global|servicio|kg|lbs?|galon|litro)?", lines[j], re.IGNORECASE)
                    if m_cant:
                        items.append({
                            "cpc": "",
                            "descripcion": line,
                            "cantidad": m_cant.group(1).replace(",", "."),
                            "unidad": (m_cant.group(2) or "Unidad").capitalize(),
                        })
                        break

    # Deduplicar por descripción
    seen = set()
    unique = []
    for it in items:
        k = it["descripcion"].lower()
        if k not in seen:
            seen.add(k)
            unique.append(it)

    return unique


# ── Scraper principal ─────────────────────────────────────────────────────────

def scrape_with_playwright():
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

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
        search_input = page.locator(
            "input[type='search'], input[placeholder*='Descripci'], #descripcionProducto, input.form-control"
        ).first
        if search_input.count() > 0:
            search_input.fill("extintor")
            search_input.press("Enter")
        else:
            page.fill("input[type='text']:last-of-type", "extintor")
            page.keyboard.press("Enter")

        page.wait_for_timeout(3000)

        # Cambiar paginación a 100 entradas
        try:
            length_select = page.locator("select[name*='DataTables'], select[name$='_length']").first
            if length_select.count() > 0:
                length_select.select_option("100")
                page.wait_for_timeout(2000)
                print("Paginación cambiada a 100 entradas", file=sys.stderr)
            else:
                selects = page.locator("select").all()
                for sel in selects:
                    opts = sel.locator("option").all()
                    vals = [o.get_attribute("value") for o in opts]
                    if "100" in vals or "-1" in vals:
                        sel.select_option("100" if "100" in vals else "-1")
                        page.wait_for_timeout(2000)
                        print("Paginación encontrada por opciones", file=sys.stderr)
                        break
        except Exception as e:
            print(f"No se pudo cambiar paginación: {e}", file=sys.stderr)

        # Extraer filas de la tabla
        print("Extrayendo filas...", file=sys.stderr)
        rows = page.locator("table tbody tr").all()
        print(f"Filas encontradas: {len(rows)}", file=sys.stderr)

        for i, row in enumerate(rows):
            cells = row.locator("td").all()
            if len(cells) < 6:
                continue

            texts = [c.inner_text().strip() for c in cells]
            tipo         = texts[0] if len(texts) > 0 else ""
            codigo       = texts[1] if len(texts) > 1 else ""
            fecha_pub    = texts[2] if len(texts) > 2 else ""
            prov_canton  = texts[3] if len(texts) > 3 else ""
            descripcion  = texts[4] if len(texts) > 4 else ""
            estado       = texts[5] if len(texts) > 5 else ""
            fecha_limite = texts[6] if len(texts) > 6 else ""
            entidad      = texts[7] if len(texts) > 7 else ""

            if not is_guayas(prov_canton) and not is_guayas(entidad):
                continue
            if not is_extintor(descripcion):
                continue

            # ID desde el href
            link = cells[1].locator("a").first
            href = link.get_attribute("href") if link.count() > 0 else ""
            nco_id = ""
            if href:
                m = re.search(r"id=([^&]+)", href)
                if m:
                    nco_id = m.group(1)

            # Detalle: ítems, email, funcionario, PDFs adjuntos
            items, email, funcionario = [], "", ""
            if nco_id:
                try:
                    detail_page = context.new_page()
                    detail_page.goto(
                        f"{DETAIL_BASE}?id={nco_id}",
                        wait_until="networkidle", timeout=20000
                    )
                    detail_html = detail_page.content()

                    # ── Ítems desde la tabla HTML ────────────────────────────
                    item_rows = re.findall(r"<tr[^>]*>(.*?)</tr>", detail_html, re.DOTALL)
                    for ir in item_rows:
                        tds = re.findall(r"<td[^>]*>(.*?)</td>", ir, re.DOTALL)
                        if len(tds) >= 4:
                            desc = clean(tds[1]) if len(tds) > 1 else ""
                            if any(k in desc.lower() for k in KEYWORDS + ["cpc", "servicio"]):
                                items.append({
                                    "cpc":        clean(tds[0]),
                                    "descripcion": desc,
                                    "unidad":     clean(tds[2]) if len(tds) > 2 else "",
                                    "cantidad":   clean(tds[3]) if len(tds) > 3 else "",
                                })

                    # ── Email y funcionario ──────────────────────────────────
                    email_m = re.search(r"[\w.\-]+@[\w.\-]+\.\w{2,}", detail_html)
                    if email_m:
                        email = email_m.group(0)

                    func_m = re.search(r"Funcionario Encargado[:\s]*([^<\n\r]{3,80})", detail_html)
                    if func_m:
                        funcionario = func_m.group(1).strip()

                    # ── TDR PDF adjunto (cuando la tabla HTML no tiene ítems) ─
                    if not items:
                        pdf_links = re.findall(
                            r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
                            detail_html, re.IGNORECASE
                        )
                        # También buscar links de descarga genérica
                        pdf_links += re.findall(
                            r'href=["\']([^"\']*(?:descargar|download|adjunto|archivo)[^"\']*)["\']',
                            detail_html, re.IGNORECASE
                        )

                        for pdf_href in pdf_links[:3]:  # máximo 3 PDFs por NCO
                            if not pdf_href.startswith("http"):
                                pdf_href = "https://compraspublicas.gob.ec" + pdf_href
                            try:
                                print(f"  Descargando TDR: {pdf_href}", file=sys.stderr)
                                pdf_resp = detail_page.request.get(pdf_href, timeout=15000)
                                if pdf_resp.ok:
                                    content_type = pdf_resp.headers.get("content-type", "")
                                    if "pdf" in content_type or pdf_href.lower().endswith(".pdf"):
                                        pdf_items = extraer_items_pdf(pdf_resp.body())
                                        if pdf_items:
                                            items = pdf_items
                                            print(f"  ✅ {len(pdf_items)} ítem(s) extraído(s) del TDR PDF", file=sys.stderr)
                                            break
                            except Exception as e:
                                print(f"  Error descargando PDF {pdf_href}: {e}", file=sys.stderr)

                    detail_page.close()

                except Exception as e:
                    print(f"Error obteniendo detalle {nco_id}: {e}", file=sys.stderr)
                    try:
                        detail_page.close()
                    except Exception:
                        pass

            resultados.append({
                "id":               nco_id,
                "codigo":           codigo,
                "tipo":             tipo,
                "fecha_publicacion": fecha_pub,
                "provincia_canton": prov_canton,
                "descripcion":      descripcion,
                "estado":           estado,
                "fecha_limite":     fecha_limite,
                "entidad":          entidad,
                "funcionario":      funcionario,
                "email":            email,
                "items":            items,
                "url_detalle":      f"{DETAIL_BASE}?id={nco_id}" if nco_id else "",
            })
            print(f"✅ {codigo} — {entidad} — {len(items)} ítem(s)", file=sys.stderr)

        browser.close()

    return resultados


def main():
    print("=== NCO Scraper con Playwright ===", file=sys.stderr)
    resultados = scrape_with_playwright()
    output = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "total":       len(resultados),
        "procesos":    resultados,
    }
    out_path = BASE_DIR / "nco-guayas.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Guardados {len(resultados)} procesos en {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
