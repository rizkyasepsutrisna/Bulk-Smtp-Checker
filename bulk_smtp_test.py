#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bulk_smtp_test.py
Bulk SMTP tester (tries 587 -> 465) with live progress bar.

Features:
 - Read SMTP list from a TXT file (format: host|username|password|from)
 - Try port 587 (STARTTLS) first; if it fails, try 465 (SSL)
 - Fixed subject/body inside script (no CLI args for subject/body)
 - Supports dry-run (login only), parallel execution, rate limiting (requests/sec)
 - Live progress bar via tqdm (optional, auto-fallback if missing)
 - Colored output via colorama (optional)
 - Default recipient: yourmail@mail.com (override with --to)
 - Saves: CSV + success/fail TXT files + end-of-run summary
"""

import smtplib
import ssl
import sys
import csv
import socket
import argparse
import time
from email.message import EmailMessage
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import random

# Optional color support
try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
except Exception:
    class _C:
        def __getattr__(self, n): return ''
    Fore = Style = _C()

# Optional progress bar
try:
    from tqdm import tqdm
except Exception:
    tqdm = None

# ---------- Configuration ----------
DEFAULT_TIMEOUT = 12
DEFAULT_TO = "yourmail@mail.com"
FIXED_SUBJECT = "SMTP TEST"
FIXED_BODY = "This is an automated SMTP test message."
# ----------------------------------

ASCII_BANNER = r"""
   ____  _   _ _  _ _  _   _____  __  __ _____ _   _ 
  | __ )| | | | || | \| | |__  / |  \/  | ____| \ | |
  |  _ \| | | | || | .` |   / /  | |\/| |  _| |  \| |
  | |_) | |_| |__   _|\  |  / /_  | |  | | |___| |\  |
  |____/ \___/   |_| |_| \_| /____|_|  |_|_____|_| \_|
                                                    
  Bulk SMTP Tester - Try 587 (STARTTLS) then 465 (SSL)
"""

class RateLimiter:
    """Simple global rate limiter: max N operations per second."""
    def __init__(self, rate: float):
        self.rate = float(rate) if rate and rate > 0 else 0.0
        self.lock = Lock()
        self._next = 0.0
        self._interval = 1.0 / self.rate if self.rate > 0 else 0.0

    def acquire(self):
        if self.rate <= 0:
            return
        with self.lock:
            now = time.monotonic()
            if self._next <= now:
                self._next = now + self._interval
                return
            sleep_for = self._next - now
            self._next += self._interval
        time.sleep(sleep_for)

def parse_line(line: str) -> Optional[Tuple[str, str, str, str]]:
    """Parse tolerant to '|' in the password. Last column is mail_from."""
    if not line:
        return None
    s = line.strip()
    if not s or s.startswith('#'):
        return None
    parts = s.split('|')
    if len(parts) < 4:
        return None
    host = parts[0].strip()
    username = parts[1].strip()
    mail_from = parts[-1].strip()
    password = '|'.join(p.strip() for p in parts[2:-1])
    if not (host and username and mail_from):
        return None
    return host, username, password, mail_from

def build_message(mail_from: str, mail_to: str) -> EmailMessage:
    msg = EmailMessage()
    msg['Subject'] = FIXED_SUBJECT
    msg['From'] = mail_from
    msg['To'] = mail_to
    msg.set_content(FIXED_BODY)
    return msg

def try_send_starttls(host, username, password, mail_from, mail_to, timeout, msg: Optional[EmailMessage], dry_run: bool):
    with smtplib.SMTP(host=host, port=587, timeout=timeout) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(username, password)
        if not dry_run and msg is not None:
            smtp.send_message(msg)

def try_send_ssl(host, username, password, mail_from, mail_to, timeout, msg: Optional[EmailMessage], dry_run: bool):
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host=host, port=465, timeout=timeout, context=context) as smtp:
        smtp.login(username, password)
        if not dry_run and msg is not None:
            smtp.send_message(msg)

def test_smtp_entry(host: str, username: str, password: str, mail_from: str,
                    mail_to: str, timeout: int, dry_run: bool) -> Tuple[bool, Optional[int], str]:
    """Return (success, used_port_or_None, error_message)."""
    msg = None if dry_run else build_message(mail_from, mail_to)
    try:
        try:
            try_send_starttls(host, username, password, mail_from, mail_to, timeout, msg, dry_run)
            return True, 587, ''
        except smtplib.SMTPAuthenticationError as e:
            return False, 587, f'Authentication error: {e}'
        except (smtplib.SMTPException, socket.timeout, ConnectionRefusedError, OSError) as e:
            try:
                try_send_ssl(host, username, password, mail_from, mail_to, timeout, msg, dry_run)
                return True, 465, ''
            except smtplib.SMTPAuthenticationError as e2:
                return False, 465, f'Authentication error: {e2}'
            except Exception as e2:
                return False, None, f'Port 587 error: {e} | Port 465 error: {e2}'
    except Exception as e:
        return False, None, f'Unexpected error: {e}'

def process_line(idx: int, total: int, line: str, timeout: int,
                 dry_run: bool, no_color: bool,
                 mail_to: str, limiter: RateLimiter) -> Tuple[str, str, Optional[int], bool, str, str]:
    """Process one input line and return CSV row tuple."""
    parsed = parse_line(line)
    if not parsed:
        display = f"[{idx}/{total}] SKIP - bad format"
        print((Fore.YELLOW if not no_color else '') + display + (Style.RESET_ALL if not no_color else ''))
        return '', '', None, False, 'format_error', line

    host, username, password, mail_from = parsed
    display = f"[{idx}/{total}] {host} | {username} -> {mail_to}"

    limiter.acquire()

    ok, used_port, err = test_smtp_entry(
        host, username, password, mail_from,
        mail_to, timeout=timeout, dry_run=dry_run
    )

    if ok:
        msg = f"{display} => SUCCESS (port {used_port}{' / dry-run' if dry_run else ''})"
        print((Fore.GREEN if not no_color else '') + msg + (Style.RESET_ALL if not no_color else ''))
        return host, username, used_port, True, '', line
    else:
        err = err or 'Unknown error'
        msg = f"{display} => FAIL | {err}"
        print((Fore.RED if not no_color else '') + msg + (Style.RESET_ALL if not no_color else ''))
        return host, username, used_port, False, err, line

def read_lines(path: Path) -> List[str]:
    return [l for l in path.read_text(encoding='utf-8', errors='ignore').splitlines() if l.strip()]

def main():
    parser = argparse.ArgumentParser(description="Bulk SMTP tester (tries 587 -> 465).")
    parser.add_argument("file", nargs="?", help="Path to SMTP file (host|username|password|from)")
    parser.add_argument("--dry-run", action="store_true", help="Only login (do not send email).")
    parser.add_argument("--parallel", action="store_true", help="Enable parallel execution (threads).")
    parser.add_argument("--workers", type=int, default=8, help="Number of worker threads for parallel mode (default: 8).")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Connection timeout in seconds (default: {DEFAULT_TIMEOUT}).")
    parser.add_argument("--no-color", action="store_true", help="Disable colored console output.")
    parser.add_argument("--to", default=DEFAULT_TO, help=f"Recipient address for test email (default: {DEFAULT_TO}).")
    parser.add_argument("--rate", type=float, default=0.0, help="Global rate limit: requests per second (0 = no limit).")
    args = parser.parse_args()

    infile = args.file
    if not infile:
        try:
            infile = input("Enter path to SMTP file: ").strip()
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(1)

    p = Path(infile)
    if not p.exists():
        print((Fore.RED if not args.no_color else '') + f"File not found: {infile}" + (Style.RESET_ALL if not args.no_color else ''))
        sys.exit(1)

    lines = read_lines(p)
    if not lines:
        print((Fore.RED if not args.no_color else '') + "Input file is empty." + (Style.RESET_ALL if not args.no_color else ''))
        sys.exit(1)

    # Banner
    print(Fore.GREEN + Style.BRIGHT + ASCII_BANNER + Style.RESET_ALL)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = f"smtp_results_{ts}.csv"
    out_success = f"smtp_success_{ts}.txt"
    out_fail = f"smtp_fail_{ts}.txt"
    total = len(lines)
    limiter = RateLimiter(args.rate)

    print((Style.BRIGHT if not args.no_color else '') + f"Starting test: {total} entries -> recipient: {args.to}" + (Style.RESET_ALL if not args.no_color else ''))
    print(f"Subject: {FIXED_SUBJECT}")
    print(f"Results will be saved to: {out_csv}, {out_success}, {out_fail}\n")

    success_list, fail_list = [], []

    # Open CSV and process with LIVE progress bar
    with open(out_csv, 'w', newline='', encoding='utf-8') as csvf:
        writer = csv.writer(csvf)
        writer.writerow(['host', 'username', 'used_port', 'success', 'error', 'raw_line'])

        if tqdm:
            pbar = tqdm(total=total, desc="Processing", unit="acct")
        else:
            pbar = None

        if args.parallel:
            with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
                futures = {
                    ex.submit(process_line, idx, total, line, args.timeout,
                              args.dry_run, args.no_color,
                              args.to, limiter): (idx, line)
                    for idx, line in enumerate(lines, start=1)
                }
                for fut in as_completed(futures):
                    host, user, used_port, success, err, raw = fut.result()
                    writer.writerow([host, user, used_port or '', success, err, raw])
                    if success:
                        success_list.append(raw)
                    else:
                        fail_list.append(raw)
                    if pbar:
                        pbar.update(1)
        else:
            # Sequential processing with per-item live update
            for idx, line in enumerate(lines, start=1):
                host, user, used_port, success, err, raw = process_line(
                    idx, total, line, args.timeout, args.dry_run, args.no_color, args.to, limiter
                )
                writer.writerow([host, user, used_port or '', success, err, raw])
                if success:
                    success_list.append(raw)
                else:
                    fail_list.append(raw)
                if pbar:
                    pbar.update(1)

        if pbar:
            pbar.close()

    # Save success/fail lists
    Path(out_success).write_text("\n".join(success_list), encoding="utf-8")
    Path(out_fail).write_text("\n".join(fail_list), encoding="utf-8")

    # Summary
    print("\n" + (Style.BRIGHT if not args.no_color else '') + "Summary:" + (Style.RESET_ALL if not args.no_color else ''))
    print(f"  Total entries: {total}")
    print(Fore.GREEN + f"  Success: {len(success_list)} -> {out_success}" + Style.RESET_ALL)
    print(Fore.RED + f"  Fail:    {len(fail_list)} -> {out_fail}" + Style.RESET_ALL)
    print("\nDetailed CSV: " + out_csv)

if __name__ == '__main__':
    main()
