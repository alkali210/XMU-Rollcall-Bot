
# XMU Rollcall Bot

> This project is forked from [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot).

Automatic Check-In Program for XMU(Tronclass), **Intended for educational and research purposes only.**

## Overview
- Monitor rollcall status in real-time
- Perform rollcall automatically:
  - Number rollcall: get number code from API
  - Radar rollcall: solve the location using two points
- Supports waiting until a certain number of classmates have checked in before submitting
- Supports multiple accounts, stores encrypted account informations and sessions in sqlite
- Using a log file to record the rollcall status

Based on version 3.4.1 of [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot).

## Installation

```bash
git clone --depth 1 -b main https://github.com/alkali210/XMU-Rollcall-Bot.git
cd XMU-Rollcall-Bot
pip install -e xmu-rollcall-cli
```
> also see [XMU Rollcall Bot CLI 使用文档](https://krsmt.notion.site/cli-doc)

## Usage

```bash
xmurollcall-cli config  # configure your account. support multiple accounts.
xmurollcall-cli switch  # switch between accounts.
xmurollcall-cli start   # start the monitor.
xmurollcall-cli refresh # refresh login status。
```

See log at `CONFIG_DIR/xmu_rollcall.log`

### Configuration

Default configuration file path: `$env:XMU_ROLLCALL_CONFIG_DIR/config.json` > `~/.xmu_rollcall/config.json` > `./config.json`

You can set the interval for monitoring *(default: 10s)*:
```jsonc
{
  "interval": 8
}
```
