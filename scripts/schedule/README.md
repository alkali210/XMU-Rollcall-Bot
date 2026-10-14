# 按照课程表签到

本目录包含两个脚本，配合使用可以把厦门大学教务系统中的课程表转换为 ICS 文件，并在上课前后自动启动、停止签到程序：

解析 ICS 文件中的课程事件，在每个课程开始前 10 分钟执行：

```text
xmu-rollcall start
```

课程开始后 20 分钟，结束签到进程。

## 使用方法

安装依赖：

```bash
npm ci
```

运行：

```bash
node --experimental-strip-types schedule.ts <ics 文件> [--timezone 时区]
```

按下 `Ctrl+C` 停止，退出时也会清理签到进程。
