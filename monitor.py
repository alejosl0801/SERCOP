#!/usr/bin/env python3
"""
Monitoreo continuo de NCOs en SERCOP.
Corre el scraper, detecta procesos nuevos y envía email de alerta.

Uso:
  GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py
  GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py --loop --intervalo 120
  P12_PASS=... GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py --loop --auto-proforma
  P12_PASS=... SERCOP_USER=... SERCOP_PASS=... python3 monitor.py --loop --auto-proforma --auto-upload
"""
import argparse
import json
import re as _re
import smtplib
import subprocess
import sys
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import os

BASE_DIR   = Path(__file__).parent
NCO_JSON   = BASE_DIR / "nco-guayas.json"
VISTOS     = BASE_DIR / "nco-vistos.json"
LOG_FILE   = BASE_DIR / "monitor.log"

GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASS", "")
EMAIL_DEST = "alejosl0801@gmail.com"
SERCOP_USER = os.environ.get("SERCOP_USER", "")
SERCOP_PASS = os.environ.get("SERCOP_PASS", "")

def cargar_vistos() -> set:
    if VISTOS.exists():
        return set(json.loads(VISTOS.read_text(encoding="utf-8")))
    return set()

def guardar_vistos(vistos: set):
    VISTOS.write_text(json.dumps(sorted(vistos), ensure_ascii=False, indent=2), encoding="utf-8")

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def enviar_email(asunto: str, cuerpo_html: str, cuerpo_texto: str):
    if not GMAIL_USER or not GMAIL_PASS:
        log("⚠ GMAIL_USER/GMAIL_APP_PASS no configurados — email no enviado.")
        return False
    msg = MIMEMultipart("alternative")
    msg["From"]    = GMAIL_USER
    msg["To"]      = EMAIL_DEST
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo_texto, "plain",  "utf-8"))
    msg.attach(MIMEText(cuerpo_html,  "html",   "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.send_message(msg)
        log(f"📧 Email enviado: {asunto}")
        return True
    except Exception as e:
        log(f"❌ Error enviando email: {e}")
        return False

def build_email_ncos(nuevos: list[dict]) -> tuple[str, str, str]:
    n = len(nuevos)
    asunto = f"🔔 PREVIFUEGO — {n} proceso{'s' if n>1 else ''} nuevo{'s' if n>1 else ''} en SERCOP"
    items_html = ""
    for nco in nuevos:
        items = nco.get("items", [])
        items_li = "".join(
            f"<li>{it.get('descripcion','?')} — {it.get('cantidad','?')} {it.get('unidad','')}</li>"
            for it in items
        ) or "<li><em>Sin ítems detectados — revisar TDR adjunto</em></li>"
        fecha_lim = nco.get("fecha_limite", "—")
        url       = nco.get("url_detalle", "#")
        entidad   = nco.get("entidad", "—")
        codigo    = nco.get("codigo", "—")
        canton    = nco.get("provincia_canton", "—")
        func      = nco.get("funcionario", "—")
        email_ent = nco.get("email", "—")
        items_html += f"""
        <div style="border:1px solid #ddd;border-radius:6px;padding:14px;margin-bottom:16px;font-family:Arial,sans-serif;">
          <h3 style="margin:0 0 8px;color:#1a3a5c;">{codigo}</h3>
          <table style="width:100%;font-size:13px;border-collapse:collapse;">
            <tr><td style="width:140px;color:#666;padding:2px 0;">Entidad</td><td><strong>{entidad}</strong></td></tr>
            <tr><td style="color:#666;padding:2px 0;">Cantón</td><td>{canton}</td></tr>
            <tr><td style="color:#666;padding:2px 0;">Fecha límite</td><td><strong style="color:#c00;">{fecha_lim}</strong></td></tr>
            <tr><td style="color:#666;padding:2px 0;">Funcionario</td><td>{func}</td></tr>
            <tr><td style="color:#666;padding:2px 0;">Email entidad</td><td><a href="mailto:{email_ent}">{email_ent}</a></td></tr>
          </table>
          <p style="margin:10px 0 4px;font-size:13px;font-weight:bold;color:#1a3a5c;">Ítems requeridos:</p>
          <ul style="font-size:13px;margin:0 0 10px 18px;padding:0;">{items_li}</ul>
          <a href="{url}" style="display:inline-block;background:#1a3a5c;color:#fff;padding:6px 14px;border-radius:4px;text-decoration:none;font-size:13px;">Ver en SERCOP →</a>
        </div>"""
    html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:680px;margin:0 auto;padding:20px;">
  <div style="background:#1a3a5c;color:#fff;padding:16px 20px;border-radius:6px 6px 0 0;">
    <h2 style="margin:0;">🔔 PREVIFUEGO — Nuevos procesos NCO</h2>
    <p style="margin:4px 0 0;font-size:13px;opacity:.8;">{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — {n} proceso{'s' if n>1 else ''} nuevo{'s' if n>1 else ''}</p>
  </div>
  <div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 6px 6px;">
    {items_html}
    <hr style="border:none;border-top:1px solid #eee;margin:16px 0;">
    <p style="font-size:12px;color:#888;margin:0;">Sistema automático PREVIFUEGO</p>
  </div>
</body></html>"""
    txt_bloques = []
    for nco in nuevos:
        items = nco.get("items", [])
        items_txt = "\n".join(f"  - {it.get('descripcion','?')}: {it.get('cantidad','?')} {it.get('unidad','')}" for it in items) or "  (sin ítems detectados)"
        txt_bloques.append(f"{─*50}\n{nco.get('codigo','—')}\nEntidad: {nco.get('entidad','—')}\nCantón: {nco.get('provincia_canton','—')}\nFecha límite: {nco.get('fecha_limite','—')}\nÍtems:\n{items_txt}\nURL: {nco.get('url_detalle','')}")
    texto = f"PREVIFUEGO — {n} NCO(s) nuevo(s)\n{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n" + "\n\n".join(txt_bloques)
    return asunto, html, texto

def correr_scraper() -> bool:
    log("🔍 Corriendo scraper NCO...")
    result = subprocess.run([sys.executable, str(BASE_DIR / "scripts" / "scrape_nco.py")],
                            capture_output=True, text=True, cwd=str(BASE_DIR))
    if result.returncode != 0:
        log(f"❌ Scraper falló:\n{result.stderr[-800:]}")
        return False
    log("✅ Scraper completado")
    return True

def detectar_nuevos() -> list[dict]:
    if not NCO_JSON.exists():
        log("⚠ nco-guayas.json no existe todavía.")
        return []
    with open(NCO_JSON, encoding="utf-8") as f:
        data = json.load(f)
    vistos   = cargar_vistos()
    procesos = data.get("procesos", [])
    nuevos   = [p for p in procesos if p.get("codigo") not in vistos]
    vistos.update(p.get("codigo") for p in procesos)
    guardar_vistos(vistos)
    return nuevos

def auto_proforma(nuevos: list[dict], auto_upload: bool = False):
    for nco in nuevos:
        codigo = nco.get("codigo", "")
        log(f"📄 Generando proforma para {codigo}...")
        result = subprocess.run([sys.executable, str(BASE_DIR / "generar_proforma.py"), "--nco", codigo],
                                capture_output=True, text=True, cwd=str(BASE_DIR), env={**os.environ})
        if result.returncode != 0:
            log(f"⚠ Proforma con advertencias ({codigo}):\n{result.stderr[-400:]}")
            continue
        log(f"✅ Proforma generada: {codigo}")
        if not auto_upload: continue
        if not SERCOP_USER or not SERCOP_PASS:
            log("⚠ SERCOP_USER/SERCOP_PASS no configurados — upload omitido")
            continue
        safe = _re.sub(r"[^\w\-]", "_", codigo)
        pdf_path = BASE_DIR / "output" / f"Proforma_{safe}_PREVIFUEGO_signed.pdf"
        if not pdf_path.exists():
            log(f"⚠ PDF firmado no encontrado: {pdf_path.name} — upload omitido")
            continue
        log("🌐 Subiendo proforma al portal SERCOP...")
        up = subprocess.run([sys.executable, str(BASE_DIR / "scripts" / "upload_proforma.py"),
                             "--nco", codigo, "--pdf", str(pdf_path)],
                            capture_output=True, text=True, cwd=str(BASE_DIR), env={**os.environ})
        if up.returncode == 0:   log(f"✅ Proforma subida al portal: {codigo}")
        elif up.returncode == 2: log(f"⚠ Upload manual requerido ({codigo})")
        else:                    log(f"❌ Error en upload ({codigo}):\n{up.stdout[-400:]}")

def ciclo(auto_gen: bool = False, auto_upload: bool = False):
    log("━" * 50)
    if not correr_scraper(): return
    nuevos = detectar_nuevos()
    if not nuevos:
        log("ℹ Sin procesos nuevos.")
        return
    log(f"🆕 {len(nuevos)} proceso(s) nuevo(s): {[n.get('codigo') for n in nuevos]}")
    asunto, html, texto = build_email_ncos(nuevos)
    enviar_email(asunto, html, texto)
    if auto_gen:
        auto_proforma(nuevos, auto_upload)

def main():
    parser = argparse.ArgumentParser(description="Monitor NCO SERCOP")
    parser.add_argument("--loop",          action="store_true")
    parser.add_argument("--intervalo",     type=int, default=120)
    parser.add_argument("--auto-proforma", action="store_true")
    parser.add_argument("--auto-upload",   action="store_true")
    args = parser.parse_args()
    log("🚀 Monitor PREVIFUEGO iniciado")
    log(f"   Email destino : {EMAIL_DEST}")
    log(f"   Auto-proforma : {'sí' if args.auto_proforma else 'no'}")
    log(f"   Auto-upload   : {'sí' if args.auto_upload else 'no'}")
    if args.loop: log(f"   Intervalo     : cada {args.intervalo} minutos")
    ciclo(args.auto_proforma, args.auto_upload)
    if args.loop:
        while True:
            log(f"💤 Próxima verificación en {args.intervalo} minutos...")
            time.sleep(args.intervalo * 60)
            ciclo(args.auto_proforma, args.auto_upload)

if __name__ == "__main__":
    main()
