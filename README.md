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
- 使用 `aiocqhttp`（OneBot v11，例如 NapCat、Lagrange）平台适配器；入群验证和踢人依赖其 QQ 协议端 API，不支持 QQ 官方机器人适配器
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

### QQ 验证消息样式

验证消息使用 QQ 原生 @成员和普通分段文字，不使用 Markdown、JSON 卡片或合并转发。题目无需点开卡片即可查看、复制，群聊与私聊会分别显示正确的作答说明：

```text
@新成员
【入群验证】
欢迎加入，请在 5 分钟内完成验证。

题目：23 + 18 = ?
作答：在群内 @机器人 并发送答案数字。
```

私聊中首行显示成员昵称，作答说明为“直接回复答案数字，无需 @机器人”。私聊失败回退群聊时恢复群内作答说明。答错、成功及超时提示使用相同的分段样式。

配置面板的验证文案使用多行文本框。更新后，完全匹配旧版默认值的文案会在发送时采用新排版，不改写保存的配置；其他自定义文案原样保留。自定义文案中可使用 `{reply_instruction}` 适配群聊/私聊，而硬编码的“@我”不会自动替换。

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

`hybrid` 会优先私聊发送验证题；如果私聊失败，会自动回退到群内发送验证题。使用 NapCat/OneBot 时，插件会尝试带 `group_id` 的私聊发送，以利用群临时会话能力。

## 配置说明

插件按照 AstrBot 官方配置方式读取配置：AstrBot 会根据 [_conf_schema.json](_conf_schema.json) 生成配置文件，并在插件实例化时传入配置对象。修改配置后，请重启插件或 AstrBot 让新配置生效。

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
| `private` | 私聊发送验证题，群内只发送提示。若私聊失败，会在群内发送回退题目。NapCat/OneBot 下会尝试带 `group_id` 的群临时会话。 |
| `hybrid` | 优先私聊发送验证题，失败后自动回退群内发送。推荐想减少群内刷屏的群使用。NapCat/OneBot 下会尝试带 `group_id` 的群临时会话。 |

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
| `{timeout_text}` | 带单位的验证时长；整分钟显示分钟，否则显示秒，适用于入群题目、私聊通知和私聊失败回退提示。 |
| `{reply_instruction}` | 当前题目的作答说明；群聊要求 @机器人，私聊直接回复数字，适用于入群题目、答错题目和私聊失败回退提示。 |
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
- 私聊验证时，插件会尝试 NapCat/OneBot 带 `group_id` 的群临时会话；如果用户关闭临时会话、平台限制主动私聊或协议端拒绝发送，仍可能失败。建议使用 `hybrid` 模式。
- 自动踢人需要 Bot 是群管理员，否则插件只能发送提示，无法完成踢出动作。
- 插件重启后，内存中的待验证状态不会恢复。正在验证中的用户可能需要重新触发验证流程。
- 入群验证依赖平台上报 `group_increase` 通知。OneBot/aiocqhttp 需要确保连接端能上报群成员增加 notice 事件。

## 可选 MC 扩展

当前插件中还包含可选的 Minecraft 扩展能力。入群验证功能不依赖这些模块。

### QQ 到 MC

RCON 用于 `/tomc`、`/mcrestart`、`/myid` 等命令。

MC RCON 功能不会后台主动连接服务器，只有调用 `/tomc`、`/mcrestart` 等命令时才会尝试连接 RCON。

如果不使用 MC 功能，不需要填写 RCON 配置。使用 MC 功能时，请至少填写 `rcon_ip`、`rcon_port` 和 `rcon_password`。

兼容旧配置字段名：`RCON_IP`、`RCON_PORT`、`RCON_PASSWORD`、`RCON_TIMEOUT`、`ADMIN_QQ`。如果日志仍提示密码未配置，请重启插件或 AstrBot 后查看启动日志中的 `[MC RCON] 配置状态`，确认 `password` 是否显示为 `已配置`。

优先通过 AstrBot WebUI 配置 RCON。如果需要本地兜底配置，可以在 AstrBot 数据目录下新建 `data/plugin_data/QQVerify/rcon_config.json`（缺失的目录请自行创建）。WebUI 中非空的配置优先于本地配置。不要将含密码的文件提交到仓库：

```json
{
  "rcon_ip": "127.0.0.1",
  "rcon_port": 25575,
  "rcon_password": "你的RCON密码",
  "mc_admin_qq": "123456789"
}
```

创建或修改该文件后，请重启插件或 AstrBot 重新读取配置。启动日志中应显示：

```text
[Config] 已加载本地配置文件: rcon_config.json
[MC RCON] 配置状态: ip=你的服务器IP, port=21002, password=已配置, admin_count=1
```

旧版插件目录下的 `rcon_config.json` 仍可读取，但会提示迁移。请将旧文件移到上述数据目录，避免插件更新或重装时被覆盖；两处同时存在时，只读取数据目录下的文件。插件不会自动复制或改写含凭据的配置文件。

WebUI 配置示例：

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

### MC 到 QQ

如果服务器由 MCSManager 管理，可以启用 MCSM 输出日志轮询。插件会定时调用：

```text
GET /api/protected_instance/outputlog
```

然后从实例控制台输出中匹配玩家聊天行。只有以指定前缀（默认 `#qq`）开头、前缀后带空白和正文的消息才会转发，例如：

```text
[Server thread/INFO]: <Steve> #qq hello
```

转发为：

```text
[服内] Steve: hello
```

配置示例：

```json
{
  "mcsm_chat_enabled": true,
  "mcsm_chat_prefix": "#qq",
  "mcsm_base_url": "http://127.0.0.1:23333",
  "mcsm_api_key": "你的MCSM API Key",
  "mcsm_instance_uuid": "实例UUID",
  "mcsm_daemon_id": "Daemon ID",
  "mcsm_output_size": 64,
  "mcsm_poll_interval": 2.0
}
```

可通过 `mcsm_chat_prefix` 自定义前缀，留空使用默认 `#qq`。前缀区分大小写，转发时会去掉前缀及正文两端的空白。普通聊天、只发送 `#qq`、`#qqhello` 或在正文中间出现 `#qq` 都不会转发。此筛选只影响 MC 到 QQ，不影响 QQ 的 `/tomc` 命令，也不会隐藏游戏内的原始聊天。

转发目标优先使用 `/tomc` 最近绑定过的会话。也就是说，先在目标群里发送一次 `/tomc 测试`，之后服内带前缀的聊天会转发到这个群。

如果没有绑定会话，可以配置 `mcsm_forward_group` 作为默认群号；但该方式需要 Bot 运行时已经拿到平台实例，稳定性不如 `/tomc` 绑定。

注意：监听任务启动后第一次拉取日志只会建立游标，不会把旧日志全部刷到 QQ；之后只转发新增且带前缀的聊天。更新前已启用监听的用户也会使用默认 `#qq` 筛选，更新后请重启插件。

## 相关链接

- [更新日志](CHANGELOG.md)
- [AstrBot 帮助文档](https://astrbot.app)

## 开发与基础规范

- 插件元信息统一由 `metadata.yaml` 提供，保留已有唯一标识 `QQVerify`，避免更名导致配置关联变化。
- 配置通过官方 `AstrBotConfig` 构造参数注入；命令入口位于 `main.py`，具体业务保留在 `core` 中。
- 插件只使用 Python 标准库与 AstrBot 提供的 API，没有额外第三方运行依赖，因此不需要 `requirements.txt`。
- 卸载或重载时会取消并等待已记录的验证任务和 MCSM 监听任务退出。
- 验证状态仍仅保存在内存中；本次未改变验证流程，也未增加状态持久化。

本地回归测试不需要运行 AstrBot：

```bash
python -m unittest discover -s tests -v
python -m compileall -q main.py core tests
python -m ruff check .
python -m ruff format --check .
```

Ruff 为开发工具，不是插件运行依赖，可通过 `python -m pip install ruff` 安装；检查规则由仓库的 `ruff.toml` 定义，不依赖上级目录配置。开发及实际运行建议使用 AstrBot 支持的 Python 3.10 或更新版本。真实平台事件、RCON 和 MCSM 联调需将插件放入 AstrBot 的 `data/plugins` 目录，启动 AstrBot 并在 WebUI 中重载插件。

规范依据：[官方插件开发指南](https://github.com/AstrBotDevs/AstrBot-docs/blob/v4/zh/dev/star/plugin-new.md)、[配置文档](https://github.com/AstrBotDevs/AstrBot-docs/blob/v4/zh/dev/star/guides/plugin-config.md)、[存储文档](https://github.com/AstrBotDevs/AstrBot-docs/blob/v4/zh/dev/star/guides/storage.md)。

验证消息继续使用现有 OneBot QQ 协议端 API 发送，保留 `{at_user}` 的原生 CQ @行为。相关规范：[官方消息发送文档](https://github.com/AstrBotDevs/AstrBot-docs/blob/v4/zh/dev/star/guides/send-message.md)、[QQ 协议端 API 调用文档](https://github.com/AstrBotDevs/AstrBot-docs/blob/v4/zh/dev/star/guides/other.md)。
