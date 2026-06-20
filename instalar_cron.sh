#!/bin/bash
# Instala el monitor de NCOs como cron job.
# Corre cada 2 horas, de lunes a viernes, entre 7am y 8pm.
#
# Uso:
#   chmod +x instalar_cron.sh
#   GMAIL_USER=tu@gmail.com GMAIL_APP_PASS=xxxx P12_PASS=tuClave ./instalar_cron.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(which python3)"
MONITOR="$SCRIPT_DIR/monitor.py"
LOG="$SCRIPT_DIR/monitor.log"

if [ -z "$GMAIL_USER" ] || [ -z "$GMAIL_APP_PASS" ]; then
  echo "ERROR: Define GMAIL_USER y GMAIL_APP_PASS antes de correr este script."
  echo "  export GMAIL_USER=alejosl0801@gmail.com"
  echo "  export GMAIL_APP_PASS=xxxx-xxxx-xxxx-xxxx"
  exit 1
fi

# Línea cron: cada 2 horas, L-V, 7:00-20:00
CRON_LINE="0 7,9,11,13,15,17,19 * * 1-5 GMAIL_USER=$GMAIL_USER GMAIL_APP_PASS=$GMAIL_APP_PASS P12_PASS=${P12_PASS:-} $PYTHON $MONITOR >> $LOG 2>&1"

# Eliminar entradas anteriores de este monitor y agregar la nueva
(crontab -l 2>/dev/null | grep -v "$MONITOR"; echo "$CRON_LINE") | crontab -

echo "✅ Cron instalado:"
echo "   $CRON_LINE"
echo ""
echo "Verificar con: crontab -l"
echo "Ver log con:   tail -f $LOG"
