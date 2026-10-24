# -*- coding: utf-8 -*-
"""Reporte semanal SERCOP: alertas, decisiones y borradores de los últimos 7 días. Lo deja en ESTADO/_REPORTES."""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
ESTADO = Path(r"C:\Users\HP\Dropbox\Previfuego\ESTADO")


def main():
    desde = datetime.now() - timedelta(days=7)
    alertas, fallos, revisiones = [], 0, 0
    log = BASE / "vigilante.log"
    if log.exists():
        for l in log.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+(.*)", l)
            if not m or datetime.fromisoformat(m.group(1)) < desde:
                continue
            if m.group(2).startswith("ALERTA"):
                alertas.append(m.group(2))
            elif m.group(2).startswith("FALLO"):
                fallos += 1
            elif m.group(2).startswith("revision ok"):
                revisiones += 1
    dec = {}
    try:
        dec = json.loads((BASE / "decisiones.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    semana = {k: v for k, v in dec.items() if v["historial"] and datetime.fromisoformat(v["historial"][-1]["cuando"]) >= desde}
    L = [f"# Reporte semanal SERCOP — {datetime.now():%Y-%m-%d}", "",
         f"- Revisiones del portal OK: {revisiones}  ·  fallos: {fallos}",
         f"- Procesos de extintores alertados: {len(alertas)}", ""]
    if alertas:
        L += ["## Alertas"] + [f"- {a}" for a in alertas] + [""]
    if semana:
        L += ["## Decisiones"] + [f"- {v['estado']}: {k} {v.get('nota', '')}" for k, v in semana.items()] + [""]
    ganados = [k for k, v in dec.items() if v["estado"] == "ganado"]
    enviados = [k for k, v in dec.items() if v["estado"] in ("enviado", "ganado", "perdido")]
    L += ["## Acumulado", f"- Enviados: {len(enviados)}  ·  Ganados: {len(ganados)}", ""]
    salida = ESTADO / "_REPORTES"
    salida.mkdir(parents=True, exist_ok=True)
    f = salida / f"reporte_{datetime.now():%Y-%m-%d}.md"
    f.write_text("\n".join(L), encoding="utf-8")
    print(f)


if __name__ == "__main__":
    main()

