# XMU Rollcall Bot

**English** | [简体中文](README.md)

> This project is forked from [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot).

Automatic Check-In Program for XMU(Tronclass), **Intended for educational and research purposes only.**

## Overview

- Monitor rollcall status in real-time
- Perform rollcall automatically:
  - Number rollcall: get number code from API
  - Radar rollcall: solve the location using two points
- Supports waiting until a certain number of classmates have checked in before submitting
- Supports multiple accounts, stores encrypted account informations and sessions in sqlite
- Record the rollcall status in a log file
- Interactive UI

Based on version 3.4.1 of [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot).

## Installation

### Windows single-file EXE

Download the versioned EXE (for example, `xmu-rollcall-3.4.2.0a0.exe`) from **Releases**, alongside the Python wheel and source distribution, and double-click it to open the menu. Python is not required.
Subcommands also work from PowerShell:

```powershell
.\xmu-rollcall-3.4.2.0a0.exe
.\xmu-rollcall-3.4.2.0a0.exe config
.\xmu-rollcall-3.4.2.0a0.exe start
```

### Global installation (from source)

```bash
git clone --depth 1 -b main https://github.com/alkali210/XMU-Rollcall-Bot.git
cd XMU-Rollcall-Bot
pip install -e xmu-rollcall-cli
```

### Virtual environment (using uv)

Run the following command from the `xmu-rollcall-cli` directory:

```bash
uv sync
```

## Usage

Run `xmu-rollcall` without arguments to open the Rich interactive menu. Enter `1`–`4` or `config` / `switch` / `start` / `refresh`, and press `Ctrl-C` to exit. Configuration, account switching, and session refresh return to the menu after completion. After selecting `start`, pressing `Ctrl-C` exits the application directly. Existing subcommands still work directly. Panels adapt to the terminal width.

```bash
xmu-rollcall         # open the interactive menu
xmu-rollcall config  # configure your account. support multiple accounts
xmu-rollcall switch  # switch between accounts
xmu-rollcall start   # start the monitor
xmu-rollcall refresh # refresh login status

uv run xmu-rollcall           # open the interactive menu with uv
uv run xmu-rollcall <command> # run a subcommand with uv
```

`refresh` clears the current account's saved login session; the next monitoring run logs in again. The monitor shows the current time, uptime, query count, and polling interval. Pressing `Ctrl+C` clears the screen and displays exit statistics.

Logs are stored as `xmu_rollcall.log` in the configuration directory.

> Currently unable to resolve the QR code rollcall, when a QR code rollcall is detected, the monitor will pause for 5 minutes to prevent repeated requests within a short period of time.

## Configuration

### Interval for monitoring

The configuration directory is selected from `XMU_ROLLCALL_CONFIG_DIR`, then `~/.xmu_rollcall`, falling back to `.xmu_rollcall` in the current directory when the home directory is not writable. On Windows the default is `%USERPROFILE%\.xmu_rollcall`. The EXE and Python versions use the same rules. This directory contains `config.json`, `secure_store.sqlite3`, `secret.key`, and logs; runtime data is not bundled into the EXE.

Press `i` in the configuration menu to set the polling interval (positive seconds, default: 10s) for all accounts. You can also edit `config.json`; changes apply on the next monitoring run:

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

### Waiting for classmates

Press `s` (Edit rollcall settings) in configuration menu to set the number of classmates to wait for before submitting the rollcall.

These settings live in the `accounts` list in `config.json`, matched to the account IDs shown in the TUI. Use a positive integer to wait or `false` to disable waiting. Both editing methods use the same configuration. Keep the actual account IDs and use the TUI to add or delete accounts.

For percentage waiting, enter `20%` in the `s` menu or set `"wait_before_answer": "20%"` in JSON. Percentages must be greater than 0% and at most 100%; decimals are supported. The denominator is the number of students returned by the API, and the required count rounds up (20% of 6 requires 2). Only `rollcall_status == "on_call_fine"` counts as signed. Missing, empty, or malformed lists keep waiting. New accounts and missing settings default to `10%`; existing explicit settings are preserved.

Credentials and sessions remain in encrypted SQLite storage. Existing database settings migrate automatically on first run; JSON settings take precedence, and legacy database settings are cleared only after a successful JSON write. Exit the configuration menu before editing the file manually.
