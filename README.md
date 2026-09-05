# XMU Rollcall Bot

[English](README-en.md) | **简体中文**

> 本项目 fork 自 [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot)。

厦门大学（Tronclass）自动签到程序，**仅供学习研究使用**

## 概览

- 实时监控签到状态
- 自动完成签到：
  - 数字签到：从 API 获取数字码
  - 雷达签到：使用两个位置点求解签到位置
- 支持等待指定数量的同学完成签到后再提交
- 支持多账号，并在 SQLite 中加密存储账号信息和会话
- 在日志文件中记录签到状态
- 更友好的交互界面

<details>
<summary>运行截图</summary>
<img src="screenshots/1.png" alt="screenshot_1" width="100%">
<br><br>
<img src="screenshots/2.png" alt="screenshot_2" width="100%">
</details>

> 基于 ![KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot) 的 3.4.1 版本。

## 安装

### Windows 单文件 EXE

发布的 EXE 文件名包含包版本号，例如 `xmu-rollcall-3.4.2.0a0.exe`。双击该文件 进入交互菜单，无需安装 Python。

### 全局安装 （从源码）

```bash
git clone --depth 1 -b main https://github.com/alkali210/XMU-Rollcall-Bot.git
cd XMU-Rollcall-Bot
pip install -e xmu-rollcall-cli
```

### 虚拟环境（使用 uv）

在 `xmu-rollcall-cli` 目录中执行：

```bash
uv sync
```

## 使用

不带参数运行 `xmu-rollcall` 即可进入交互菜单，按 `Ctrl-C` 退出。
原有带参数命令仍可直接使用：

```bash
xmu-rollcall         # 打开交互菜单
xmu-rollcall config  # 配置账号，支持多账号
xmu-rollcall switch  # 切换账号
xmu-rollcall start   # 启动监控
xmu-rollcall refresh # 刷新登录状态

uv run xmu-rollcall           # 使用 uv 打开交互菜单
uv run xmu-rollcall <command> # 使用 uv 执行子命令
```

`refresh` 会清除当前账号的已保存登录会话，下次启动监控时重新登录。监控界面显示当前时间、运行时长、查询次数及监控间隔，按 `Ctrl-C` 清屏并显示退出统计。

日志文件位于配置目录内的 `xmu_rollcall.log`。

> 目前无法处理二维码签到，检测到二维码签到时，监控程序将暂停 5 分钟，以防止短时间内重复请求。

## 配置

### 监控间隔

配置目录优先使用环境变量 `XMU_ROLLCALL_CONFIG_DIR`，否则使用 `~/.xmu_rollcall`；用户目录不可写时使用当前目录下的 `.xmu_rollcall`。

在配置菜单中按 `i` 设置监控间隔，对所有账号生效（默认：10 秒，支持正数秒值）。也可以直接编辑 `config.json`，下次启动监控时生效：

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

### 等待同学签到

在配置菜单中按 `s`，设置提交签到前等待的同学签到人数。

等待人数保存在 `config.json` 的 `accounts` 列表中，通过 `id` 对应 TUI 中的账号；正整数表示等待人数，`false` 表示不等待。TUI 修改与手动编辑使用同一份配置。请保留实际账号的 ID，账号增删仍通过 TUI 操作。

也支持按比例等待：在 TUI 的 `s` 菜单输入 `20%`，或在 JSON 中设置 `"wait_before_answer": "20%"`。支持大于 0%、不超过 100% 的百分比（可含小数）。分母为接口返回的学生名单总人数，目标人数向上取整。
