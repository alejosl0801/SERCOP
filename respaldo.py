# -*- coding: utf-8 -*-
"""Respaldo diario de la configuración del sistema SERCOP a Dropbox (conserva 14)."""
import zipfile
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DESTINO = Path(r"C:\Users\HP\Dropbox\Previfuego\RESPALDO_SERCOP")
EXTRA = [Path.home() / ".sercop" / "p12.dpapi"]
LOCALES = ["politica_sercop.json", "precios.json", "vistos.json", "decisiones.json", "ntfy_topic.txt", "nco-guayas.json", "procesados.json"]


def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    out = DESTINO / f"sercop_{datetime.now():%Y%m%d}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(BASE.glob("*.py")) + sorted(BASE.glob("*.ps1")) + sorted(BASE.glob("*.md")):
            z.write(f, f.name)
        for n in LOCALES:
            if (BASE / n).exists():
                z.write(BASE / n, n)
        for f in EXTRA:
            if f.exists():
                z.write(f, "sercop_dir/" + f.name)
    for viejo in sorted(DESTINO.glob("sercop_*.zip"))[:-14]:
        viejo.unlink()
    print(out)


if __name__ == "__main__":
    main()
