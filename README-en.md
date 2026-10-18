# XMU Rollcall Bot

**English** | [简体中文](README.md)

> This project is forked from [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot).

Automatic Check-In Program for XMU(Tronclass), **Intended for educational and research purposes only.**

## Overview

- Monitor rollcall status in real-time
- Perform rollcall automatically:
  - Number rollcall: get number code from API
    The timetable API is queried using the rollcall's UTC date, avoiding date mismatches before 08:00 Beijing time.
- Supports waiting until a certain number of classmates have checked in before submitting
- Supports multiple accounts, stores encrypted account informations and sessions in sqlite
- Record the rollcall status in a log file
- Interactive UI

Based on version 3.4.1 of [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot).

## Installation

### Pip

```bash
pip install "git+https://github.com/alkali210/XMU-Rollcall-Bot.git#subdirectory=xmu-rollcall-cli"
```

### Single-file executables

Download the matching `xmu-rollcall-<version>-<platform>-<arch>` from **Releases** (Windows files end in `.exe`). The six combinations are `windows-amd64`, `windows-arm64`, `linux-amd64`, `linux-arm64`, `macos-amd64`, and `macos-arm64`. No Python installation is needed. On Windows double-click the EXE or run it from PowerShell; on Linux/macOS, run `chmod +x <downloaded-file>` before launching it in a terminal. Linux compatibility depends on the target system's glibc version.

Nuitka builds and smoke-tests each target on its native GitHub Actions runner. Pushing a `v*` tag attaches all six binaries plus the Python distributions to the GitHub Release. Alternatively, run the `Build binaries with Nuitka` workflow manually to download the artifacts.

To build locally on the target OS/architecture, use Python 3.13 and a C compiler (Visual Studio 2022 C++ Build Tools on Windows, Xcode command-line tools on macOS, GCC and patchelf on Linux). From `xmu-rollcall-cli/`:

```bash
python -m pip install . "Nuitka>=2.7,<5" ordered-set zstandard
python -m nuitka --mode=onefile --assume-yes-for-downloads --jobs=4 --output-filename=xmu-rollcall-local --output-dir=dist --include-package=xmulogin --include-package-data=xmulogin packaging/entry.py
python packaging/smoke_exe.py dist/xmu-rollcall-local
```

On Windows, add `--windows-console-mode=force --msvc=latest` and use `--output-filename=xmu-rollcall-local.exe` and `dist/xmu-rollcall-local.exe` for the smoke check. The workflow sets platform-specific versioned output filenames. The first build needs internet access to download build helpers. Smoke tests use a temporary configuration directory and require no credentials or login.

### From source

```bash
git clone --depth 1 -b main https://github.com/alkali210/XMU-Rollcall-Bot.git
cd XMU-Rollcall-Bot/xmu-rollcall-cli
uv sync
```

## Usage

Run `xmu-rollcall` without arguments to open the Rich interactive menu. Enter `1`–`5` or `config` / `switch` / `start` / `refresh` / `check`, and press `Ctrl-C` to exit. Configuration, account switching, session refresh, and update checks return to the menu after completion. After selecting `start`, pressing `Ctrl-C` exits the application directly. Existing subcommands still work directly. Panels adapt to the terminal width.

```bash
xmu-rollcall         # open the interactive menu
xmu-rollcall config  # configure your account. support multiple accounts
xmu-rollcall switch  # switch between accounts
xmu-rollcall start   # start the monitor
xmu-rollcall refresh # refresh login status
xmu-rollcall check   # check for updates
xmu-rollcall radar [options] [coordinates] # submit a known radar location
```

Use `xmu-rollcall start --id 2` to switch to account ID `2` and start monitoring, just like selecting that account with `switch` and then running `start`. The selection is saved as the current account; omitting `--id` keeps using the current account.

### Submit Known Radar Coordinates
Usage:
```bash
xmu-rollcall radar --latitude <lat> --longitude <lon> [--account-id <id>] [--rollcall-id <id>]
```
- `--latitude` / `--longitude`: The parameter name can be omitted: simply type `xmu-rollcall radar 24 118`
- `--account-id`: Specifies an account; if omitted, the currently selected account is used
- `--rollcall-id`: If omitted, the data is submitted to the active radar check-in for the current account; if no match is found, an exception is thrown

`refresh` clears the current account's saved login session; the next monitoring run logs in again. The monitor shows the current time, uptime, query count, and polling interval. Pressing `Ctrl+C` clears the screen and displays exit statistics.

Logs are stored as `xmu_rollcall.log` in the configuration directory.

> Automatic QR code and radar rollcalls are not supported. When an unfinished rollcall of either type is detected, the monitor reports it as unsupported and pauses for 5 minutes to prevent repeated requests. Radar coordinate calculation has been removed; the monitor does not submit coordinates.

## Configuration

### Interval for monitoring

The configuration directory is selected from `XMU_ROLLCALL_CONFIG_DIR`, then `~/.xmu_rollcall`, falling back to `.xmu_rollcall` in the current directory when the home directory is not writable. On Windows the default is `%USERPROFILE%\.xmu_rollcall`. The packaged executables and Python installation use the same rules. This directory contains `config.json`, `secure_store.sqlite3`, `secret.key`, and logs; runtime data is not bundled into the executables.

Press `i` in the configuration menu to set the polling interval (positive seconds, default: 60s) for all accounts. You can also edit `config.json`; changes apply on the next monitoring run:

```jsonc
{
  "interval": 15,
  "current_account_id": 1,
  "accounts": [
    {"id": 1, "rollcall_settings": {"wait_before_answer": 5}},
    {"id": 2, "rollcall_settings": {"wait_before_answer": false}}
  ]
}
```

### Monitor error retries

Press `r` in configuration to toggle and save `disable_monitor_retry` for all accounts (default: `false`). With `true`, monitoring exits on errors without backoff retries; `false` keeps up to 10 network retries. You can also set this boolean at the top level of `config.json`; it takes effect on the next monitor start. Startup never uses backoff retries.

### Waiting for classmates

Press `s` (Edit rollcall settings) in configuration menu to set the number of classmates to wait for before submitting the rollcall.

These settings live in the `accounts` list in `config.json`, matched to the account IDs shown in the TUI. Use a positive integer to wait or `false` to disable waiting. Both editing methods use the same configuration. Keep the actual account IDs and use the TUI to add or delete accounts.

For percentage waiting, enter `20%` in the `s` menu or set `"wait_before_answer": "20%"` in JSON. Percentages must be greater than 0% and at most 100%; decimals are supported. The denominator is the number of students returned by the API, and the required count rounds up (20% of 6 requires 2). Only `rollcall_status == "on_call_fine"` counts as signed. Missing, empty, or malformed lists keep waiting. New accounts and missing settings default to `10%`; existing explicit settings are preserved.

Each wait round lasts up to five minutes, checking attendance every five seconds. Reaching the target triggers submission; a timeout skips submission and returns to monitoring to query the current rollcall status. If the rollcall is still active, the number code is fetched again and a new wait round starts.

Credentials and sessions remain in encrypted SQLite storage. Existing database settings migrate automatically on first run; JSON settings take precedence, and legacy database settings are cleared only after a successful JSON write. Exit the configuration menu before editing the file manually.
