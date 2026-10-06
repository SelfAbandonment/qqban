import ast
import json
import re
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import Mock

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
    methods = {"_extract_chat_messages", "_get_new_mcsm_output"}
    manager.body = [
        node
        for node in manager.body
        if isinstance(node, ast.FunctionDef) and node.name in methods
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
    namespace = {"re": re, "logger": Mock()}
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

    def test_existing_deduplication_is_preserved(self):
        output = "<Steve> #qq hello\n<Steve> #qq hello\n<Alex> #qq hello"
        self.assertEqual(
            self.manager._extract_chat_messages(output),
            [("Steve", "hello"), ("Alex", "hello")],
        )
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


if __name__ == "__main__":
    unittest.main()
