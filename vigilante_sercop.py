# -*- coding: utf-8 -*-
"""Vigilante SERCOP: revisa el portal y avisa en grande si hay procesos NUEVOS de extintores cerca de Guayaquil.

Lo ejecuta el Programador de tareas de Windows (tarea SERCOP_Vigilante) cada 30 min.
Uso manual:  py vigilante_sercop.py            -> revisa y avisa
             py vigilante_sercop.py --seed     -> solo registra lo que hay hoy, sin avisar
"""
import json
import decisiones
import subprocess
import sys
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
VISTOS = BASE / "vistos.json"
ESTADO = BASE / "estado_vigilante.json"
LOG = BASE / "vigilante.log"
ALERTAS = BASE / "ALERTAS.txt"
TEXTO = BASE / "alerta_texto.txt"
NTFY = BASE / "ntfy_topic.txt"
COLA = BASE / "cola_preparar.jsonl"

NCO_URL = "https://compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/FrmNCOListado.cpe"
PORTAL_URL = "https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/FrmNCOListado.cpe"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

TIPOS = [("54092", "Ínfima Cuantía"), ("54089", "Necesidad de Contratación")]
TERMS = ["extintor", "recarga", "incendio", "pqs", "contra incendio"]
CERCA = ("GUAYAQUIL", "SAMBORONDON", "SAMBORONDÓN", "DAULE", "DURAN", "DURÁN")
FALLOS_PARA_AVISAR = 6


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except Exception:
        pass


def cargar(path, defecto):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return defecto


def guardar(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def parse_fecha(s):
    try:
        return datetime.strptime(s.strip()[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def buscar(page, tipo_val, term):
    ultimo, error = [], None
    for _ in range(3):
        try:
            page.goto(NCO_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("table tbody tr", timeout=45000)
            page.wait_for_timeout(2500)
            page.locator("select").all()[1].select_option(tipo_val)
            page.wait_for_timeout(1500)
            box = page.locator(
                "input[type='search'], input[placeholder*='Descripci'], #descripcionProducto, input.form-control"
            ).first
            box.fill(term)
            box.press("Enter")
            page.wait_for_timeout(3500)
            for sel in page.locator("select").all():
                vals = [o.get_attribute("value") for o in sel.locator("option").all()]
                if "100" in vals:
                    sel.select_option("100")
                    page.wait_for_timeout(2500)
                    break
            filas = []
            for row in page.locator("table tbody tr").all():
                texts = [c.inner_text().strip() for c in row.locator("td").all()]
                if len(texts) >= 8:
                    filas.append(texts)
            ultimo, error = filas, None
            if any(term in t[4].lower() for t in filas):
                return filas
        except Exception as e:
            error = e
    if error is not None:
        raise error
    return ultimo


def scrape():
    from playwright.sync_api import sync_playwright

    resultado = {}
    ahora = datetime.now()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_context(locale="es-EC", user_agent=UA).new_page()
            combos = errores = 0
            ultimo_error = None
            for tipo_val, tipo_name in TIPOS:
                for term in TERMS:
                    combos += 1
                    try:
                        filas_busqueda = buscar(page, tipo_val, term)
                    except Exception as e:
                        errores += 1
                        ultimo_error = e
                        log(f"busqueda fallida ({tipo_name}/{term}): {str(e).splitlines()[0][:150]}")
                        continue
                    for t in filas_busqueda:
                        codigo, prov, desc, estado, limite, entidad = t[1], t[3], t[4], t[5], t[6], t[7]
                        contacto = t[9] if len(t) > 9 else ""
                        if not any(c in (prov + " " + entidad).upper() for c in CERCA):
                            continue
                        d = desc.lower()
                        if any(k in d for k in ("extintor", "pqs", "polvo quimico", "polvo químico", "co2")):
                            nivel = "relevante"
                        elif "incendio" in d or "recarga" in d:
                            nivel = "info"
                        else:
                            continue
                        lim = parse_fecha(limite)
                        vigente = estado.strip().lower() == "en curso" and lim is not None and lim > ahora
                        resultado[codigo] = {
                            "codigo": codigo, "tipo": tipo_name, "prov": prov, "desc": desc,
                            "entidad": entidad, "limite": limite, "limite_dt": lim,
                            "contacto": contacto.replace("\n", " | "), "nivel": nivel, "vigente": vigente,
                        }
            if errores == combos:
                raise RuntimeError(f"todas las busquedas fallaron: {ultimo_error}")
        finally:
            browser.close()
    return list(resultado.values())


def faltan(lim):
    if lim is None:
        return "?"
    s = (lim - datetime.now()).total_seconds()
    if s <= 0:
        return "vencido"
    d, h = int(s // 86400), int((s % 86400) // 3600)
    return f"{d} d {h} h" if d else f"{h} h {int((s % 3600) // 60)} min"


def mostrar_popup(banner, color, cuerpo, url2=""):
    TEXTO.write_text(f"{banner}\n{color}\n{PORTAL_URL}\n{url2}\n{cuerpo}", encoding="utf-8-sig")
    r = subprocess.run(["schtasks", "/run", "/tn", "SERCOP_Alerta"], capture_output=True, text=True)
    if r.returncode != 0:
        log(f"schtasks /run SERCOP_Alerta fallo: {r.stderr.strip() or r.stdout.strip()}")
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
             "-File", str(BASE / "alerta_popup.ps1")],
            creationflags=0x08000000 | 0x00000200,
        )


def push_celular(titulo, cuerpo):
    if not NTFY.exists():
        return
    try:
        topic = NTFY.read_text(encoding="utf-8").strip()
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}", data=cuerpo.encode("utf-8"),
            headers={"Title": titulo, "Priority": "urgent", "Tags": "fire,rotating_light"},
        )
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        log(f"ntfy fallo: {e}")


def encolar_preparacion(nuevos):
    """Deja en cola la preparación del borrador (la ejecuta la tarea SERCOP_Preparar, sin límite de 10 min)."""
    try:
        with open(COLA, "a", encoding="utf-8") as fh:
            for f in nuevos:
                fh.write(json.dumps({"codigo": f["codigo"], "estado": "En Curso",
                                     "firmar": f["tipo"] == "Ínfima Cuantía"}, ensure_ascii=False) + "\n")
        r = subprocess.run(["schtasks", "/run", "/tn", "SERCOP_Preparar"], capture_output=True, text=True)
        if r.returncode != 0:
            log(f"schtasks /run SERCOP_Preparar fallo: {r.stderr.strip() or r.stdout.strip()}")
        else:
            log(f"preparación en cola: {[f['codigo'] for f in nuevos]}")
    except Exception as e:
        log(f"no se pudo encolar la preparación: {e}")


def recordar(filas, vistos):
    """Recuerda cada hora los procesos relevantes sin decisión a los que les faltan menos de 24 h."""
    ahora = datetime.now()
    cambios = False
    for f in filas:
        if not (f["vigente"] and f["nivel"] == "relevante") or decisiones.resuelto(f["codigo"]):
            continue
        lim = f["limite_dt"]
        if lim is None or (lim - ahora).total_seconds() > 24 * 3600:
            continue
        v = vistos.get(f["codigo"], {})
        ult = v.get("recordatorio")
        if ult and (ahora - datetime.fromisoformat(ult)).total_seconds() < 3600:
            continue
        v["recordatorio"] = ahora.isoformat(timespec="seconds")
        vistos[f["codigo"]] = v
        cambios = True
        cuerpo = (f"RECORDATORIO: AUN SIN DECISION\nENTIDAD: {f['entidad']}\nCODIGO: {f['codigo']}\nOBJETO: {f['desc']}\n"
                  f"LIMITE: {f['limite']}   (faltan {faltan(lim)})\n\nDecide: py decidir.py {f['codigo']} participa | descarta | enviado")
        if (lim - ahora).total_seconds() < 6 * 3600:
            mostrar_popup(f"QUEDAN {faltan(lim).upper()} - DECIDE YA", "Red", cuerpo)
        push_celular("Quedan " + faltan(lim), cuerpo[:600])
        log(f"recordatorio {f['codigo']} faltan {faltan(lim)}")
    if cambios:
        guardar(VISTOS, vistos)


def alertar(nuevos):
    bloques = []
    for f in nuevos:
        extra = "" if f["tipo"] == "Ínfima Cuantía" else "\n(Proceso grande: revisar si aplica antes de cotizar)"
        bloques.append(
            f"TIPO: {f['tipo']}\nCODIGO: {f['codigo']}\nENTIDAD: {f['entidad']}\n"
            f"OBJETO: {f['desc']}\nLUGAR: {f['prov']}\n"
            f"LIMITE: {f['limite']}   (faltan {faltan(f['limite_dt'])})\n"
            f"CONTACTO: {f['contacto']}{extra}"
        )
    cuerpo = ("\n\n" + "-" * 60 + "\n\n").join(bloques)
    with open(ALERTAS, "a", encoding="utf-8") as fh:
        fh.write(f"===== {datetime.now():%Y-%m-%d %H:%M} =====\n{cuerpo}\n\n")
    for f in nuevos:
        log(f"ALERTA nuevo {f['tipo']} {f['codigo']} {f['entidad']} limite {f['limite']}")
    n = len(nuevos)
    banner = "NUEVO PROCESO DE EXTINTORES EN SERCOP" if n == 1 else f"{n} NUEVOS PROCESOS DE EXTINTORES EN SERCOP"
    mostrar_popup(banner, "Red", cuerpo)
    push_celular(banner, cuerpo[:900])
    encolar_preparacion(nuevos)


def registrar_fallo(detalle):
    est = cargar(ESTADO, {"fallos": 0})
    est["fallos"] = est.get("fallos", 0) + 1
    guardar(ESTADO, est)
    log(f"FALLO #{est['fallos']}: {detalle}")
    if est["fallos"] == FALLOS_PARA_AVISAR:
        mostrar_popup(
            "EL VIGILANTE SERCOP NO PUEDE REVISAR", "DarkOrange",
            f"Lleva {FALLOS_PARA_AVISAR} revisiones seguidas con error (unas 3 horas).\n"
            "Puede que el portal este caido o haya cambiado.\n\nUltimo error:\n" + detalle[-600:],
        )


def main():
    seed = "--seed" in sys.argv
    try:
        filas = scrape()
    except Exception:
        registrar_fallo(traceback.format_exc())
        return 1
    guardar(ESTADO, {"fallos": 0})

    vistos = cargar(VISTOS, {})
    nuevos_rel, nuevos_info = [], []
    for f in filas:
        if f["codigo"] in vistos:
            continue
        vistos[f["codigo"]] = {"visto": datetime.now().isoformat(timespec="seconds"), "nivel": f["nivel"]}
        if f["vigente"]:
            (nuevos_rel if f["nivel"] == "relevante" else nuevos_info).append(f)
    guardar(VISTOS, vistos)

    if seed:
        log(f"SEED: {len(filas)} procesos registrados como ya vistos")
        return 0
    for f in nuevos_info:
        log(f"info (sin alerta) {f['tipo']} {f['codigo']} {f['desc'][:80]}")
    recordar(filas, vistos)
    nuevos_rel = [f for f in nuevos_rel if not decisiones.resuelto(f["codigo"])]
    if nuevos_rel:
        alertar(nuevos_rel)
    else:
        log(f"revision ok: {len(filas)} coincidencias, 0 nuevos relevantes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
