# XMU Rollcall Bot

[English](README.md) | **简体中文**

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

基于 [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot) 的 3.4.1 版本。

## 安装

### 全局安装

```bash
pip install -e xmu-rollcall-cli
```

### 虚拟环境（使用 uv）

在 `xmu-rollcall-cli` 目录中执行：

```bash
uv sync
```

## 使用

```bash
xmurollcall-cli config  # 配置账号，支持多账号
xmurollcall-cli switch  # 切换账号
xmurollcall-cli start   # 启动监控
xmurollcall-cli refresh # 刷新登录状态

uv run xmurollcall-cli <command> # 如果使用 uv
```

日志文件位于 `XMU_ROLLCALL_CONFIG_DIR/xmu_rollcall.log`。

> 目前无法处理二维码签到，检测到二维码签到时，监控程序将暂停 5 分钟，以防止短时间内重复请求。

## 配置

### 监控间隔

默认配置文件路径优先级：`XMU_ROLLCALL_CONFIG_DIR/config.json` > `~/.xmu_rollcall/config.json` > `./xmu-rollcall-cli/config.json`

可以设置监控间隔，对所有账号生效（默认：10 秒）：

```jsonc
{
  "interval": 15
}
```

### 等待同学签到

在配置菜单中按 `s`（编辑签到设置），设置提交签到前等待的同学签到人数。

> 可以随时按 `Ctrl + C` 中止配置。
