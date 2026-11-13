"""Thermal guard: pause training when the laptop runs hot, resume after a cool-down.

Every 10 s it reads the GPU temperature (nvidia-smi) and, where Windows exposes it, the ACPI thermal-zone (CPU)
temperature. If either crosses its limit, every training process (ml/train.py and its data-loader workers) is
suspended (frozen, not killed, so no progress is lost), the guard waits 3 minutes, and resumes only once the
temperature is back under the resume threshold (otherwise it waits another 3 minutes).

usage: python ml/thermal_guard.py [--gpu-max 80] [--gpu-resume 70] [--cpu-max 90] [--cool 180]
"""
import argparse
import subprocess
import time
from datetime import datetime

import psutil


def gpu_temp():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        return max(int(x) for x in out if x.strip())
    except Exception:
        return None


def cpu_temp():
    """ACPI thermal zone in deci-Kelvin; not available on every laptop or without rights, then None."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
                              "-ErrorAction Stop | Measure-Object CurrentTemperature -Maximum).Maximum"],
                             capture_output=True, text=True, timeout=15).stdout.strip()
        return round(float(out) / 10 - 273.15) if out else None
    except Exception:
        return None


def training_procs():
    """Python processes whose script argument is ml/train.py (not shells or -c snippets that mention it)."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if not (p.info["name"] or "").lower().startswith("python"):
                continue
            args = [a.replace("\\", "/") for a in (p.info["cmdline"] or [])[1:3]]
            if any(a.endswith("ml/train.py") for a in args):
                procs.append(p)
                procs.extend(p.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return list({p.pid: p for p in procs}.values())


def log(msg):
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu-max", type=int, default=80)
    ap.add_argument("--gpu-resume", type=int, default=70)
    ap.add_argument("--cpu-max", type=int, default=90)
    ap.add_argument("--cool", type=int, default=180)
    a = ap.parse_args()
    log(f"guard on: pause at GPU >= {a.gpu_max} C or CPU >= {a.cpu_max} C, cool {a.cool}s, resume < {a.gpu_resume} C")
    for p in training_procs():  # never leave training frozen by a previous guard instance
        try:
            if p.status() == psutil.STATUS_STOPPED:
                p.resume()
                log(f"resumed stranded process {p.pid}")
        except psutil.Error:
            pass
    n = 0
    while True:
        g = gpu_temp()
        c = cpu_temp() if n % 3 == 0 else None
        n += 1
        hot = (g is not None and g >= a.gpu_max) or (c is not None and c >= a.cpu_max)
        procs = training_procs() if hot else []
        if hot and procs:
            for p in procs:
                try:
                    p.suspend()
                except psutil.Error:
                    pass
            log(f"HOT gpu={g} cpu={c}: paused {len(procs)} training processes, cooling {a.cool}s")
            while True:
                time.sleep(a.cool)
                g2 = gpu_temp()
                if g2 is None or g2 < a.gpu_resume:
                    break
                log(f"still warm gpu={g2}, cooling another {a.cool}s")
            for p in procs:
                try:
                    p.resume()
                except psutil.Error:
                    pass
            log(f"resumed training (gpu={gpu_temp()})")
        elif n % 30 == 0:
            log(f"ok gpu={g} cpu={c}")
        time.sleep(10)


if __name__ == "__main__":
    main()
