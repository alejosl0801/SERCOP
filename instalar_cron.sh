#!/bin/bash
# Instala el monitor de NCOs como cron job (Linux/Mac)
# Corre cada 2 horas de L-V 7am-8pm
#
# Uso: GMAIL_USER=... GMAIL_APP_PASS=... bash instalar_cron.sh

set -e

if [ -z "$GMAIL_USER" ] || [ -z "$GMAIL_APP_PASS" ]; then
  echo "ERROR: Define GMAIL_USER y GMAIL_APP_PASS antes de correr este script."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(which python3)"
LOG="$SCRIPT_DIR/monitor.log"

# Crear entrada de cron
CRON_LINE="0 7-20/2 * * 1-5 GMAIL_USER=$GMAIL_USER GMAIL_APP_PASS=$GMAIL_APP_PASS $PYTHON $SCRIPT_DIR/monitor.py --auto-proforma >> $LOG 2>&1"

# Agregar al crontab sin duplicar
(crontab -l 2>/dev/null | grep -v "monitor.py"; echo "$CRON_LINE") | crontab -

echo "✅ Cron instalado. Verificar con: crontab -l"
echo "   Log en: $LOG"
