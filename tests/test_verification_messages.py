import ast
import asyncio
import importlib.util
import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "verification_messages", ROOT / "core" / "verification_messages.py"
)
messages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(messages)


def load_verification_plugin():
    tree = ast.parse((ROOT / "core" / "join_head.py").read_text(encoding="utf-8"))
    tree.body = [
        node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    tree.body.insert(
        0,
        ast.ImportFrom(
            module="__future__", names=[ast.alias(name="annotations")], level=0
        ),
    )

    def config_value(configs, keys, default):
        for config in configs:
            for key in keys:
                if key in config:
                    return config[key]
        return default

    namespace = {
        "asyncio": asyncio,
        "re": re,
        "logger": Mock(),
        "config_int": config_value,
        "config_str": config_value,
        "DEFAULT_TEMPLATES": messages.DEFAULT_TEMPLATES,
        "verification_template": messages.verification_template,
        "verification_timeout_text": messages.verification_timeout_text,
    }
    exec(compile(ast.fix_missing_locations(tree), "join_head.py", "exec"), namespace)
    return namespace["QQGroupVerifyPlugin"], namespace["_safe_format"]


Plugin, safe_format = load_verification_plugin()


class VerificationTemplateTests(unittest.TestCase):
    def test_schema_and_runtime_defaults_match(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        plugin = Plugin(Mock(), {})
        for key, template in messages.DEFAULT_TEMPLATES.items():
            with self.subTest(key=key):
                self.assertEqual(schema[key]["default"], template)
                self.assertEqual(schema[key]["type"], "text")
                self.assertEqual(getattr(plugin, key), template)

    def test_legacy_defaults_upgrade_without_mutating_configuration(self):
        for key, old_templates in messages.LEGACY_TEMPLATES.items():
            for old_template in old_templates:
                with self.subTest(key=key, template=old_template):
                    config = {key: old_template}
                    plugin = Plugin(Mock(), config)
                    self.assertEqual(
                        getattr(plugin, key), messages.DEFAULT_TEMPLATES[key]
                    )
                    self.assertEqual(config, {key: old_template})

    def test_custom_templates_are_preserved(self):
        for key in messages.DEFAULT_TEMPLATES:
            template = "{at_user} 自定义文案\n{member_name} {unknown}"
            plugin = Plugin(Mock(), {key: template})
            self.assertEqual(getattr(plugin, key), template)
            self.assertIn(
                "{unknown}", safe_format(template, at_user="成员", member_name="昵称")
            )

    def test_timeout_text_does_not_round_down(self):
        for seconds, expected in (
            (300, "5 分钟"),
            (60, "1 分钟"),
            (30, "30 秒"),
            (90, "90 秒"),
        ):
            with self.subTest(seconds=seconds):
                self.assertEqual(messages.verification_timeout_text(seconds), expected)

    def test_all_default_messages_render_without_unresolved_variables(self):
        args = {
            "at_user": "[CQ:at,qq=123]",
            "question": "23 + 18 = ?",
            "timeout_text": "5 分钟",
            "reply_instruction": "在群内 @机器人 并发送答案数字。",
            "wrong_attempts": 1,
            "remaining_attempts": 2,
            "max_wrong_attempts": 3,
            "countdown": 5,
        }
        for key, template in messages.DEFAULT_TEMPLATES.items():
            with self.subTest(key=key):
                result = safe_format(template, **args)
                self.assertTrue(result.startswith("[CQ:at,qq=123]\n【"))
                self.assertNotRegex(result, r"\{[a-z_]+\}")


class VerificationDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = SimpleNamespace(
            api=SimpleNamespace(call_action=AsyncMock(return_value={}))
        )
        self.args = {
            "at_user": "[CQ:at,qq=123]",
            "question": "23 + 18 = ?",
            "timeout": 5,
            "timeout_text": "5 分钟",
            "reply_instruction": "在群内 @机器人 并发送答案数字。",
            "wrong_attempts": 1,
            "remaining_attempts": 2,
        }

    async def send(self, mode, is_new=True, **config):
        plugin = Plugin(Mock(), {"verification_message_mode": mode, **config})
        await plugin._send_verification_prompt(
            self.bot, "123", 456, "新成员", self.args, is_new
        )
        return self.bot.api.call_action.call_args_list

    async def test_group_prompt_preserves_native_at_and_line_breaks(self):
        calls = await self.send("group")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args, ("send_group_msg",))
        self.assertEqual(calls[0].kwargs["group_id"], 456)
        self.assertEqual(
            calls[0].kwargs["message"],
            "[CQ:at,qq=123]\n【入群验证】\n欢迎加入，请在 5 分钟内完成验证。\n\n"
            "题目：23 + 18 = ?\n作答：在群内 @机器人 并发送答案数字。",
        )

    async def test_private_prompt_uses_nickname_and_direct_reply(self):
        for mode in ("private", "hybrid"):
            with self.subTest(mode=mode):
                self.bot.api.call_action.reset_mock()
                calls = await self.send(mode)
                self.assertEqual(calls[0].args, ("send_private_msg",))
                self.assertEqual(calls[0].kwargs["user_id"], 123)
                self.assertEqual(calls[0].kwargs["group_id"], 456)
                text = calls[0].kwargs["message"]
                self.assertTrue(text.startswith("新成员\n"))
                self.assertIn("直接回复答案数字，无需 @机器人。", text)
                self.assertNotIn("[CQ:at", text)
                self.assertEqual(calls[1].args, ("send_group_msg",))
                self.assertIn("请打开与机器人的私聊", calls[1].kwargs["message"])
                self.assertEqual(self.args["at_user"], "[CQ:at,qq=123]")
                self.assertEqual(
                    self.args["reply_instruction"], "在群内 @机器人 并发送答案数字。"
                )

    async def test_failed_private_delivery_restores_group_instructions(self):
        async def call_action(action, **kwargs):
            if action == "send_private_msg":
                raise RuntimeError("private delivery unavailable")
            return {}

        self.bot.api.call_action.side_effect = call_action
        for mode in ("private", "hybrid"):
            with self.subTest(mode=mode):
                self.bot.api.call_action.reset_mock()
                calls = await self.send(mode)
                self.assertEqual(calls[1].args, ("send_group_msg",))
                text = calls[1].kwargs["message"]
                self.assertTrue(text.startswith("[CQ:at,qq=123]\n"))
                self.assertIn("题目：23 + 18 = ?", text)
                self.assertIn("作答：在群内 @机器人 并发送答案数字。", text)
                self.assertNotIn("无需 @机器人", text)

    async def test_wrong_answer_in_private_only_sends_private_question(self):
        calls = await self.send("private", is_new=False)
        self.assertEqual(len(calls), 1)
        self.assertIn("已答错 1 次，剩余尝试：2。", calls[0].kwargs["message"])
        self.assertIn("直接回复答案数字", calls[0].kwargs["message"])

    async def test_custom_prompt_remains_unchanged_in_group_delivery(self):
        calls = await self.send(
            "group", new_member_prompt="{at_user} 自定义题目 {question}"
        )
        self.assertEqual(
            calls[0].kwargs["message"], "[CQ:at,qq=123] 自定义题目 23 + 18 = ?"
        )

    async def test_correct_answer_sends_sectioned_welcome_to_group(self):
        for mode in ("group", "private", "hybrid"):
            with self.subTest(mode=mode):
                self.bot.api.call_action.reset_mock()
                plugin = Plugin(Mock(), {"verification_message_mode": mode})
                task = Mock()
                plugin.pending["456:123"] = {"gid": 456, "answer": 41, "task": task}
                event = SimpleNamespace(
                    get_sender_id=lambda: "123",
                    bot=self.bot,
                    stop_event=Mock(),
                )
                await plugin._process_answer(
                    event, "456:123", "41", {"sender": {"nickname": "新成员"}}
                )
                self.bot.api.call_action.assert_awaited_once_with(
                    "send_group_msg",
                    group_id=456,
                    message=(
                        "[CQ:at,qq=123]\n【验证通过】\n欢迎加入本群，祝你玩得愉快！\n\n"
                        "【入群指引】\n• 群规与通知：请先阅读群公告\n"
                        "• 游戏客户端：前往群文件下载整合包\n"
                        "• 服务器地址：查看整合包内附的 IP"
                    ),
                )
                task.cancel.assert_called_once()
                self.assertEqual(plugin.pending, {})
                event.stop_event.assert_called_once()

    async def test_correct_answer_preserves_custom_welcome(self):
        plugin = Plugin(Mock(), {"welcome_message": "{at_user} 欢迎 {member_name}！"})
        plugin.pending["456:123"] = {"gid": 456, "answer": 41, "task": Mock()}
        event = SimpleNamespace(
            get_sender_id=lambda: "123", bot=self.bot, stop_event=Mock()
        )
        await plugin._process_answer(
            event, "456:123", "41", {"sender": {"card": "自定义昵称"}}
        )
        self.bot.api.call_action.assert_awaited_once_with(
            "send_group_msg", group_id=456, message="[CQ:at,qq=123] 欢迎 自定义昵称！"
        )


if __name__ == "__main__":
    unittest.main()
