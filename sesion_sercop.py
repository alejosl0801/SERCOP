# -*- coding: utf-8 -*-
"""Sesión persistente del portal SERCOP en un perfil de Chrome dedicado.

  py sesion_sercop.py login      abre Chrome con el perfil dedicado; entras tú UNA vez (la clave la escribes tú)
  py sesion_sercop.py estado URL revisa sin ventana si esa pantalla pide clave (mide cuánto dura la sesión)
  py sesion_sercop.py abrir URL  abre ese enlace en el perfil con la sesión ya iniciada (para proformas)

El perfil dedicado conserva las cookies del portal entre usos. Todavía no se mide cuánto dura la sesión de SERCOP.
"""
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
PERFIL = Path.home() / ".sercop" / "perfil_chrome"
LOG = BASE / "sesion.log"
ESTADO_FILE = BASE / "sesion_estado.txt"
INICIO_URL = "https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/FrmNCOListado.cpe"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"


def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {m}\n")


def contexto(p, headless):
    PERFIL.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(str(PERFIL), headless=headless, locale="es-EC", user_agent=UA,
                                                viewport={"width": 1280, "height": 900})


def hay_sesion(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3500)
    return page.locator("input[type='password']").count() == 0


def estado(url):
    """Abre `url` (la pantalla de 'Enviar Proforma' de un proceso) sin ventana y mira si pide clave."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = contexto(p, True)
        try:
            ok = hay_sesion(ctx.pages[0] if ctx.pages else ctx.new_page(), url)
        finally:
            ctx.close()
    log("sesión " + ("ABIERTA" if ok else "PIDE CLAVE") + f" ({url[:80]})")
    print("sesión abierta" if ok else "el portal pide clave")
    return 0 if ok else 1


def login():
    """Abre el perfil dedicado en el listado de procesos. Entra a cualquier proceso > Enviar Proforma > pon tu clave."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = contexto(p, False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(INICIO_URL, wait_until="domcontentloaded", timeout=60000)
        print("Entra a un proceso > Enviar Proforma > escribe tu usuario y clave. Luego CIERRA la ventana.")
        try:
            ctx.wait_for_event("close", timeout=30 * 60 * 1000)
        except Exception:
            pass
    log("login manual en el perfil dedicado")


def abrir(url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = contexto(p, False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            ctx.wait_for_event("close", timeout=60 * 60 * 1000)
        except Exception:
            pass


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["login"]:
        login()
    elif a[:1] == ["estado"]:
        sys.exit(estado(a[1]) if len(a) > 1 else print("uso: py sesion_sercop.py estado <URL de Enviar Proforma>") or 2)
    elif a[:1] == ["abrir"] and len(a) > 1:
        abrir(a[1])
    else:
        print(__doc__)
