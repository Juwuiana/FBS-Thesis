#!/data/data/com.termux/files/usr/bin/bash
# One-time setup inside Termux. Run from the project folder:  bash scripts/termux_setup.sh
set -e
pkg update -y && pkg upgrade -y
pkg install -y python sqlite unzip net-tools
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-phone.txt
[ -f .env ] || cp .env.example .env
echo
echo "Setup done. Next:"
echo "  1) python -m scripts.battery_probe"
echo "  2) flask --app run create-admin --email you@example.com"
echo "  3) bash scripts/termux_start.sh"
