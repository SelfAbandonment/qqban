DEFAULT_TEMPLATES = {
    "new_member_prompt": (
        "{at_user}\n【入群验证】\n欢迎加入，请在 {timeout_text}内完成验证。\n\n"
        "题目：{question}\n作答：{reply_instruction}"
    ),
    "welcome_message": (
        "{at_user}\n【验证成功】\n欢迎加入！\n\n"
        "1. 请仔细阅读群公告\n2. 群文件可下载整合包，内含服务器 IP\n\n祝你玩得愉快！"
    ),
    "wrong_answer_prompt": (
        "{at_user}\n【答案错误】\n已答错 {wrong_attempts} 次，剩余尝试：{remaining_attempts}。\n\n"
        "新题目：{question}\n作答：{reply_instruction}"
    ),
    "wrong_answer_limit_prompt": (
        "{at_user}\n【验证失败】\n答错次数已达到上限（{max_wrong_attempts} 次）。\n"
        "将在 {countdown} 秒后被移出本群。"
    ),
    "private_verification_notice_prompt": (
        "{at_user}\n【入群验证】\n验证题已发送至私聊，请在 {timeout_text}内完成。\n"
        "请打开与机器人的私聊，直接回复答案数字。"
    ),
    "private_message_failed_prompt": (
        "{at_user}\n【入群验证】\n私聊发送失败，请在群内完成验证。\n"
        "请在 {timeout_text}内作答。\n\n题目：{question}\n作答：{reply_instruction}"
    ),
    "countdown_warning_prompt": (
        "{at_user}\n【验证即将超时】\n请尽快查看验证题，并按题目下方的作答说明完成验证。"
    ),
    "failure_message": (
        "{at_user}\n【验证超时】\n未在规定时间内完成验证。\n"
        "将在 {countdown} 秒后被移出本群。"
    ),
    "kick_message": "{at_user}\n【已移出本群】\n入群验证未通过。",
}

LEGACY_TEMPLATES = {
    "new_member_prompt": {
        "{at_user} 欢迎加入本群！请在 {timeout} 分钟内 @我 并回答下面的问题以完成验证：\n{question}",
        "{at_user} 欢迎加入本群！请在 {timeout} 分钟内@我并回答下面的问题以完成验证：\n{question}",
    },
    "welcome_message": {
        "{at_user} 验证成功，欢迎你的加入！\n1.请仔细阅读群公告\n2.群文件下载整合包自带IP\n最后祝您玩得愉快",
    },
    "wrong_answer_prompt": {
        "{at_user} 答案错误，请重新回答验证。这是你的新问题：\n{question}",
    },
    "wrong_answer_limit_prompt": {
        "{at_user} 答案错误次数过多，你将在 {countdown} 秒后被请出本群。",
    },
    "private_verification_notice_prompt": {
        "{at_user} 验证题已通过私聊发送，请在 {timeout} 分钟内完成验证。",
    },
    "private_message_failed_prompt": {
        "{at_user} 私聊发送失败，请在群内 @我 回答下面的问题完成验证：\n{question}",
    },
    "countdown_warning_prompt": {
        "{at_user} 验证即将超时，请尽快查看我（BOT）的验证消息进行人机验证！",
        "{at_user} 验证即将超时，请尽快查看我的验证消息进行人机验证！",
    },
    "failure_message": {
        "{at_user} 验证超时，你将在 {countdown} 秒后被请出本群。",
    },
    "kick_message": {
        "{at_user} 因未在规定时间内完成验证，已被请出本群。",
    },
}


def verification_template(key: str, value: str) -> str:
    if value in LEGACY_TEMPLATES[key]:
        return DEFAULT_TEMPLATES[key]
    return value


def verification_timeout_text(seconds: int) -> str:
    if seconds % 60 == 0:
        return f"{seconds // 60} 分钟"
    return f"{seconds} 秒"
