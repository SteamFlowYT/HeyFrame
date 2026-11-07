"""Read-only system queries and explicitly bounded local timer commands.

No evdev, no uinput, no keys, no volume changes, no arbitrary shell execution.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import time

@dataclass(frozen=True)
class Battery:
    percentage: int
    charging: bool
    minutes: int | None = None

@dataclass(frozen=True)
class Reply:
    text: str
    action: str = "none"
    seconds: int = 0


def read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except (OSError, UnicodeError):
        return ""


def read_int(path: Path) -> int | None:
    try:
        return int(read_text(path))
    except ValueError:
        return None


def read_battery(root: Path = Path('/sys/class/power_supply')) -> Battery | None:
    # Ignore controller/device batteries, matching the FrameYap design.
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return None
    for path in entries:
        if read_text(path / 'type').lower() != 'battery':
            continue
        if read_text(path / 'scope').lower() == 'device':
            continue
        percentage = read_int(path / 'capacity')
        if percentage is None or not 0 <= percentage <= 100:
            continue
        status = read_text(path / 'status').lower()
        charging = status in ('charging', 'full')
        minutes = None
        if status == 'discharging':
            for remaining, rate in [('energy_now','power_now'),('charge_now','current_now')]:
                value = read_int(path / remaining)
                power = read_int(path / rate)
                if value is not None and power is not None and value >= 0 and power > 0:
                    estimate = round(60 * value / power)
                    if 1 <= estimate <= 1440:
                        minutes = estimate
                    break
        return Battery(percentage, charging, minutes)
    return None


def battery_reply(b: Battery | None) -> str:
    if b is None:
        return 'Headset battery data is unavailable.'
    if b.charging:
        return f'Headset battery, {b.percentage} percent. Charging.'
    result = f'Headset battery, {b.percentage} percent.'
    if b.minutes is not None:
        h, m = divmod(b.minutes, 60)
        result += f' Approximate time remaining, {h} hours and {m} minutes.' if h else f' Approximate time remaining, {m} minutes.'
    else:
        result += ' Remaining time estimate unavailable.'
    return result


def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub('[^a-z0-9 ]', ' ', text.lower())).strip()


def has(t: str, *phrases: str) -> bool:
    return any(re.search(r'\b' + re.escape(s) + r'\b', t) for s in phrases)


NUMBERS = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,
           "nine":9,"ten":10,"eleven":11,"twelve":12,"fifteen":15,"twenty":20,"thirty":30,
           "forty":40,"forty five":45,"fifty":50,"sixty":60,"ninety":90,"a":1,"an":1}


def parse_timer(t: str) -> int | None:
    # Conservative: one unit, <= two hours; fails closed on unsupported phrases.
    m = re.search(r'\b(?:timer(?: for)?|remind me in|countdown for|set (?:a )?timer(?: for)?)\s+(\d{1,3}|[a-z ]+?)\s+(seconds?|minutes?|hours?)\b',t)
    if not m:
        return None
    amount = m.group(1).strip()
    n = int(amount) if amount.isdigit() else NUMBERS.get(amount)
    if n is None and ' ' in amount:
        parts = amount.split()
        if len(parts) == 2 and parts[0] in ('twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety') and parts[1] in NUMBERS and 1 <= NUMBERS[parts[1]] <= 9:
            n = {'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}[parts[0]] + NUMBERS[parts[1]]
    if n is None or n <= 0:
        return None
    scale = {'second':1,'minute':60,'hour':3600}[m.group(2).rstrip('s')]
    seconds = n * scale
    return seconds if 1 <= seconds <= 7200 else None


def format_duration(seconds: int) -> str:
    seconds = max(0,int(seconds))
    if seconds >= 3600:
        h, rem = divmod(seconds,3600)
        m = rem // 60
        return f'{h} hours' + (f' and {m} minutes' if m else '')
    if seconds >= 60:
        m, sec = divmod(seconds,60)
        return f'{m} minutes' + (f' and {sec} seconds' if sec else '')
    return f'{seconds} seconds'


def wifi_reply() -> str:
    if not shutil.which('nmcli'):
        return 'Wi-Fi details are unavailable on this SteamOS installation.'
    try:
        result = subprocess.run(['nmcli','-t','-f','IN-USE,SSID,SIGNAL','dev','wifi','list'],
                                capture_output=True,text=True,timeout=3,check=True)
        for line in result.stdout.splitlines():
            if line.startswith('*:'):
                # Ignore colon-escaping; only report signal, not private SSIDs aloud.
                percent = line.rsplit(':',1)[-1].strip()
                if percent.isdigit() and 0 <= int(percent) <= 100:
                    return f'Connected Wi-Fi signal, {percent} percent.'
        return 'Wi-Fi signal information is unavailable.'
    except (OSError,subprocess.SubprocessError):
        return 'Wi-Fi information is unavailable right now.'


def volume_reply() -> str:
    # READ ONLY. Do not modify sink state.
    if not shutil.which('wpctl'):
        return 'Headset volume data is unavailable.'
    try:
        p = subprocess.run(['wpctl','get-volume','@DEFAULT_AUDIO_SINK@'],
                           capture_output=True,text=True,check=True,timeout=3)
        m = re.search(r'Volume:\s*([0-9.]+)',p.stdout)
        if m:
            percent = min(150,max(0,round(float(m.group(1))*100)))
            return f'Current volume, {percent} percent.' + (' Muted.' if '[MUTED]' in p.stdout else '')
    except (OSError,ValueError,subprocess.SubprocessError):
        pass
    return 'Headset volume data is unavailable.'


def memory_reply(path: Path = Path('/proc/meminfo')) -> str:
    lines = read_text(path)
    stats = dict((m.group(1),int(m.group(2))) for m in re.finditer(r'^(MemTotal|MemAvailable):\s+(\d+) kB$',lines,re.M))
    if 'MemTotal' not in stats or 'MemAvailable' not in stats:
        return 'Memory status unavailable.'
    return f'Available memory, {stats["MemAvailable"] / (1024*1024):.1f} gigabytes out of {stats["MemTotal"] / (1024*1024):.1f}.'


def uptime_reply(path: Path = Path('/proc/uptime')) -> str:
    try:
        seconds = int(float(read_text(path).split()[0]))
        days, hours = divmod(seconds // 3600, 24)
        return f'Headset uptime, {days} days and {hours} hours.' if days else f'Headset uptime, {hours} hour' + ('s' if hours != 1 else '') + f' and {(seconds//60)%60} minutes.'
    except (IndexError,ValueError):
        return 'Headset uptime data unavailable.'


def storage_reply(home: Path | None = None) -> str:
    try:
        usage = shutil.disk_usage(home or Path.home())
        return f'Available storage, {usage.free / (1024**3):.1f} gigabytes.'
    except OSError:
        return 'Storage data unavailable.'


def steamvr_reply() -> str:
    """Query user-service status only; never start or stop SteamVR."""
    systemctl = shutil.which('systemctl')
    if not systemctl:
        return 'SteamVR service status is unavailable.'
    try:
        p = subprocess.run([systemctl, '--user', 'is-active', 'steamvr.service'],
                           capture_output=True, text=True, timeout=3, check=False)
        status = p.stdout.strip()
        if status == 'active':
            return 'SteamVR service is running.'
        if status in ('inactive', 'failed'):
            return 'SteamVR service is not currently running.'
    except (OSError, subprocess.SubprocessError):
        pass
    return 'SteamVR service status is unavailable.'


def answer(text: str, timer_seconds_left: int | None = None,
           battery_root: Path = Path('/sys/class/power_supply'), now: datetime | None = None) -> Reply:
    t = normalize(text)
    t = re.sub(r'^(?:hey frame|hay frame)\b[ ,]*','',t).strip()
    if not t:
        return Reply('Listening. Please say a command.')
    # Creator and gameplay actions go before generic words such as time/status.
    if has(t, 'highlight marker', 'mark the moment', 'mark this moment',
           'mark that moment', 'mark highlight', 'bookmark this moment', 'bookmark that'):
        return Reply('Marking the recording.', 'mark_moment')
    if has(t, 'take a screenshot', 'take screenshot', 'capture screenshot',
           'screenshot please', 'grab a screenshot'):
        return Reply('Taking screenshot.', 'screenshot')
    if has(t, 'open dashboard', 'show dashboard', 'open steamvr dashboard',
           'show steam dashboard', 'show steamvr dashboard'):
        return Reply('Opening SteamVR dashboard.', 'open_dashboard')
    if has(t, 'pause game', 'pause the game', 'pause my game'):
        return Reply('Opening the SteamVR dashboard. Games may continue running behind it.', 'pause_game')
    if has(t, 'resume game', 'resume the game', 'unpause game', 'unpause the game'):
        return Reply('Close the SteamVR dashboard with the Steam button. In-game pause requires a game-specific binding.', 'resume_game')
    if has(t, 'personal quote', 'my portal quote', 'read my quotes', 'my glados quote'):
        return Reply('Selecting your personal quote.', 'personal_quote')
    if has(t, 'read my last note', 'last note', 'what did i note', 'read last note'):
        return Reply('Reading last note.', 'last_note')
    # Notes are opt-in, brief and saved only on-device; no arbitrary dictation loop.
    note = re.search(r'^(?:take a note|make a note|note to self|remember this)\s+(.+)$', t)
    if note:
        return Reply(note.group(1)[:160], 'save_note')
    if has(t, 'battery warning on', 'low battery warning on'):
        return Reply('Low battery alerts enabled.', 'alerts_on')
    if has(t, 'battery warning off', 'low battery warning off'):
        return Reply('Low battery alerts disabled.', 'alerts_off')
    # Recorder actions are explicit and locally scoped; never interpret ambiguous
    # background audio as permission to record or terminate other processes.
    if has(t, 'start recording', 'begin recording', 'record video', 'record gameplay', 'start the recorder'):
        return Reply('Starting recording.', 'record_start')
    if has(t, 'stop recording', 'finish recording', 'end recording', 'stop the recorder'):
        return Reply('Stopping recording.', 'record_stop')
    if has(t, 'recording status', 'am i recording', 'are we recording', 'check recording', 'is it recording'):
        return Reply('Checking recording.', 'record_status')
    if has(t, 'tell me a joke', 'tell a joke', 'tell me a glados joke', 'tell a glados joke', 'make me laugh', 'say a joke', 'something funny'):
        return Reply('Generating joke.', 'joke')
    if has(t, 'glados quote', 'portal quote', 'portal two quote', 'portal 2 quote', 'tell me a quote', 'give me a quote', 'say a quote', 'quote from portal', 'line from portal', 'something glados would say', 'say something sarcastic'):
        return Reply('Generating quote.', 'quote')
    if has(t,'battery alerts on','turn on battery warnings','enable battery warnings'):
        return Reply('Low battery alerts enabled.', 'alerts_on')
    if has(t,'battery alerts off','turn off battery warnings','disable battery warnings'):
        return Reply('Low battery alerts disabled.', 'alerts_off')
    if has(t,'stop listening','go offline','shut down assistant','disable assistant'):
        return Reply('Voice assistant offline.', 'shutdown')
    if has(t,'cancel timer','stop timer','clear timer'):
        return Reply('Timer cancelled.' if timer_seconds_left is not None else 'No timer is active.', 'cancel_timer')
    if has(t,'how long on the timer','time left on timer','timer remaining','check timer','timer status'):
        return Reply('No timer is active.' if timer_seconds_left is None else
                     f'Timer remaining, {format_duration(timer_seconds_left)}.')
    if has(t,'timer','countdown','remind me in'):
        seconds = parse_timer(t)
        if seconds is None:
            return Reply('Try: set a timer for five minutes. Maximum two hours.')
        return Reply(f'Timer set for {format_duration(seconds)}.', 'set_timer', seconds)
    if has(t,'battery','charge','remaining power','power level'):
        return Reply(battery_reply(read_battery(battery_root)))
    if has(t,'time','clock'):
        current = now or datetime.now().astimezone()
        return Reply(f'Current time, {current.strftime("%I:%M %p").lstrip("0")}')
    if has(t,'date','day is it','today'):
        current = now or datetime.now().astimezone()
        return Reply(f'Today is {current.strftime("%A %B %d")}.')
    if has(t,'storage','disk space','free space'):
        return Reply(storage_reply())
    if has(t,'memory','ram'):
        return Reply(memory_reply())
    if has(t,'wi fi','wifi','wireless','signal strength','internet connection'):
        return Reply(wifi_reply())
    if has(t,'volume','sound level'):
        return Reply(volume_reply())
    if has(t,'uptime','how long have you been on'):
        return Reply(uptime_reply())
    if has(t,'help','what can you do','available commands'):
        return Reply('Try recording, mark this moment, screenshot, battery, timer, a joke, Portal quote, note to self, or open dashboard.')
    if has(t,'steamvr','steam vr','virtual reality running','vr running'):
        return Reply(steamvr_reply())
    if has(t,'hello','are you there','status report','system status','report'):
        return Reply('Frame voice system online. ' + battery_reply(read_battery(battery_root)))
    # No generative answer and no shell execution. Never pretend to understand.
    return Reply('Command not recognized. Say Hey Frame, then help.')
