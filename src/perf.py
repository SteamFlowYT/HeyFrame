"""Read-only process CPU/RSS sampling for on-headset resource benchmarking."""
from __future__ import annotations
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def main_pid(service: str = 'hey-frame.service') -> int | None:
    binary = shutil.which('systemctl')
    if not binary:
        return None
    try:
        p = subprocess.run([binary, '--user', 'show', service,
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



def process_tree_stats(pid: int, procroot=Path('/proc')) -> tuple[int, int, int]:
    """Cumulative CPU ticks + current RSS for a service's process descendants.

    Includes the listener's pw-record and native TTS worker when active.
    Children may disappear during sampling, which is normal.
    """
    seen: set[int] = set()
    pending = [pid]
    ticks, rss = 0, 0
    while pending and len(seen) < 128:
        current = pending.pop()
        if current in seen or current <= 0:
            continue
        seen.add(current)
        try:
            t, r = process_stats(current, procroot)
            ticks += t
            rss += r
            children = (procroot / str(current) / 'task' / str(current) /
                        'children').read_text().split()
            pending.extend(int(child) for child in children if child.isdecimal())
        except (OSError, ValueError, IndexError):
            continue
    return ticks, rss, len(seen)


def measure(seconds=10, pid: int | None = None, clock=time.monotonic, pause=time.sleep):
    """Read-only sampling of the listener, its children and optional VR tab.

    Average % is normalized to ONE CPU core (100% means one busy core).
    Memory is total RSS of sampled processes, not unique-memory accounting.
    This does not measure GPU use, battery life, or impact on a game.
    """
    pid = pid or main_pid()
    if not pid:
        raise RuntimeError('Hey Frame service is not running. Use hey-frame start first.')
    seconds = max(3, min(int(seconds), 120))
    dashboard = main_pid('hey-frame-dashboard.service') if pid else None
    pids = [pid] + ([dashboard] if dashboard and dashboard != pid else [])
    clock_ticks = os.sysconf('SC_CLK_TCK')
    totals = {}
    total_cpu_seconds = 0.0
    peak_rss = 0
    peak_count = 0

    def snapshot() -> None:
        nonlocal peak_rss, peak_count, total_cpu_seconds
        current = {}
        size, count = 0, 0
        for service_pid in pids:
            ticks, rss, processes = process_tree_stats(service_pid)
            current[service_pid] = ticks
            size += rss
            count += processes
            if service_pid in totals:
                total_cpu_seconds += max(0, ticks - totals[service_pid]) / clock_ticks
        totals.update(current)
        peak_rss = max(peak_rss, size)
        peak_count = max(peak_count, count)

    t0 = clock()
    snapshot()
    while True:
        remain = seconds - (clock() - t0)
        if remain <= 0:
            break
        pause(min(1.0, remain))
        snapshot()
    elapsed = max(0.001, clock() - t0)
    return {
        'pid': pid, 'elapsed': round(elapsed, 1),
        'cpu_percent': round(total_cpu_seconds / elapsed * 100, 1),
        'rss_mib': round(peak_rss / 1024, 1),
        'processes': peak_count,
        'includes_dashboard': bool(dashboard),
    }


def describe(results) -> str:
    return (f"Listener PID {results['pid']} | sampled {results['elapsed']}s | "
            f"average CPU {results['cpu_percent']}% of one core | "
            f"peak total RSS {results['rss_mib']} MiB across "
            f"{results.get('processes', 1)} processes "
            f"({'including' if results.get('includes_dashboard') else 'excluding'} SteamVR tab). "
            'Includes sampled child processes, but not GPU, battery-life or game performance.')
