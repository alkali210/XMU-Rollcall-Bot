# Tronclass 数字签到助手

`xmu-rollcall.user.js` 是一个运行在 `https://lnt.xmu.edu.cn/` 上的浏览器用户脚本，用于自动完成数字签到。

## 行为

脚本安装后会自动启动，每 10 秒请求一次待签到列表：

1. 获取 `/api/radar/rollcalls` 中的签到列表。
2. 筛选尚未签到的数字签到。
3. 请求对应的 `student_rollcalls` 接口获取 `number_code`。
4. 生成设备标识，并提交 `answer_number_rollcall`。
5. 在浏览器控制台和页面右下角显示发现课程、签到码、成功或失败状态。

脚本会记录当前会话中已经成功提交的签到，避免重复提交。雷达签到和二维码签到不会被自动提交。

## 用法

1. 安装 Tampermonkey、Violentmonkey 等用户脚本管理器。
2. 新建用户脚本，将 `xmu-rollcall.user.js` 的内容复制进去，或直接导入该文件。
3. 登录并打开 `https://lnt.xmu.edu.cn/`。
4. 脚本会在页面加载后自动开始运行。

签到接口依赖当前浏览器会话，因此使用前需要先在该站点完成登录。

## 控制台接口

脚本加载后，可以在浏览器控制台通过 `window.XMURollcallBot` 控制：

```js
// 查看运行状态
window.XMURollcallBot.status()

// 手动立即检查一次
window.XMURollcallBot.runOnce()

// 停止自动轮询
window.XMURollcallBot.stop()

// 重新启动自动轮询
window.XMURollcallBot.start()

// 使用自定义轮询间隔，单位为毫秒，最小为 1000
window.XMURollcallBot.start(5000)
```

仅在确认当前账号和签到状态后使用，签到码等敏感信息会显示在本地浏览器控制台和页面通知中。
