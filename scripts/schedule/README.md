# 课程表导出与按照课程表自动签到

本目录包含两个脚本，配合使用可以把厦门大学教务系统中的课程表转换为 ICS 文件，并在上课前后自动启动、停止签到程序：

## `jw-schedule-export.user.js`

浏览器用户脚本，运行在厦门大学教务系统的课表页面：

`https://jw.xmu.edu.cn/gsapp/sys/wdkbapp/*default/index.do*`

用脚本管理器（如 Tampermonkey）安装。

### 行为

在页面上添加 **导出 ICS** 按钮。点击后将当前课程表导出为标准 iCalendar `.ics` 文件。

## `schedule.ts`

解析 ICS 文件中的课程事件，在每个课程开始前 10 分钟执行：

```text
xmu-rollcall start
```

课程开始后 20 分钟，结束签到进程。

### 使用方法

```bash
node --experimental-strip-types schedule.ts <ics 文件> [--timezone 时区]
```
按下 `Ctrl+C` 停止，退出时也会清理签到进程。
