#!/usr/bin/env python3
"""
Monitoreo continuo de NCOs en SERCOP.
Corre el scraper, detecta procesos nuevos y envía email de alerta.

Uso:
  # Una sola verificación:
  GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py

  # Loop cada 2 horas (corre en segundo plano):
  GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py --loop --intervalo 120

  # Con generación automática de proforma:
  P12_PASS=... GMAIL_USER=... GMAIL_APP_PASS=... python3 monitor.py --loop --auto-proforma
"""
import argparse
import json
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

# ── Registro de NCOs ya vistos ────────────────────────────────────────────────

def cargar_vistos() -> set:
    if VISTOS.exists():
        return set(json.loads(VISTOS.read_text(encoding="utf-8")))
    return set()

def guardar_vistos(vistos: set):
    VISTOS.write_text(
        json.dumps(sorted(vistos), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

# ── Log ───────────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── Email ─────────────────────────────────────────────────────────────────────

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
    """Construye cuerpo HTML y texto plano del email de alerta."""
    n = len(nuevos)
    asunto = f"🔔 PREVIFUEGO — {n} proceso{'s' if n>1 else ''} nuevo{'s' if n>1 else ''} en SERCOP"

    # ── HTML ──────────────────────────────────────────────────────────────────
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
            <tr><td style="width:140px;color:#666;padding:2px 0;">Entidad</td>
                <td><strong>{entidad}</strong></td></tr>
            <tr><td style="color:#666;padding:2px 0;">Cantón</td>
                <td>{canton}</td></tr>
            <tr><td style="color:#666;padding:2px 0;">Fecha límite</td>
                <td><strong style="color:{'#c00' if fecha_lim else '#333'};">{fecha_lim}</strong></td></tr>
            <tr><td style="color:#666;padding:2px 0;">Funcionario</td>
                <td>{func}</td></tr>
            <tr><td style="color:#666;padding:2px 0;">Email entidad</td>
                <td><a href="mailto:{email_ent}">{email_ent}</a></td></tr>
          </table>
          <p style="margin:10px 0 4px;font-size:13px;font-weight:bold;color:#1a3a5c;">Ítems requeridos:</p>
          <ul style="font-size:13px;margin:0 0 10px 18px;padding:0;">{items_li}</ul>
          <a href="{url}" style="display:inline-block;background:#1a3a5c;color:#fff;padding:6px 14px;
             border-radius:4px;text-decoration:none;font-size:13px;">Ver en SERCOP →</a>
        </div>"""

    html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:680px;margin:0 auto;padding:20px;">
  <div style="background:#1a3a5c;color:#fff;padding:16px 20px;border-radius:6px 6px 0 0;">
    <h2 style="margin:0;">🔔 PREVIFUEGO — Nuevos procesos NCO</h2>
    <p style="margin:4px 0 0;font-size:13px;opacity:.8;">
      {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — {n} proceso{'s' if n>1 else ''} nuevo{'s' if n>1 else ''}
    </p>
  </div>
  <div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 6px 6px;">
    {items_html}
    <hr style="border:none;border-top:1px solid #eee;margin:16px 0;">
    <p style="font-size:12px;color:#888;margin:0;">
      Para generar la proforma: <code>P12_PASS=... python3 generar_proforma.py --nco CODIGO</code><br>
      Sistema automático PREVIFUEGO
    </p>
  </div>
</body></html>"""

    # ── Texto plano ───────────────────────────────────────────────────────────
    txt_bloques = []
    for nco in nuevos:
        items = nco.get("items", [])
        items_txt = "\n".join(
            f"  - {it.get('descripcion','?')}: {it.get('cantidad','?')} {it.get('unidad','')}"
            for it in items
        ) or "  (sin ítems detectados)"
        txt_bloques.append(
            f"{'─'*50}\n"
            f"{nco.get('codigo','—')}\n"
            f"Entidad:     {nco.get('entidad','—')}\n"
            f"Cantón:      {nco.get('provincia_canton','—')}\n"
            f"Fecha límite:{nco.get('fecha_limite','—')}\n"
            f"Funcionario: {nco.get('funcionario','—')}\n"
            f"Email:       {nco.get('email','—')}\n"
            f"Ítems:\n{items_txt}\n"
            f"URL: {nco.get('url_detalle','')}"
        )
    texto = (
        f"PREVIFUEGO — {n} NCO(s) nuevo(s) detectado(s)\n"
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        + "\n\n".join(txt_bloques)
        + "\n\nPara generar proforma:\n"
          "  P12_PASS=... python3 generar_proforma.py --nco CODIGO"
    )

    return asunto, html, texto

# ── Scraper ───────────────────────────────────────────────────────────────────

def correr_scraper() -> bool:
    log("🔍 Corriendo scraper NCO...")
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "scripts" / "scrape_nco.py")],
        capture_output=True, text=True, cwd=str(BASE_DIR)
    )
    if result.returncode != 0:
        log(f"❌ Scraper falló:\n{result.stderr[-800:]}")
        return False
    log("✅ Scraper completado")
    return True

# ── Detección de nuevos ───────────────────────────────────────────────────────

def detectar_nuevos() -> list[dict]:
    if not NCO_JSON.exists():
        log("⚠ nco-guayas.json no existe todavía.")
        return []

    with open(NCO_JSON, encoding="utf-8") as f:
        data = json.load(f)

    vistos   = cargar_vistos()
    procesos = data.get("procesos", [])
    nuevos   = [p for p in procesos if p.get("codigo") not in vistos]

    # Marcar todos como vistos
    vistos.update(p.get("codigo") for p in procesos)
    guardar_vistos(vistos)

    return nuevos

# ── Auto-proforma ─────────────────────────────────────────────────────────────

def auto_proforma(nuevos: list[dict]):
    for nco in nuevos:
        codigo = nco.get("codigo", "")
        log(f"📄 Generando proforma para {codigo}...")
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "generar_proforma.py"), "--nco", codigo],
            capture_output=True, text=True, cwd=str(BASE_DIR),
            env={**os.environ}
        )
        if result.returncode == 0:
            log(f"✅ Proforma generada: {codigo}")
        else:
            log(f"⚠ Proforma con advertencias ({codigo}):\n{result.stderr[-400:]}")

# ── Ciclo principal ───────────────────────────────────────────────────────────

def ciclo(auto_gen: bool = False):
    log("━" * 50)
    ok = correr_scraper()
    if not ok:
        return

    nuevos = detectar_nuevos()
    if not nuevos:
        log("ℹ Sin procesos nuevos.")
        return

    log(f"🆕 {len(nuevos)} proceso(s) nuevo(s): {[n.get('codigo') for n in nuevos]}")

    asunto, html, texto = build_email_ncos(nuevos)
    enviar_email(asunto, html, texto)

    if auto_gen:
        auto_proforma(nuevos)


def main():
    parser = argparse.ArgumentParser(description="Monitor NCO SERCOP")
    parser.add_argument("--loop",          action="store_true", help="Correr en bucle indefinido")
    parser.add_argument("--intervalo",     type=int, default=120, help="Minutos entre ciclos (default: 120)")
    parser.add_argument("--auto-proforma", action="store_true", help="Generar proforma automáticamente al detectar nuevo NCO")
    args = parser.parse_args()

    log("🚀 Monitor PREVIFUEGO iniciado")
    log(f"   Email destino : {EMAIL_DEST}")
    log(f"   Auto-proforma : {'sí' if args.auto_proforma else 'no'}")
    if args.loop:
        log(f"   Intervalo     : cada {args.intervalo} minutos")

    ciclo(args.auto_proforma)

    if args.loop:
        while True:
            log(f"💤 Próxima verificación en {args.intervalo} minutos...")
            time.sleep(args.intervalo * 60)
            ciclo(args.auto_proforma)


if __name__ == "__main__":
    main()
