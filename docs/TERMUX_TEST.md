# Testing on an Android phone with Termux

## 1. Install
- Install **Termux from F-Droid** (or the GitHub releases). The Play Store build is outdated and
  `pkg` will not work.
- Copy the project zip to the phone (Downloads), then in Termux:
      termux-setup-storage            # allow storage, accept the prompt
      cp ~/storage/downloads/FBS-Thesis-feature-green-metrics.zip ~
      pkg install unzip && unzip FBS-Thesis-feature-green-metrics.zip
      cd FBS-Thesis-feature-green-metrics
      bash scripts/termux_setup.sh
  The setup installs only `requirements-phone.txt` (pure Python). Do NOT `pip install -r requirements.txt`:
  it is a full desktop freeze (numba, opencv, matplotlib...) that will not build on Termux.

## 2. Check the battery sensor (most important step)
      python -m scripts.battery_probe
Run it **unplugged**, then **plugged in**.
- Values printed and a sensible power (about 0.3-2 W, screen off, on battery) = the sensor works.
- "UNREADABLE" = Android is blocking `/sys/class/power_supply` for Termux on this device. The app still
  runs but labels readings `estimated`. Tell me and I will add a `termux-battery-status` fallback.
- If the wattage is 1000x too big or small, set `FBS_CURRENT_UNIT=uA` or `mA` in `.env`.
- While **charging**, the reading is charge current, not consumption. The app treats those readings as
  `estimated` and stores no telemetry power. Take real measurements on battery.

## 3. Run
      flask --app run create-admin --email you@example.com      # asks for a password
      DEMO=1 bash scripts/termux_start.sh
- On the phone: open http://localhost:5000 -> sign in -> Green Computing.
- From a laptop on the same Wi-Fi or the phone's hotspot: use the http://<ip>:5000 line the script prints.
- Stop with Ctrl+C. `termux-wake-lock` runs automatically; also set Termux to
  "Unrestricted" in Android battery settings so it isn't killed in the background.

## 4. What to check
| Check | Expected |
|---|---|
| `http://<ip>:5000/health` | `battery_readable: true` on a working phone |
| Green Computing -> Run 10 (unplugged) | Live Inference Log Source = `battery` |
| Same while plugged in | Source = `estimated` |
| Simulate connection loss -> Run 10 -> Restore connection | queue 10 -> 0, a gap with 10 records in Offline Events (demo controls; stop the real monitor first) |
| `flask --app run connectivity-status` | `Probe now: reachable`, and after the monitor starts `Monitor: running` |
| Restart Termux and the server | data is still there (SQLite file in `instance/`) |

## 5. Measure the idle baseline (unplugged, screen off)
      flask --app run telemetry-loop --idle --interval 10      # let it run ~5 min, then Ctrl+C
      sqlite3 instance/fbs_thesis.sqlite3 "SELECT ROUND(AVG(power_w),3), COUNT(*) FROM system_telemetry_log WHERE is_idle=1;"
Put the average into `.env` as `FBS_IDLE_POWER_W=<value>` (this is subtracted from per-inference power).

## 6. Controlled test-run protocol (for the thesis)
Fully charged, **unplugged**, screen off, Wi-Fi on, no other apps, fixed number of screenings (for example
4 x "Run 10" x 3 repetitions). Note the phone model, Android version, temperature and battery %; export
`green_computing_log` afterwards. Repeat per candidate model once `model.joblib` exists.

## 7. Test real link-loss detection
The monitor starts with `scripts/termux_start.sh`. Check it first:

      flask --app run connectivity-status          # probe result + what the database believes
      tail -f connectivity.log                     # transitions are logged here

1. Decide what "online" means in `.env` (`FBS_PROBE_TARGETS`, default = the internet; use the router's
   address to watch the Wi-Fi link instead). For a quick test lower `FBS_PROBE_INTERVAL_S=5`.
2. Turn Wi-Fi/mobile data off (or use airplane mode; `localhost` keeps working). After about
   `FAIL_THRESHOLD x INTERVAL` seconds the log prints `link DOWN` and the Green Computing page shows OFFLINE.
3. With `DEMO=1`, press **Run screening** a few times: they are queued through the real
   `on_visit_saved()` because the link is down. Check *Sync Queue* and *View All*.
4. Turn Wi-Fi back on. After `OK_THRESHOLD` good probes the log prints `link UP`, the gap closes with its
   record count and duration in *Offline Events* / *View full events log*. Records stay `QUEUED` because no
   sync transport is configured yet.
5. Kill the monitor (Ctrl+C). About 3 minutes later the page warns that the connectivity monitor is not running.
(Do not press the demo "Simulate connection loss / Restore connection" buttons during this test.)

## Known limits
- Detection delay is about `FAIL_THRESHOLD x INTERVAL` (45 s by default). If the monitor is not running,
  no gaps are recorded.
- The monitor watches the phone's own network link; it cannot see drafts held on other devices.
- A phone plugged in all day cannot measure its own consumption from the battery sensor; use controlled
  on-battery runs, or an inline USB power meter as a cross-check.
