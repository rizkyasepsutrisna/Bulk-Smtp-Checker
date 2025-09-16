# Bulk SMTP Tester

A Python script for performing **bulk SMTP account testing** from a text file. The script tests connection on port **587 (STARTTLS)** and falls back to **465 (SSL)**. Results are saved to a CSV file and separated into two TXT files for successes and failures.

---

## Features

- Read SMTP list from a TXT file with the format:
  ```
  mail_host|mail_username|mail_password|mail_from_address
  ```
  The parser tolerates `|` characters inside the password by treating the last field as the `mail_from_address`.

- For each entry, the script will:
  1. Try `host:587` with STARTTLS → LOGIN → (if not dry-run) SEND
  2. If port 587 fails (except authentication error), try `host:465` with SSL
  3. Record results (host, username, used port, success/fail, error, raw line) to a CSV file

- Fixed subject/body inside the script (no CLI args for subject/body):
  - Subject: `SMTP TEST`
  - Body: `This is an automated SMTP test message.`

- Options / CLI flags:
  - `--dry-run` — perform login only; do not send the test email
  - `--parallel` — enable multi-threaded execution (uses `--workers`)
  - `--workers N` — number of worker threads (default: 8)
  - `--rate N` — global requests-per-second rate limit (0 = no limit)
  - `--to ADDRESS` — override default test recipient (default: `yourmail@mail.com`)
  - `--timeout` — connection timeout in seconds (default 12)
  - `--no-color` — disable colored console output
  - `--no-banner` — disable ASCII banner and small visual effects

- Live progress bar (requires `tqdm`), colored console output (requires `colorama`)

- Output files:
  - `smtp_results_YYYYmmdd_HHMMSS.csv` — detailed CSV results
  - `smtp_success_YYYYmmdd_HHMMSS.txt` — raw lines that succeeded
  - `smtp_fail_YYYYmmdd_HHMMSS.txt` — raw lines that failed

- End-of-run summary printed to console (counts of successes/failures and file names)

---

## Requirements

- Python 3.8+ (recommended)

Optional (for nicer UI):

```bash
pip install colorama tqdm
```

The script runs without these optional packages; it will simply skip colored output or progress bar if they are missing.

---

## Usage

Create a `smtp.txt` file with one SMTP entry per line. Example:

```
smtp.example.com|user@example.com|password123|user@example.com
```

Run the script:

### Sequential (default)

```bash
python3 bulk_smtp_test.py smtp.txt
```

### Dry-run (login only)

```bash
python3 bulk_smtp_test.py smtp.txt --dry-run
```

### Parallel with 16 workers

```bash
python3 bulk_smtp_test.py smtp.txt --parallel --workers 16
```

### With rate limit (max 5 requests/sec)

```bash
python3 bulk_smtp_test.py smtp.txt --parallel --workers 16 --rate 5
```

### Change test recipient

```bash
python3 bulk_smtp_test.py smtp.txt --to someone@example.com
```

---

## Output

After the run you will find:

- `smtp_results_YYYYmmdd_HHMMSS.csv` — a CSV containing: host, username, used_port, success, error, raw_line
- `smtp_success_YYYYmmdd_HHMMSS.txt` — raw input lines that succeeded
- `smtp_fail_YYYYmmdd_HHMMSS.txt` — raw input lines that failed

A short summary will be printed to the console showing total entries, success count, and fail count.

---

## Example

This repository should include the `bulk_smtp_test.py` script and a sample `smtp.txt` (or you can create your own). After running the script, check the generated CSV and TXT files for details.

---

## Disclaimer

This script is intended for testing SMTP servers you own or have explicit permission to test. Do **not** use it for spamming, account cracking, or other illegal activities. The author is not responsible for misuse.

---

## Donate

If you find this project useful, consider supporting it:

➡️ [Donate via Saweria](https://saweria.co/zainpewpewpew)

---

Feel free to edit this README to add screenshots, badges, or additional instructions for your GitHub repository.
