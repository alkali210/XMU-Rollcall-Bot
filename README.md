# XMU Rollcall Bot

[English](README-en.md) | **简体中文**

> 本项目 fork 自 [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot)，并基于其 3.4.1 版本进行开发。

厦门大学（Tronclass）自动签到程序，**仅供学习研究使用**

## 概览

- 实时监控签到状态，支持设置监控间隔
- 自动完成签到：
  - 数字签到：从 API 获取数字码
  - 雷达签到：使用两个位置点求解签到位置
- 支持提交签到前按比例或人数等待
- 支持多账号，并在 SQLite 中加密存储账号信息和会话
- 在日志文件中记录签到状态
- 更友好的交互界面

<details>
<summary>运行截图</summary>
<img src="screenshots/1.png" alt="screenshot_1" width="100%">
<br><br>
<img src="screenshots/2.png" alt="screenshot_2" width="100%">
</details>

## 安装

### Windows EXE

从 [Releases](https://github.com/alkali210/XMU-Rollcall-Bot/releases) `xmu-rollcall-<version>.exe`。双击进入交互菜单，无需安装 Python。

### 从源码安装

clone 本仓库并进入 `xmu-rollcall-cli/`：

```bash
git clone --depth 1 https://github.com/alkali210/XMU-Rollcall-Bot.git
cd XMU-Rollcall-Bot/xmu-rollcall-cli
```

#### 虚拟环境

```bash
uv sync
```

#### 全局安装

```bash
pip install -e .
```

## 使用

不带参数运行 `xmu-rollcall`，或者双击 `exe` 即可进入交互菜单，按 `Ctrl+C` 退出。

命令行参数：

```bash
xmu-rollcall config  # 配置账号，支持多账号
xmu-rollcall switch  # 切换账号
xmu-rollcall start   # 启动监控
xmu-rollcall refresh # 刷新登录状态
xmu-rollcall --help  # 查看帮助

uv run xmu-rollcall [option] # 如果使用 uv
```

在交互界面中，可以随时按 `Ctrl+C` 退出或者回到主菜单。

日志文件位于配置目录内的 `xmu_rollcall.log`。

### 断线恢复

监控内建网络重试，无需额外守护脚本。连接中断、连接/读取超时、响应传输中断，以及 HTTP 408、429、500、502、503、504 会按 5、10、20、40、60 秒退避重试，之后每 60 秒重试。首次请求之外最多重试 10 次，仍失败则提示并退出；期间可按 `Ctrl+C` 退出。成功完成一轮后重置等待时间和重试计数，断线及恢复会显示提示并写入日志。SSL 意外 EOF（`UNEXPECTED_EOF_WHILE_READING`）也会触发上述退避重试。

签到处理中断后会重新查询服务器状态，再决定是否提交，避免直接重放结果未知的提交请求。监控、数字签到和雷达签到请求设置了 10 秒连接超时、30 秒读取超时；等待同学签到的查询保留 10 秒超时。启动时验证缓存会话、调用登录库抛出的异常直接报错退出，不进行退避重试，也不会把验证时的断线误判为会话过期。登录库内部的超时和错误返回行为仍由该库控制。

认证失败、证书错误、无效响应和程序错误不作为暂时性网络故障无限重试。长时间断线期间可能错过已结束的签到；网络恢复不会补签过期任务。

方案选择：内建重试能保留会话并根据签到状态恢复，适用于命令行和 Windows EXE。额外守护进程可用于无人值守部署时兜底进程崩溃，但会增加部署与退出管理成本，且无法区分网络故障与配置错误，因此本次采用内建重试。

> 目前无法处理二维码签到，检测到二维码签到时，监控程序将暂停 5 分钟，以防止短时间内重复请求。

## 配置

可以直接在 TUI 中配置，在初次使用时需要新建账号并输入学号密码登录。

配置目录优先使用环境变量 `XMU_ROLLCALL_CONFIG_DIR`，否则使用 `~/.xmu_rollcall`；用户目录不可写时使用当前目录下的 `.xmu_rollcall`。

配置文件示例：

```jsonc
{
  "interval": 15,
  "current_account_id": 1,
  "accounts": [
    {
      "id": 1,
      "rollcall_settings": {
        "wait_before_answer": 5
      }
    },
    {
      "id": 2,
      "rollcall_settings": {
        "wait_before_answer": false
      }
    }
  ]
}
```

### 监控间隔

在配置菜单中按 `i` 设置监控间隔，对所有账号生效（默认：10 秒，支持正数秒值）。也可以直接编辑 `config.json`，下次启动监控时生效。

### 等待同学签到

在配置菜单中按 `s`，设置提交签到前的等待，正整数表示提交前等待的已签到人数，百分比表示提交前等待的人数比例，`false` 表示不等待，默认值为 `10%`。
