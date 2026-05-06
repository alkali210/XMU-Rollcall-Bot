

<div align="center">

  <img src="https://socialify.git.ci/KrsMt-0113/XMU-Rollcall-Bot/image?font=JetBrains+Mono&forks=1&language=1&name=1&owner=1&pattern=Plus&stargazers=1&theme=Light" />

</div>

## Install

```bash
pip install -e xmu-rollcall-cli
```

## Usage

```bash
xmu config  # configure your account. support multiple accounts.
xmu switch  # switch between accounts.
xmu start   # start the monitor.
```
See log at `CONFIG_DIR/xmu_rollcall.log`

### Configuration
Default configuration file path: `$env:XMU_ROLLCALL_CONFIG_DIR` > `~/.xmu_rollcall/config.json` > `./config.json`

You can set the interval and the wait time before attempting rollcall *(default: 10s)*:
```json
{
  "interval": 8,
  "delay": 12 // or false to disable the wait time
}
```

## Other

[XMU File Downloader](https://chromewebstore.google.com/detail/imannochailfofibofphcpmlddlbbhao?utm_source=item-share-cb)