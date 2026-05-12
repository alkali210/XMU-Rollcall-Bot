
# XMU Rollcall Bot

Automatic Check-In Program for XMU(Tronclass), **Intended for educational and research purposes only.**

## Features
- Monitor rollcall status in real-time
- Perform rollcall automatically:
  - Number rollcall: get number code from API
  - Radar rollcall: find the location using two points
- Supports waiting until a certain number of classmates have checked in before submitting
- Supports multiple accounts
- Using a log file to record the rollcall status

This project is based on version 3.4.1 of [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot), which has been archived.

## Installation

```bash
pip install -e xmu-rollcall-cli
```
> also see [XMU Rollcall Bot CLI 使用文档](https://krsmt.notion.site/cli-doc)

## Usage

```bash
xmurollcall-cli config  # configure your account. support multiple accounts.
xmurollcall-cli switch  # switch between accounts.
xmurollcall-cli start   # start the monitor.
```
> the previous alias `xmu` is no longer supported.

See log at `CONFIG_DIR/xmu_rollcall.log`

### Configuration

```bash
xmurollcall-cli config
```
to configure your account. You can add multiple accounts, and edit rollcall settings for each account.

Default configuration file path: `$env:XMU_ROLLCALL_CONFIG_DIR/config.json` > `~/.xmu_rollcall/config.json` > `./config.json`

You can set the interval for monitoring *(default: 10s)*:
```jsonc
{
  "interval": 8
}
```

> The configuration file stores credentials in plain text; do not post it anywhere.
