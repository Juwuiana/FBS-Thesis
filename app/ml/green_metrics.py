"""Per-inference energy/carbon measurement for a phone running the app under Termux.

Valid only while the phone runs on battery (not charging): see measure().
Method: sample battery voltage x current before and after the inference, average the two
readings as the device power, and multiply by the measured wall time. If the battery
nodes are unreadable (laptop, locked-down phone) fall back to a CPU-share x TDP estimate
and tag the row 'estimated' so it is never mistaken for a measurement.

Caveat for the thesis: one instantaneous battery sample is noisy and covers the whole
phone, so per-inference energy is an attribution, not a direct meter reading.
"""
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional


def _read_int(path: str) -> Optional[int]:
    try:
        with open(path) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


class BatteryReader:
    def __init__(self, sysfs_dir: str, current_unit: str = "auto"):
        self.dir = sysfs_dir
        self._unit = None if current_unit == "auto" else current_unit
        self._unit_locked = current_unit != "auto"

    def _node(self, name):
        return _read_int(os.path.join(self.dir, name))

    def available(self) -> bool:
        return self._node("voltage_now") is not None and self._node("current_now") is not None

    @staticmethod
    def guess_current_unit(sample_abs_current: int) -> str:
        # Phones normally draw 50 mA..3 A: that is 50_000..3_000_000 in uA or 50..3000 in mA.
        return "uA" if sample_abs_current > 20_000 else "mA"

    def current_unit(self, raw_current: int) -> str:
        if self._unit is None and raw_current != 0:
            self._unit = self.guess_current_unit(abs(raw_current))  # cache first non-zero guess
        return self._unit or "uA"

    def sample(self) -> Optional[dict]:
        v_raw, i_raw = self._node("voltage_now"), self._node("current_now")
        if v_raw is None or i_raw is None:
            return None
        volts = v_raw / 1e6 if v_raw > 100_000 else v_raw / 1e3  # uV vs mV
        amps_div = 1e6 if self.current_unit(i_raw) == "uA" else 1e3
        amps = abs(i_raw) / amps_div  # sign flips between charging/discharging
        temp = self._node("temp")
        level = self._node("capacity")
        return {
            "power_w": volts * amps,
            "temp_c": temp / 10.0 if temp is not None else None,  # tenths of a degree
            "level_pct": float(level) if level is not None else None,
            "charging": self.is_charging(),
        }

    def is_charging(self) -> Optional[bool]:
        """Uses the 'status' node ("Charging"/"Full"/"Discharging"); None if unreadable."""
        try:
            with open(os.path.join(self.dir, "status")) as fh:
                return fh.read().strip().lower() in ("charging", "full")
        except OSError:
            return None


def rss_mb() -> float:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return 0.0


@dataclass
class Measurement:
    latency_ms: float = 0.0
    cpu_pct: float = 0.0
    ram_mb: float = 0.0
    power_w: float = 0.0
    energy_kwh: float = 0.0
    carbon_kg: float = 0.0
    method: str = "estimated"


@contextmanager
def measure(reader: BatteryReader, emission_factor: float, idle_power_w: float = 0.0,
            tdp_w: float = 5.0):
    """Usage:  with measure(reader, factor) as m: <inference>   then read m.*"""
    m = Measurement()
    ncpu = os.cpu_count() or 1
    before = reader.sample()
    cpu0, t0 = time.process_time(), time.perf_counter()
    try:
        yield m
    finally:
        wall = max(time.perf_counter() - t0, 1e-9)
        cpu = time.process_time() - cpu0
        after = reader.sample()
        m.latency_ms = wall * 1000.0
        m.cpu_pct = min(100.0, cpu / wall / ncpu * 100.0)
        m.ram_mb = rss_mb()
        # While charging, current_now is the current flowing INTO the battery, not what the phone
        # itself draws, so those readings are not a consumption measurement. Only trust them when
        # the phone is running on its battery (status unreadable is treated as not charging).
        charging = bool((before or {}).get("charging") or (after or {}).get("charging"))
        if before and after and not charging:
            m.method = "battery"
            m.power_w = max((before["power_w"] + after["power_w"]) / 2.0 - idle_power_w, 0.0)
        else:
            m.method = "estimated"
            m.power_w = tdp_w * m.cpu_pct / 100.0
        m.energy_kwh = m.power_w * wall / 3.6e6
        m.carbon_kg = m.energy_kwh * emission_factor
