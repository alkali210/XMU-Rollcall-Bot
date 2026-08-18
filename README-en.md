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

Based on version 3.4.1 of [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot).

## Installation

### Virtual environment (using uv)

Run the following command from the `xmu-rollcall-cli` directory:

```bash
uv sync
```

### Global installation (from source)

```bash
git clone --depth 1 -b main https://github.com/alkali210/XMU-Rollcall-Bot.git
cd XMU-Rollcall-Bot
pip install -e xmu-rollcall-cli
```

### Global installation (from wheel)

```bash
pip install xmu_rollcall_cli-3.4.1.4-py3-none-any.whl # download from releases
```

## Usage

```bash
xmurollcall-cli config  # configure your account. support multiple accounts
xmurollcall-cli switch  # switch between accounts
xmurollcall-cli start   # start the monitor
xmurollcall-cli refresh # refresh login status

uv run xmurollcall-cli <command> # if using uv
```

See log at `XMU_ROLLCALL_CONFIG_DIR/xmu_rollcall.log`

> Currently unable to resolve the QR code rollcall, when a QR code rollcall is detected, the monitor will pause for 5 minutes to prevent repeated requests within a short period of time.

## Configuration

### Interval for monitoring

Default configuration file path: `XMU_ROLLCALL_CONFIG_DIR/config.json` > `~/.xmu_rollcall/config.json` > `./xmu-rollcall-cli/config.json`

You can set the interval for monitoring *(default: 10s)*, it will apply to all accounts:

```jsonc
{
  "interval": 15
}
```

### Waiting for classmates

Press `s` (Edit rollcall settings) in configuration menu to set the number of classmates to wait for before submitting the rollcall.

> You can press `Ctrl + C` to abort configuration at any time.
