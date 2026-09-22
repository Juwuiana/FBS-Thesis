"""Shows what the battery sensor reports so you can verify units before trusting any numbers.
    python -m scripts.battery_probe            (run it unplugged AND plugged in, compare)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ml.green_metrics import BatteryReader  # noqa: E402
from config import Config  # noqa: E402

d = Config.BATTERY_SYSFS_DIR
print("Directory:", d)
for n in ("voltage_now", "current_now", "temp", "capacity", "status"):
    try:
        print(f"  {n:12}", open(os.path.join(d, n)).read().strip())
    except OSError as e:
        print(f"  {n:12} UNREADABLE ({e.__class__.__name__})")

r = BatteryReader(d, Config.CURRENT_NOW_UNIT)
s = r.sample()
if s is None:
    print("\nResult: sensor NOT readable -> the app will label readings 'estimated'.")
else:
    raw = int(open(os.path.join(d, "current_now")).read().strip())
    print(f"\nDetected current unit : {r.current_unit(raw)} (override with FBS_CURRENT_UNIT)")
    print(f"Power                 : {s['power_w']:.2f} W   temp {s['temp_c']} C   level {s['level_pct']}%")
    print(f"Charging              : {s['charging']}")
    print("Sanity: a phone with the screen off usually draws roughly 0.3-2 W on battery.")
    if s["charging"]:
        print("NOTE: charging - this is charge current, NOT what the phone consumes. "
              "Unplug for real measurements.")
