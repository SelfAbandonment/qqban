# QQVerify

QQVerify 是一个 AstrBot 群成员入群验证插件。新成员入群后，插件会自动生成数学验证题，用户需要在规定时间内完成验证；超时或连续答错达到上限后，插件会自动执行踢出流程。

插件的核心目标是减少广告号、机器人和批量小号进群带来的管理压力。

## 功能

- 新成员入群自动下发数学验证题
- 支持群聊验证、私聊验证、优先私聊失败回退群聊
- 支持验证超时警告、超时踢出和踢出前倒计时
- 支持最大答错次数限制
- 支持 easy、normal、hard 三档题目难度
- 验证状态按群号和用户号隔离，避免多群验证互相覆盖
- 插件卸载时自动清理待验证任务
- 验证成功、答错、超时、踢出等提示语均可配置

## 使用要求

- AstrBot 已正常运行
- Bot 需要在目标 QQ 群中拥有发送消息权限
- 如果需要自动踢出未验证用户，Bot 需要拥有群管理员权限
- 如果启用私聊验证，平台和用户设置需要允许 Bot 向新成员发送私聊消息

## 安装

将本插件放入 AstrBot 插件目录后，在 AstrBot 中启用插件即可。

插件元信息位于 [metadata.yaml](metadata.yaml)，配置项位于 [_conf_schema.json](_conf_schema.json)。

## 验证流程

默认流程如下：

1. 新成员加入群聊。
2. 插件生成一道数学验证题。
3. 插件在群内发送验证提示。
4. 用户在群内 `@Bot 答案`。
5. 答案正确后发送欢迎语，验证结束。
6. 超时或答错次数过多后，插件发送提示并踢出用户。

如果启用私聊验证，用户可以直接在私聊里回复答案数字。

## 推荐配置

稳妥的默认配置：

```json
{
  "verification_timeout": 300,
  "kick_countdown_warning_time": 60,
  "kick_delay": 5,
  "max_wrong_attempts": 3,
  "verification_difficulty": "normal",
  "verification_message_mode": "group"
}
```

更安静的群聊体验：

```json
{
  "verification_message_mode": "hybrid"
}
```

`hybrid` 会优先私聊发送验证题；如果私聊失败，会自动回退到群内发送验证题。

## 配置说明

修改配置后，可以发送以下命令让插件重新读取 AstrBot 配置和本地兜底配置：

```text
/qqverify_reload
```

如果已配置 `mc_admin_qq`，该命令仅允许白名单用户执行；如果管理员列表尚未读取成功，则允许执行，方便修复配置。

插件按照 AstrBot 官方配置方式读取配置：AstrBot 会根据 [_conf_schema.json](_conf_schema.json) 生成配置文件，并在插件实例化时传入配置对象。`/qqverify_reload` 会基于当前配置对象重新刷新运行时参数。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `verification_timeout` | `300` | 验证总超时时间，单位秒。 |
| `kick_countdown_warning_time` | `60` | 踢出前提前多少秒发送警告。设为 `0` 可禁用提前警告。 |
| `kick_delay` | `5` | 发送验证失败提示后，等待多少秒再踢出。 |
| `max_wrong_attempts` | `3` | 最大答错次数。设为 `0` 表示不限制答错次数。 |
| `verification_difficulty` | `normal` | 题目难度，可选 `easy`、`normal`、`hard`。 |
| `verification_message_mode` | `group` | 验证消息发送模式，可选 `group`、`private`、`hybrid`。 |

### 题目难度

| 难度 | 说明 |
| --- | --- |
| `easy` | 简单加减法。适合普通群，用户体验最好。 |
| `normal` | 加法、减法、整除法。默认推荐。 |
| `hard` | 加法、减法、乘法、整除法、数列题。适合广告号较多的群。 |

### 验证消息模式

| 模式 | 说明 |
| --- | --- |
| `group` | 在群内发送验证题，用户需要在群内 `@Bot 答案`。兼容性最好。 |
| `private` | 私聊发送验证题，群内只发送提示。若私聊失败，会在群内发送回退题目。 |
| `hybrid` | 优先私聊发送验证题，失败后自动回退群内发送。推荐想减少群内刷屏的群使用。 |

## 消息模板变量

以下模板支持自定义：

- `new_member_prompt`：新成员入群验证提示
- `welcome_message`：验证成功欢迎语
- `wrong_answer_prompt`：答错后重新出题提示
- `wrong_answer_limit_prompt`：答错次数达到上限提示
- `private_verification_notice_prompt`：私聊验证成功发送后，群内提示
- `private_message_failed_prompt`：私聊发送失败后的群内提示
- `countdown_warning_prompt`：验证即将超时提示
- `failure_message`：验证失败、踢出前提示
- `kick_message`：踢出后提示

常用变量：

| 变量 | 说明 |
| --- | --- |
| `{at_user}` | 被验证用户的 CQ at。私聊验证题中会替换为昵称。 |
| `{member_name}` | 用户群昵称或 QQ 号。 |
| `{question}` | 当前验证题。 |
| `{timeout}` | 验证超时时间，单位分钟。 |
| `{countdown}` | 踢出前等待秒数。 |
| `{wrong_attempts}` | 当前已答错次数。 |
| `{remaining_attempts}` | 剩余可答错次数。 |
| `{max_wrong_attempts}` | 最大答错次数。 |

示例：

```text
{at_user} 欢迎加入本群！请在 {timeout} 分钟内完成验证：
{question}
```

## 注意事项

- 群内验证时，用户需要 `@Bot` 并发送答案，避免普通聊天中的数字误触发验证。
- 私聊验证时，如果用户关闭临时会话或平台不允许 Bot 私聊，可能发送失败。建议使用 `hybrid` 模式。
- 自动踢人需要 Bot 是群管理员，否则插件只能发送提示，无法完成踢出动作。
- 插件重启后，内存中的待验证状态不会恢复。正在验证中的用户可能需要重新触发验证流程。

## 可选 MC 扩展

当前插件中还包含一个可选的 Minecraft RCON 扩展模块，用于 `/tomc`、`/mcrestart`、`/myid` 等命令。入群验证功能不依赖该模块。

MC RCON 功能不会后台主动连接服务器，只有调用 `/tomc`、`/mcrestart` 等命令时才会尝试连接 RCON。

如果不使用 MC 功能，不需要填写 RCON 配置。使用 MC 功能时，请至少填写 `rcon_ip`、`rcon_port` 和 `rcon_password`。

兼容旧配置字段名：`RCON_IP`、`RCON_PORT`、`RCON_PASSWORD`、`RCON_TIMEOUT`、`ADMIN_QQ`。如果日志仍提示密码未配置，请重载插件后查看启动日志中的 `[MC RCON] 配置状态`，确认 `password` 是否显示为 `已配置`。

如果 AstrBot 配置没有传入插件，也可以在插件目录新建 `rcon_config.json` 作为兜底配置。该文件已加入 `.gitignore`，不要提交到仓库：

```json
{
  "rcon_ip": "127.0.0.1",
  "rcon_port": 25575,
  "rcon_password": "你的RCON密码",
  "mc_admin_qq": "123456789"
}
```

创建或修改该文件后，可以发送 `/qqverify_reload` 重新读取配置，不必重启 AstrBot。重载成功后，日志中应显示：

```text
[Config] 已加载本地配置文件: rcon_config.json
[MC RCON] 配置状态: ip=你的服务器IP, port=21002, password=已配置, admin_count=1
```

启用示例：

```json
{
  "rcon_ip": "127.0.0.1",
  "rcon_port": 25575,
  "rcon_password": "你的RCON密码",
  "mc_admin_qq": "123456789"
}
```

如果不使用 MC 功能，可以忽略以下配置：

- `rcon_ip`
- `rcon_port`
- `rcon_password`
- `rcon_timeout`
- `mc_admin_qq`

## 相关链接

- [更新日志](CHANGELOG.md)
- [AstrBot 帮助文档](https://astrbot.app)
