import ast
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load_config_helpers(data_path, plugin_path):
    tree = ast.parse((ROOT / "core" / "config_utils.py").read_text(encoding="utf-8"))
    tree.body = [
        node
        for node in tree.body
        if not isinstance(node, ast.ImportFrom) or not node.module.startswith("astrbot")
    ]
    tree.body.insert(
        0,
        ast.ImportFrom(
            module="__future__", names=[ast.alias(name="annotations")], level=0
        ),
    )
    namespace = {
        "logger": Mock(),
        "get_astrbot_data_path": lambda: data_path,
        "__file__": str(plugin_path / "core" / "config_utils.py"),
    }
    exec(compile(ast.fix_missing_locations(tree), "config_utils.py", "exec"), namespace)
    return namespace


def load_method(file_name, class_name, method_name):
    tree = ast.parse((ROOT / file_name).read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(node for node in cls.body if node.name == method_name)
    module = ast.Module(body=[method], type_ignores=[])
    namespace = {"asyncio": asyncio, "logger": Mock()}
    exec(compile(ast.fix_missing_locations(module), str(file_name), "exec"), namespace)
    return namespace[method_name]


class ConfigStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.data_path = root / "data"
        self.plugin_path = root / "plugin"
        self.plugin_path.mkdir()
        self.preferred = (
            self.data_path / "plugin_data" / "QQVerify" / "rcon_config.json"
        )
        self.helpers = load_config_helpers(self.data_path, self.plugin_path)

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_absent_local_config_is_optional(self):
        self.assertEqual(self.helpers["load_json_config"]("rcon_config.json"), {})
        self.helpers["logger"].warning.assert_not_called()

    def test_data_directory_takes_precedence(self):
        self.write_json(self.preferred, {"rcon_port": 25576})
        self.write_json(self.plugin_path / "rcon_config.json", {"rcon_port": 25575})
        self.assertEqual(
            self.helpers["load_json_config"]("rcon_config.json"), {"rcon_port": 25576}
        )
        self.helpers["logger"].warning.assert_not_called()

    def test_legacy_file_remains_readable_with_migration_warning(self):
        legacy = self.plugin_path / "rcon_config.json"
        self.write_json(legacy, {"rcon_port": 25575})
        self.assertEqual(
            self.helpers["load_json_config"]("rcon_config.json"), {"rcon_port": 25575}
        )
        self.helpers["logger"].warning.assert_called_once()
        self.assertTrue(legacy.exists())
        self.assertFalse(self.preferred.exists())

    def test_invalid_config_logs_error_without_using_stale_legacy_file(self):
        self.write_json(self.plugin_path / "rcon_config.json", {"rcon_port": 25575})
        for content in ("[]", "{invalid json"):
            with self.subTest(content=content):
                self.preferred.parent.mkdir(parents=True, exist_ok=True)
                self.preferred.write_text(content, encoding="utf-8")
                self.helpers["logger"].reset_mock()
                self.assertEqual(
                    self.helpers["load_json_config"]("rcon_config.json"), {}
                )
                self.helpers["logger"].warning.assert_called_once()

    def test_injected_config_and_aliases_still_take_precedence(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                self.helpers["config_int"](
                    [{"nested": {"RCON_PORT": {"value": 25576}}}, {"rcon_port": 25575}],
                    ["rcon_port", "RCON_PORT"],
                    25574,
                ),
                25576,
            )
            self.assertEqual(
                self.helpers["config_str"](
                    [{"mcsm_chat_prefix": "   "}], ["mcsm_chat_prefix"], "#qq"
                ),
                "#qq",
            )


class PluginLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def running_task(self, cleanup):
        try:
            await asyncio.Event().wait()
        finally:
            cleanup()

    async def test_minecraft_task_cleanup_completes_before_terminate_returns(self):
        cleanup = Mock()
        task = asyncio.create_task(self.running_task(cleanup))
        await asyncio.sleep(0)
        owner = SimpleNamespace(
            mcsm_monitor_task=task,
            target_umo="group",
            target_group_id="123",
            bound_bot=Mock(),
        )
        terminate = load_method(
            Path("core") / "minecraft_manager.py", "MinecraftManager", "terminate"
        )
        await terminate(owner)
        cleanup.assert_called_once()
        self.assertTrue(task.done())
        self.assertIsNone(owner.mcsm_monitor_task)
        self.assertIsNone(owner.target_umo)
        self.assertIsNone(owner.target_group_id)
        self.assertIsNone(owner.bound_bot)
        await terminate(owner)

    async def test_verification_tasks_are_awaited_and_state_is_cleared(self):
        cleanup = Mock()
        running = asyncio.create_task(self.running_task(cleanup))
        await asyncio.sleep(0)
        not_started = asyncio.create_task(self.running_task(Mock()))
        owner = SimpleNamespace(
            pending={"1": {"task": running}, "2": {"task": not_started}}
        )
        terminate = load_method(
            Path("core") / "join_head.py", "QQGroupVerifyPlugin", "terminate"
        )
        await terminate(owner)
        cleanup.assert_called_once()
        self.assertTrue(running.done())
        self.assertTrue(not_started.done())
        self.assertEqual(owner.pending, {})
        await terminate(owner)

    async def test_main_cleans_both_modules_even_if_first_fails(self):
        join = SimpleNamespace(
            terminate=AsyncMock(side_effect=RuntimeError("cleanup failed"))
        )
        minecraft = SimpleNamespace(terminate=AsyncMock())
        owner = SimpleNamespace(join=join, minecraft=minecraft)
        terminate = load_method(Path("main.py"), "MyPlugin", "terminate")
        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            await terminate(owner)
        minecraft.terminate.assert_awaited_once()
        self.assertIsNone(owner.join)
        self.assertIsNone(owner.minecraft)
        await terminate(owner)


class PluginContractTests(unittest.TestCase):
    def test_entry_uses_injected_configuration_and_metadata(self):
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        cls = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MyPlugin"
        )
        self.assertEqual(cls.decorator_list, [])
        init = next(node for node in cls.body if node.name == "__init__")
        self.assertEqual(init.args.args[2].annotation.id, "AstrBotConfig")
        self.assertEqual(init.args.defaults, [])
        self.assertNotIn("get_config", (ROOT / "main.py").read_text(encoding="utf-8"))

    def test_metadata_preserves_identity_and_declares_actual_platform(self):
        metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
        self.assertIn("name: QQVerify\n", metadata)
        self.assertIn("author: SelfAbandonment\n", metadata)
        self.assertIn("repo: https://github.com/SelfAbandonment/qqban\n", metadata)
        self.assertIn("support_platforms:\n  - aiocqhttp", metadata)

    def test_config_options_include_existing_defaults(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        for key in ("verification_difficulty", "verification_message_mode"):
            self.assertIn(schema[key]["default"], schema[key]["options"])


if __name__ == "__main__":
    unittest.main()
