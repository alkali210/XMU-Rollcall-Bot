# XMU Rollcall Bot

[English](README-en.md) | **简体中文**

> 本项目 fork 自 [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot)

厦门大学（Tronclass）自动签到程序，**仅供学习研究使用**

## 概览

- 实时监控签到状态，支持设置监控间隔
- 自动完成签到：
  - 数字签到：从 API 获取数字码
  - 雷达签到：依次尝试保存的经纬度或者手动输入
- 支持提交签到前按比例或人数等待
- 支持多账号，并在 SQLite 中加密存储账号信息和会话
- 在日志文件中记录签到状态
- 更友好的交互界面
- 监控过程中断线自动重试恢复

## 安装

### Pip

```bash
pip install "git+https://github.com/alkali210/XMU-Rollcall-Bot.git#subdirectory=xmu-rollcall-cli"
```

### 单文件可执行程序

从 [Releases](https://github.com/alkali210/XMU-Rollcall-Bot/releases) 下载适合操作系统和 CPU 架构的文件：

| 系统 | amd64 | arm64 |
| --- | --- | --- |
| Windows | `windows-amd64.exe` | `windows-arm64.exe` |
| Linux | `linux-amd64` | `linux-arm64` |
| macOS | `macos-amd64` | `macos-arm64` |

无需安装 Python；Windows 可双击运行，Linux/macOS 下载后先执行 `chmod +x <filename>`，再运行。

### 从源码安装

```bash
git clone --depth 1 https://github.com/alkali210/XMU-Rollcall-Bot.git
cd XMU-Rollcall-Bot/xmu-rollcall-cli
uv sync
```

## 使用

不带参数运行 `xmu-rollcall`，或者双击 `exe` 即可进入交互菜单，按 `Ctrl+C` 退出。在初次使用时需要新建账号并输入学号密码登录，自动提交雷达签到需要先设置[雷达位置列表](#雷达位置列表)。

### 命令行参数

```bash
xmu-rollcall config  # 配置
xmu-rollcall switch  # 切换账号
xmu-rollcall start [--id <id>]  # 启动监控
xmu-rollcall refresh # 刷新登录状态
xmu-rollcall check   # 检查更新
xmu-rollcall radar [options] [coordinates] # 提交已知雷达签到坐标
xmu-rollcall --help  # 查看帮助
```

指定账号启动可使用 `xmu-rollcall start --id 2`，等同于先运行 `switch` 选择 ID 为 `2` 的账号，再 `start`。

在交互界面中，可以随时按 `Ctrl+C` 退出或者回到主菜单。

日志文件位于配置目录内的 `xmu_rollcall.log`。

二维码签到不支持自动处理，检测到未完成的二维码签到时暂停 5 分钟。

#### 提交已知雷达签到坐标

用法：

```bash
xmu-rollcall radar --latitude <lat> --longitude <lon> [--account-id <id>] [--rollcall-id <id>]
```

- `--latitude` / `--longitude`：可以省略参数名，写 `xmu-rollcall radar 24 118` 即可
- `--account-id`：指定账号，省略时使用当前选中的账号
- `--rollcall-id`：省略时向当前账号的活动雷达签到提交，查询不到时返回异常

## 配置

配置文件示例：

```jsonc
{
  "current_account_id": 1,
  "interval": 30.0, // 监控间隔
  "disable_monitor_retry": true, // 监控错误重试
  "accounts": [
    {
      "id": 1,
      "rollcall_settings": {
        "wait_before_answer": "30.0%" // 等待同学签到
      }
    },
    {
      "id": 2,
      "rollcall_settings": {
        "wait_before_answer": 10
      }
    }
  ]
}
```

如果直接编辑此文件，会在下次启动时生效。

### 监控间隔

在配置菜单中按 `i` 设置监控间隔，对所有账号生效（默认：60 秒，支持正数秒值）。

### 监控错误重试

监控阶段出现连接中断，连接/读取超时，响应传输中断，`HTTP 408/429/500/502/503/504`，`UNEXPECTED_SSL_EOF` 时，程序默认会按 5, 10, 20, 40, 60 秒退避重试，之后每 60 秒重试，最多 10 次，期间可按 `Ctrl+C` 退出。

`disable_monitor_retry` 设为 `true` 时，监控阶段出错直接报错退出，不进行重试。在配置菜单中按 `r` 可以切换此选项。

### 等待同学签到

在配置菜单中按 `s`，设置提交签到前的等待，正整数表示提交前等待的已签到人数，百分比表示提交前等待的人数比例，`false` 表示不等待，默认值为 `10%`。

每轮最多等待 5 分钟，每 5 秒查询一次已签到人数。超时返回监控重新查询签到状态。如果签到仍然活动再开始下一轮等待。

等待期间可按 **Ctrl+P** 跳过等待，直接尝试提交。

### 雷达位置列表

运行 `xmu-rollcall config`，按 `l` 进入位置设置，可以添加经纬度和备注。

位置保存于配置目录的 `radar_locations.jsonl`:

```json
{"latitude":24.1234,"longitude":118.1234,"remark":"教学楼 A"}
{"latitude":24.5678,"longitude":118.5678,"remark":"教学楼 B"}
```

每次处理雷达签到会重新读取列表依次尝试，全部失败再提示手动处理。雷达签到和数字签到共用等待设置。
