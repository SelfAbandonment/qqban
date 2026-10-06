import ast
import json
import re
import threading
import unittest
import urllib.parse
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]


def load_chat_methods():
    """Load the log parser without requiring AstrBot or starting a monitor."""
    tree = ast.parse(
        (ROOT / "core" / "minecraft_manager.py").read_text(encoding="utf-8")
    )
    manager = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MinecraftManager"
    )
    methods = {
        "_extract_chat_messages",
        "_get_new_mcsm_output",
        "_build_mcsm_output_url",
        "_fetch_mcsm_output_sync",
        "_forward_mc_chat",
        "send_to_mc",
        "_get_configured_mcsm_bot",
    }
    manager.body = [
        node
        for node in manager.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in methods
    ]
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__", names=[ast.alias(name="annotations")], level=0
            ),
            manager,
        ],
        type_ignores=[],
    )
    namespace = {
        "re": re,
        "json": json,
        "logger": Mock(),
        "urllib": urllib,
        "Comp": SimpleNamespace(Plain=lambda text: SimpleNamespace(text=text)),
        "MessageEventResult": lambda chain: SimpleNamespace(chain=chain),
    }
    exec(
        compile(
            ast.fix_missing_locations(module),
            str(ROOT / "core" / "minecraft_manager.py"),
            "exec",
        ),
        namespace,
    )
    return namespace["MinecraftManager"]


MinecraftManager = load_chat_methods()


class MinecraftChatTests(unittest.TestCase):
    def setUp(self):
        self.manager = MinecraftManager()
        self.manager.mcsm_chat_prefix = "#qq"
        self.manager.mcsm_recent_chat_lines = deque(maxlen=200)
        self.manager.mcsm_last_output = ""
        self.manager.mcsm_output_initialized = False

    def test_prefix_is_removed_from_supported_log_formats(self):
        output = (
            "[Server thread/INFO]: <Steve> #qq hello\n"
            "[12:34:56] [Server thread/INFO]: [Not Secure] <Alex> #qq hi there\n"
            "<Player> #qq   extra spaces   \n"
        )
        self.assertEqual(
            self.manager._extract_chat_messages(output),
            [("Steve", "hello"), ("Alex", "hi there"), ("Player", "extra spaces")],
        )

    def test_ordinary_chat_and_invalid_prefix_messages_are_ignored(self):
        for message in (
            "hello",
            "#qq",
            "#qq   ",
            "#qqhello",
            "#qqx hello",
            "hello #qq world",
            "#QQ hello",
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    self.manager._extract_chat_messages(f"<Steve> {message}"), []
                )
        self.assertEqual(list(self.manager.mcsm_recent_chat_lines), [])

    def test_custom_prefix_and_whitespace_separator(self):
        self.manager.mcsm_chat_prefix = "!qq"
        self.assertEqual(
            self.manager._extract_chat_messages("<Steve> !qq\thello\n<Alex> #qq hi"),
            [("Steve", "hello")],
        )

    def test_at_prefix_matches_reported_forge_log(self):
        self.manager.mcsm_chat_prefix = "@qq"
        output = (
            "[08:01:09] [Server thread/INFO] [minecraft/MinecraftServer]: "
            "<SelfAbandonmen> @qq 测试11\n"
            "[08:09:09] [Server thread/INFO] [minecraft/MinecraftServer]: "
            "<SelfAbandonmen> @qq 测试22"
        )
        self.assertEqual(
            self.manager._extract_chat_messages(output),
            [("SelfAbandonmen", "测试11"), ("SelfAbandonmen", "测试22")],
        )

    def test_messages_after_empty_initial_log_are_not_discarded(self):
        self.manager.mcsm_chat_prefix = "@qq"
        self.assertEqual(self.manager._get_new_mcsm_output(""), "")
        self.assertEqual(self.manager._get_new_mcsm_output(""), "")
        new_output = self.manager._get_new_mcsm_output("<Steve> @qq hello\n")
        self.assertEqual(
            self.manager._extract_chat_messages(new_output), [("Steve", "hello")]
        )

    def test_outputlog_request_uses_kilobyte_unit(self):
        self.manager.mcsm_base_url = "http://localhost:23333"
        self.manager.mcsm_instance_uuid = "instance"
        self.manager.mcsm_daemon_id = "daemon"
        self.manager.mcsm_api_key = ""
        for size in (16, 64, 128):
            with self.subTest(size=size):
                self.manager.mcsm_output_size = size
                url = urllib.parse.urlsplit(self.manager._build_mcsm_output_url())
                query = urllib.parse.parse_qs(url.query)
                self.assertEqual(query["size"], [f"{size}kb"])
                self.assertEqual(query["uuid"], ["instance"])
                self.assertEqual(query["daemonId"], ["daemon"])
                self.assertNotIn("apikey", query)

    def test_kilobyte_window_preserves_full_reported_chat_line(self):
        self.manager.mcsm_chat_prefix = "@qq"
        line = (
            "[08:09:09] [Server thread/INFO] [minecraft/MinecraftServer]: "
            "<SelfAbandonmen> @qq 测试22\n"
        )
        output = line + "[08:09:10] [Server thread/INFO]: Saving world data\n"
        self.assertGreater(len(output), 64)
        self.assertEqual(self.manager._extract_chat_messages(output[-64:]), [])
        self.assertEqual(
            self.manager._extract_chat_messages(output[-64 * 1024 :]),
            [("SelfAbandonmen", "测试22")],
        )

    def test_extraction_does_not_mark_unsent_messages_as_delivered(self):
        output = "<Steve> #qq hello\n<Steve> #qq hello\n<Alex> #qq hello"
        self.assertEqual(
            self.manager._extract_chat_messages(output),
            [("Steve", "hello"), ("Alex", "hello")],
        )
        self.assertEqual(list(self.manager.mcsm_recent_chat_lines), [])
        self.assertEqual(
            self.manager._extract_chat_messages(output),
            [("Steve", "hello"), ("Alex", "hello")],
        )
        self.manager.mcsm_recent_chat_lines.extend(["Steve\0hello", "Alex\0hello"])
        self.assertEqual(self.manager._extract_chat_messages(output), [])

    def test_initial_history_is_not_forwarded(self):
        history = "<Steve> #qq old\n"
        self.assertEqual(self.manager._get_new_mcsm_output(history), "")
        new_output = self.manager._get_new_mcsm_output(
            history + "<Steve> ordinary chat\n<Alex> #qq new\n"
        )
        self.assertEqual(
            self.manager._extract_chat_messages(new_output), [("Alex", "new")]
        )

    def test_schema_default_matches_prefix(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        self.assertEqual(
            schema["mcsm_chat_prefix"]["default"], self.manager.mcsm_chat_prefix
        )


class MinecraftDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.output = ""
        self.queries = []
        test = self

        class OutputLogHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                test.queries.append(query)
                size = query["size"][0]
                limit = int(size[:-2]) * 1024 if size.endswith("kb") else int(size)
                body = json.dumps(
                    {"status": 200, "data": test.output[-limit:]}, ensure_ascii=False
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), OutputLogHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.manager = MinecraftManager()
        self.manager.mcsm_base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.manager.mcsm_instance_uuid = "test-instance"
        self.manager.mcsm_daemon_id = "test-daemon"
        self.manager.mcsm_api_key = ""
        self.manager.mcsm_output_size = 64
        self.manager.rcon_timeout = 2
        self.manager.mcsm_chat_prefix = "@qq"
        self.manager.mcsm_last_output = ""
        self.manager.mcsm_output_initialized = False
        self.manager.mcsm_recent_chat_lines = deque(maxlen=200)
        self.manager.forwarded_msgs = deque(maxlen=500)
        self.manager.target_umo = None
        self.manager.target_group_id = None
        self.manager.bound_bot = None
        self.manager.mcsm_forward_group = ""
        self.manager.mcsm_platform_id = ""
        self.platforms = []
        self.manager.context = SimpleNamespace(
            send_message=AsyncMock(),
            platform_manager=SimpleNamespace(get_insts=lambda: self.platforms),
        )
        self.bot = SimpleNamespace(
            api=SimpleNamespace(
                call_action=AsyncMock(return_value={"message_id": 789})
            ),
            group_poke=AsyncMock(),
        )

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def chat(self, time, message="测试"):
        return (
            f"[{time}] [Server thread/INFO] [minecraft/MinecraftServer]: "
            f"<SelfAbandonmen> @qq {message}\n"
        )

    async def poll(self):
        output = self.manager._fetch_mcsm_output_sync()
        new_output = self.manager._get_new_mcsm_output(output)
        for username, message in self.manager._extract_chat_messages(new_output):
            await self.manager._forward_mc_chat(username, message)

    async def bind_with_tomc(self):
        self.manager.execute_rcon = AsyncMock(return_value=(True, ""))
        event = SimpleNamespace(
            unified_msg_origin="test:GroupMessage:456",
            bot=self.bot,
            get_group_id=lambda: "456",
            get_sender_name=lambda: "QQ user",
            get_sender_id=lambda: "123",
        )
        await self.manager.send_to_mc(event, "测试")

    async def test_unbound_chat_can_be_resent_after_tomc_binding(self):
        await self.poll()
        self.output += self.chat("08:36:07")
        await self.poll()
        self.assertEqual(list(self.manager.mcsm_recent_chat_lines), [])
        await self.bind_with_tomc()
        self.output += self.chat("08:36:22")
        await self.poll()
        self.bot.api.call_action.assert_awaited_once_with(
            "send_group_msg", group_id=456, message="[服内] SelfAbandonmen: 测试"
        )
        self.assertEqual(list(self.manager.forwarded_msgs), [("789", "SelfAbandonmen")])
        self.assertEqual(self.queries[-1]["size"], ["64kb"])

    async def test_failed_send_does_not_block_player_retry(self):
        await self.poll()
        await self.bind_with_tomc()
        self.bot.api.call_action.side_effect = RuntimeError("send failed")
        self.output += self.chat("08:36:22")
        with self.assertRaisesRegex(RuntimeError, "send failed"):
            await self.poll()
        self.assertEqual(list(self.manager.mcsm_recent_chat_lines), [])
        self.bot.api.call_action.side_effect = None
        self.output += self.chat("08:36:25")
        await self.poll()
        self.assertEqual(self.bot.api.call_action.await_count, 2)

    async def test_duplicate_batch_is_only_sent_once_after_success(self):
        await self.poll()
        await self.bind_with_tomc()
        self.output += self.chat("08:36:22") + self.chat("08:36:23")
        await self.poll()
        self.bot.api.call_action.assert_awaited_once()
        self.output += self.chat("08:36:25")
        await self.poll()
        self.bot.api.call_action.assert_awaited_once()

    async def test_context_route_marks_success_only_after_send(self):
        await self.poll()
        self.manager.target_umo = "test:GroupMessage:456"
        self.manager.context.send_message.side_effect = RuntimeError(
            "context send failed"
        )
        self.output += self.chat("08:36:22")
        with self.assertRaisesRegex(RuntimeError, "context send failed"):
            await self.poll()
        self.assertEqual(list(self.manager.mcsm_recent_chat_lines), [])
        self.manager.context.send_message.side_effect = None
        self.output += self.chat("08:36:25")
        await self.poll()
        self.assertEqual(self.manager.context.send_message.await_count, 2)
        self.assertEqual(len(self.manager.mcsm_recent_chat_lines), 1)

    def platform(self, platform_id, bot=None, name="aiocqhttp"):
        return SimpleNamespace(
            meta=lambda: SimpleNamespace(id=platform_id, name=name),
            get_client=lambda: bot,
        )

    async def test_configured_group_works_without_tomc_or_rcon(self):
        await self.poll()
        self.manager.mcsm_forward_group = "987"
        self.platforms.append(self.platform("onebot-main", self.bot))
        self.output += self.chat("08:36:22")
        await self.poll()
        self.bot.api.call_action.assert_awaited_once_with(
            "send_group_msg", group_id=987, message="[服内] SelfAbandonmen: 测试"
        )
        self.assertIsNone(self.manager.bound_bot)
        self.assertIsNone(self.manager.target_umo)

    async def test_platform_id_selects_robot_and_ignores_other_adapters(self):
        other_bot = SimpleNamespace(api=SimpleNamespace(call_action=AsyncMock()))
        self.platforms.extend(
            [
                self.platform("other", other_bot),
                self.platform("chosen", self.bot),
                self.platform("telegram", other_bot, name="telegram"),
            ]
        )
        self.manager.mcsm_forward_group = "987"
        self.manager.mcsm_platform_id = "chosen"
        await self.manager._forward_mc_chat("Steve", "hello")
        self.bot.api.call_action.assert_awaited_once()
        other_bot.api.call_action.assert_not_awaited()

    async def test_missing_or_ambiguous_platform_never_falls_back_to_tomc(self):
        await self.bind_with_tomc()
        self.manager.mcsm_forward_group = "987"
        for platform_id, platforms in (
            ("", []),
            ("", [self.platform("a", self.bot), self.platform("b", self.bot)]),
            ("missing", [self.platform("a", self.bot)]),
            ("", [self.platform("a", None)]),
        ):
            with self.subTest(platform_id=platform_id, count=len(platforms)):
                self.platforms[:] = platforms
                self.manager.mcsm_platform_id = platform_id
                self.assertFalse(await self.manager._forward_mc_chat("Steve", "hello"))
                self.bot.api.call_action.assert_not_awaited()
                self.manager.context.send_message.assert_not_awaited()
                self.assertEqual(list(self.manager.mcsm_recent_chat_lines), [])

    async def test_platform_can_become_available_after_plugin_start(self):
        self.manager.mcsm_forward_group = "987"
        self.assertFalse(await self.manager._forward_mc_chat("Steve", "hello"))
        self.platforms.append(self.platform("main", self.bot))
        self.assertTrue(await self.manager._forward_mc_chat("Steve", "hello"))
        self.bot.api.call_action.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
