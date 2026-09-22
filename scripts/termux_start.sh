#!/data/data/com.termux/files/usr/bin/bash
# Starts the web app, the connectivity monitor, and the telemetry sampler if the battery sensor
# is readable.
#   bash scripts/termux_start.sh            normal
#   DEMO=1 bash scripts/termux_start.sh     with the presentation demo controls
cd "$(dirname "$0")/.."
. .venv/bin/activate
command -v termux-wake-lock >/dev/null && termux-wake-lock     # keep the CPU awake while serving
[ "$DEMO" = "1" ] && export FBS_DEMO_MODE=1
export FLASK_DEBUG=0

if python - <<'PY'
import sys; from app.ml.green_metrics import BatteryReader; from config import Config
sys.exit(0 if BatteryReader(Config.BATTERY_SYSFS_DIR, Config.CURRENT_NOW_UNIT).available() else 1)
PY
then
  flask --app run telemetry-loop > telemetry.log 2>&1 &
  echo "Telemetry sampler started (log: telemetry.log)"
else
  echo "Battery sensor not readable: readings will be labelled 'estimated'."
fi

# Connectivity monitor: records DISCONNECT/RECONNECT events and drives the offline queue.
# What "online" means is FBS_PROBE_TARGETS in .env (default: the internet).
flask --app run connectivity-monitor > connectivity.log 2>&1 &
echo "Connectivity monitor started (log: connectivity.log)"

IP=$(ip -4 addr show wlan0 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1)
echo "Open on this phone : http://localhost:5000"
[ -n "$IP" ] && echo "Open from a laptop : http://$IP:5000   (same Wi-Fi/hotspot)"
python run.py
