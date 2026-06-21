#!/usr/bin/env python3
"""
Sube una proforma PDF firmada al portal SERCOP para un NCO específico.

Uso:
  SERCOP_USER=<ruc_o_usuario> SERCOP_PASS=<clave> \\
    python3 scripts/upload_proforma.py --nco NIC-xxx --pdf output/Proforma_NIC-xxx_signed.pdf

Variables de entorno requeridas:
  SERCOP_USER  — usuario del portal (RUC del proveedor: 0952773976001)
  SERCOP_PASS  — contraseña del portal SERCOP
"""
import argparse
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

LOGIN_URL  = "https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/EP/epLoginProveedor.cpe"
NCO_LIST   = "https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/FrmNCOListado.cpe"

SERCOP_USER = os.environ.get("SERCOP_USER", "")
SERCOP_PASS = os.environ.get("SERCOP_PASS", "")


def log(msg: str):
    print(msg, flush=True)


def upload(nco_codigo: str, pdf_path: Path, headless: bool = True):
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    if not SERCOP_USER or not SERCOP_PASS:
        print("ERROR: Define SERCOP_USER y SERCOP_PASS como variables de entorno.", file=sys.stderr)
        sys.exit(1)

    if not pdf_path.exists():
        print(f"ERROR: PDF no encontrado: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    log(f"NCO: {nco_codigo}")
    log(f"PDF: {pdf_path.name}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            locale="es-EC",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        )
        page = ctx.new_page()

        # ── 1. Login ──────────────────────────────────────────────────────────
        log("1. Iniciando sesión en SERCOP...")
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)

        # Aceptar cookies si aparece el banner
        try:
            page.locator("button:has-text('Aceptar'), button:has-text('Accept')").first.click(timeout=3000)
        except PWTimeout:
            pass

        # Intentar distintos selectores para el campo RUC/usuario
        ruc_sel = [
            "#rucEmpresa", "#usuario", "#ruc", "input[name='rucEmpresa']",
            "input[name='usuario']", "input[type='text']",
        ]
        for sel in ruc_sel:
            if page.locator(sel).count() > 0:
                page.fill(sel, SERCOP_USER)
                break
        else:
            log("  ⚠ No se encontró campo RUC — verificar URL de login")
            browser.close()
            sys.exit(1)

        # Campo contraseña
        pass_sel = [
            "#contrasena", "#password", "#clave", "input[name='contrasena']",
            "input[type='password']",
        ]
        for sel in pass_sel:
            if page.locator(sel).count() > 0:
                page.fill(sel, SERCOP_PASS)
                break

        # Botón ingresar
        login_btn = page.locator(
            "button[type='submit'], input[type='submit'], button:has-text('Ingresar'), "
            "button:has-text('Iniciar'), a:has-text('Ingresar')"
        ).first
        login_btn.click()
        page.wait_for_load_state("networkidle", timeout=30000)

        # Verificar login exitoso
        if "login" in page.url.lower() or "Login" in page.url:
            log("  ❌ Login fallido — verifica SERCOP_USER y SERCOP_PASS")
            browser.close()
            sys.exit(1)
        log(f"  ✅ Sesión iniciada ({page.url})")

        # ── 2. Buscar el NCO en la lista ─────────────────────────────────────
        log(f"2. Buscando NCO {nco_codigo}...")
        page.goto(NCO_LIST, wait_until="networkidle", timeout=30000)

        # Buscar en campo de filtro
        search_sel = [
            "input[type='search']", "#descripcionProducto", "input.form-control",
            "input[placeholder*='Cod']", "input[placeholder*='Buscar']",
        ]
        searched = False
        for sel in search_sel:
            if page.locator(sel).count() > 0:
                page.fill(sel, nco_codigo)
                page.keyboard.press("Enter")
                page.wait_for_timeout(2000)
                searched = True
                break

        if not searched:
            log("  ⚠ No se encontró campo de búsqueda — intentando buscar en tabla")

        # Encontrar fila del NCO
        row = page.locator(f"tr:has-text('{nco_codigo}')").first
        if row.count() == 0:
            log(f"  ❌ No se encontró {nco_codigo} en la lista — verifica que esté activo")
            browser.close()
            sys.exit(1)

        # Click en el código para ir al detalle
        row.locator("a").first.click()
        page.wait_for_load_state("networkidle", timeout=30000)
        log(f"  ✅ Entrado al detalle ({page.url})")

        # ── 3. Encontrar botón para adjuntar proforma ─────────────────────────
        log("3. Buscando opción para adjuntar proforma...")
        time.sleep(1)

        # Selectores probables del botón de adjuntar/subir proforma
        upload_triggers = [
            "button:has-text('Adjuntar')",
            "button:has-text('Subir')",
            "button:has-text('Proforma')",
            "a:has-text('Adjuntar')",
            "a:has-text('Subir proforma')",
            "input[type='file']",
            "#btnAdjuntarProforma",
            ".btn-adjuntar",
        ]

        file_input = None
        for sel in upload_triggers:
            el = page.locator(sel).first
            if el.count() > 0:
                if "file" in (el.get_attribute("type") or ""):
                    file_input = el
                else:
                    el.click()
                    page.wait_for_timeout(1500)
                    # Buscar el input file que puede aparecer tras el click
                    fi = page.locator("input[type='file']").first
                    if fi.count() > 0:
                        file_input = fi
                break

        if not file_input or file_input.count() == 0:
            log("  ⚠ No se encontró campo de carga de archivo.")
            log("    El portal puede requerir subir el archivo a través de una sección específica.")
            log("    Pasos manuales:")
            log(f"    1. Abre: {page.url}")
            log(f"    2. Busca 'Adjuntar proforma' o 'Subir documento'")
            log(f"    3. Selecciona: {pdf_path}")
            browser.close()
            sys.exit(2)

        # ── 4. Subir el PDF ───────────────────────────────────────────────────
        log(f"4. Subiendo {pdf_path.name}...")
        file_input.set_input_files(str(pdf_path))
        page.wait_for_timeout(1000)

        # Confirmar/guardar
        confirm_sel = [
            "button:has-text('Guardar')", "button:has-text('Enviar')",
            "button:has-text('Aceptar')", "button[type='submit']",
            "input[type='submit']",
        ]
        for sel in confirm_sel:
            el = page.locator(sel).first
            if el.count() > 0:
                el.click()
                page.wait_for_load_state("networkidle", timeout=20000)
                break

        # Verificar éxito (busca mensaje de confirmación o error)
        page_text = page.inner_text("body")
        if any(w in page_text.lower() for w in ["exitoso", "guardado", "enviado", "correcto", "registrado"]):
            log(f"  ✅ Proforma subida exitosamente")
        elif any(w in page_text.lower() for w in ["error", "fallido", "inválido", "invalido"]):
            log(f"  ❌ Error al subir — revisa el portal manualmente: {page.url}")
            sys.exit(1)
        else:
            log(f"  ℹ Verifica en el portal que la proforma quedó adjunta: {page.url}")

        browser.close()
        log("\nListo.")


def main():
    parser = argparse.ArgumentParser(description="Sube proforma al portal SERCOP")
    parser.add_argument("--nco",     required=True, help="Código NCO (ej: NIC-0998610151001-2026-00028)")
    parser.add_argument("--pdf",     required=True, help="Ruta al PDF firmado")
    parser.add_argument("--visible", action="store_true", help="Mostrar el navegador (debug)")
    args = parser.parse_args()

    upload(args.nco, Path(args.pdf).resolve(), headless=not args.visible)


if __name__ == "__main__":
    main()
