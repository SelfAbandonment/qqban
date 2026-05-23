# 更新日志

本文档记录 QQVerify 插件的重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循插件自身发布节奏。

## [未发布]

### 初始功能

- 新增验证状态隔离：待验证状态按“群号 + QQ号”保存，避免同一用户在多个群验证时互相覆盖。
- 新增最大答错次数配置 `max_wrong_attempts`，达到上限后自动进入踢出流程。
- 新增验证难度配置 `verification_difficulty`，支持 `easy`、`normal`、`hard`。
- 新增验证消息发送模式 `verification_message_mode`，支持 `group`、`private`、`hybrid`。
- 新增私聊验证支持，用户可以在私聊中直接回复答案完成验证。
- 新增私聊发送失败回退提示 `private_message_failed_prompt`。
- 新增私聊验证群内提示 `private_verification_notice_prompt`。
- 新增答错次数过多提示 `wrong_answer_limit_prompt`。
- 新增插件卸载清理逻辑，卸载时会取消所有待验证倒计时任务。
- 新增可选 Minecraft RCON 扩展模块，提供 `/tomc`、`/mcrestart`、`/myid` 命令。
- 新增 MC RCON 扩展开关 `mc_rcon_enabled`，默认关闭，避免入群验证场景误触发 RCON 连接。

### 优化

- 优化验证题生成逻辑，默认难度不再出现过难乘法题。
- 优化群聊验证触发逻辑，仍要求用户在群内 `@Bot` 后作答，减少普通聊天误触发。
- 优化私聊模式体验：答错后重新出题只私聊用户，避免反复刷群提示。
- 优化事件 raw 数据和 Bot 实例访问方式，提高适配器兼容性和静态诊断质量。
- 完善 [README.md](README.md)，补充安装、配置、验证流程、消息模板变量和注意事项。

### 变更

- 主插件入口现在同时监听群消息和私聊消息，以支持私聊验证作答。
- RCON 密码改为通过配置项 `rcon_password` 提供，不再建议硬编码到源码中。
- MC RCON 发送失败时会返回具体原因，例如未启用、未配置密码、认证失败或连接异常。
- MC RCON 命令不再被启用开关拦截；调用 `/tomc` 或 `/mcrestart` 时会直接根据 RCON 配置尝试连接，未填写密码时提示 `RCON 密码未配置`。

### 验证

- 已通过 `python -m compileall main.py core` 编译检查。
- 已通过编辑器诊断检查。
- 已通过 `git diff --check` 空白格式检查。

## [0.1.0] - 初始版本

### 新增

- 新成员入群后自动发送数学验证题。
- 支持验证超时警告、超时失败提示和自动踢出。
- 支持验证成功欢迎消息。
- 支持答错后重新生成验证题。
- 支持通过配置自定义验证提示语、欢迎语、超时提示和踢出提示。
