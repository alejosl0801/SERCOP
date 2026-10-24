# -*- coding: utf-8 -*-
"""Registro de decisiones sobre procesos: participa / descarta / enviado / ganado / perdido.

Uso:  py decidir.py NIC-xxxx participa|descarta|enviado|ganado|perdido ["motivo o nota"]
      py decidir.py --lista
Lo usa el vigilante (no recuerda procesos ya resueltos) y el reporte semanal.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parent / "decisiones.json"
ESTADOS = ("participa", "descarta", "descarte_auto", "enviado", "ganado", "perdido")
RESUELTOS = ("descarta", "descarte_auto", "enviado", "ganado", "perdido")


def cargar():
    try:
        return json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def registrar(codigo, estado, nota=""):
    d = cargar()
    hist = d.get(codigo, {}).get("historial", [])
    hist.append({"estado": estado, "nota": nota, "cuando": datetime.now().isoformat(timespec="seconds")})
    d[codigo] = {"estado": estado, "nota": nota, "historial": hist}
    ARCHIVO.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def estado(codigo):
    return cargar().get(codigo, {}).get("estado")


def resuelto(codigo):
    return estado(codigo) in RESUELTOS


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--lista"] or not a:
        for k, v in cargar().items():
            print(f"{v['estado']:<14} {k}  {v.get('nota', '')}")
    elif len(a) >= 2 and a[1] in ESTADOS:
        registrar(a[0], a[1], " ".join(a[2:]))
        print(f"{a[0]} -> {a[1]}")
    else:
        print(__doc__)
