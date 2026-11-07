"""Read-only process CPU/RSS sampling for on-headset resource benchmarking."""
from __future__ import annotations
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def main_pid() -> int | None:
    binary = shutil.which('systemctl')
    if not binary:
        return None
    try:
        p = subprocess.run([binary, '--user', 'show', 'hey-frame.service',
                            '-p', 'MainPID', '--value'], capture_output=True,
                           text=True, check=False, timeout=3)
        pid = int(p.stdout.strip())
        return pid if pid > 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def process_stats(pid: int, procroot=Path('/proc')) -> tuple[int,int]:
    if pid <= 0:
        raise ValueError('PID must be positive')
    stat = (procroot/str(pid)/'stat').read_text()
    # comm can contain spaces, so split only after the closing parenthesis.
    fields = stat.rsplit(')', 1)[1].strip().split()
    jiffies = int(fields[11]) + int(fields[12])  # fields utime, stime
    status = (procroot/str(pid)/'status').read_text()
    match = re.search(r'^VmRSS:\s+(\d+)\s+kB',status,re.M)
    rss_kb = int(match.group(1)) if match else 0
    return jiffies, rss_kb


def measure(seconds=10, pid: int | None = None, clock=time.monotonic, pause=time.sleep):
    """Measure app load; no background service gets started or modified."""
    pid = pid or main_pid()
    if not pid:
        raise RuntimeError('Hey Frame service is not running. Use hey-frame start first.')
    seconds = max(3,min(int(seconds),120))
    before, rss1 = process_stats(pid)
    t0 = clock()
    pause(seconds)
    after, rss2 = process_stats(pid)
    elapsed = clock()-t0
    ticks = os.sysconf('SC_CLK_TCK')
    cpu = max(0,(after-before)/ticks / max(elapsed,0.001)*100)
    return {'pid':pid,'elapsed':round(elapsed,1),'cpu_percent':round(cpu,1),
            'rss_mib':round(max(rss1,rss2)/1024,1)}


def describe(results) -> str:
    return (f"PID {results['pid']} | sampled {results['elapsed']}s | "
            f"average CPU {results['cpu_percent']}% of one core | "
            f"peak sampled RSS {results['rss_mib']} MiB. "
            'Not a headset battery-life or gaming performance measurement.')
