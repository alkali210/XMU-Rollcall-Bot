# XMU Rollcall Bot

> [!note]
> ## 2026-10-12 雷达签到失效
> 对于不在范围内的提交不会再返回距离了，当前依赖距离计算坐标的方法失效，暂时已在 `main` 分支上移除，与 QR 签到一样按不支持处理。
>
> 作为替代，如果已知经纬度（根据上课地点），可以尝试手动或者使用 Agent [提交已知雷达签到坐标](#提交已知雷达签到坐标)。
> 
> **TODO: 增加教学地点坐标列表（分校区），自动提交**

---

[English](README-en.md) | **简体中文**

> 本项目 fork 自 [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot)，并基于其 3.4.1 版本进行开发。

厦门大学（Tronclass）自动签到程序，**仅供学习研究使用**

## 概览

- 实时监控签到状态，支持设置监控间隔
- 自动完成签到：
  - 数字签到：从 API 获取数字码
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

不带参数运行 `xmu-rollcall`，或者双击 `exe` 即可进入交互菜单，按 `Ctrl+C` 退出。

命令行参数：

```bash
xmu-rollcall config  # 配置账号，支持多账号
xmu-rollcall switch  # 切换账号
xmu-rollcall start   # 启动监控
xmu-rollcall refresh # 刷新登录状态
xmu-rollcall check   # 检查更新
xmu-rollcall radar [options] [coordinates] # 提交已知雷达签到坐标
xmu-rollcall --help  # 查看帮助
```

指定账号启动可使用 `xmu-rollcall start --id 2`，等同于先运行 `switch` 选择 ID 为 `2` 的账号，再 `start`。

在交互界面中，可以随时按 `Ctrl+C` 退出或者回到主菜单。

日志文件位于配置目录内的 `xmu_rollcall.log`。

> 目前无法自动处理二维码和雷达签到，检测到未完成的此类签到时，监控程序将暂停 5 分钟，以防止短时间内重复请求。

### 提交已知雷达签到坐标

用法：

```bash
xmu-rollcall radar --latitude <lat> --longitude <lon> [--account-id <id>] [--rollcall-id <id>]
```

- `--latitude` / `--longitude`：可以省略参数名，写 `xmu-rollcall radar 24 118` 即可
- `--account-id`：指定账号，省略时使用当前选中的账号
- `--rollcall-id`：省略时向当前账号的活动雷达签到提交，查询不到时返回异常

## 配置

可以直接在 TUI 中配置，在初次使用时需要新建账号并输入学号密码登录。

配置目录优先使用环境变量 `XMU_ROLLCALL_CONFIG_DIR`，否则使用 `~/.xmu_rollcall`；用户目录不可写时使用当前目录下的 `.xmu_rollcall`。

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

> 如果直接编辑此文件，会在下次启动时生效。

### 监控间隔

在配置菜单中按 `i` 设置监控间隔，对所有账号生效（默认：60 秒，支持正数秒值）。

### 监控错误重试

监控阶段出现连接中断，连接/读取超时，响应传输中断，`HTTP 408/429/500/502/503/504`，`UNEXPECTED_SSL_EOF` 时，程序默认会按 5, 10, 20, 40, 60 秒退避重试，之后每 60 秒重试，最多 10 次，期间可按 `Ctrl+C` 退出。

`disable_monitor_retry` 设为 `true` 时，监控阶段出错直接报错退出，不进行重试。在配置菜单中按 `r` 可以切换此选项。

### 等待同学签到

在配置菜单中按 `s`，设置提交签到前的等待，正整数表示提交前等待的已签到人数，百分比表示提交前等待的人数比例，`false` 表示不等待，默认值为 `10%`。

每轮最多等待 5 分钟，每 5 秒查询一次已签到人数。超时返回监控重新查询签到状态。如果签到仍然活动，会重新获取数字码并开始下一轮等待。

等待期间可按 **Ctrl+P** 跳过等待，直接提交数字码。
