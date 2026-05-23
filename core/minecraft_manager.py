import asyncio
import json
import os
import struct
from typing import Any, Dict, Iterable, Optional, Tuple

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult
import astrbot.api.message_components as Comp
from astrbot.api.star import Context


SERVERDATA_AUTH = 3
SERVERDATA_EXECCOMMAND = 2


def _to_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, Iterable):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _unwrap_config_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return getattr(value, "value")
    return value


def _is_empty_config_value(value: Any) -> bool:
    return value is None or str(value).strip() in {"", "None", "null"}


def _config_get(config: Dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        value = None
        found = False

        if hasattr(config, "get"):
            value = config.get(key, None)
            found = value is not None

        if not found and isinstance(config, dict) and key in config:
            value = config[key]
            found = True

        if not found and hasattr(config, key):
            value = getattr(config, key)
            found = True

        value = _unwrap_config_value(value)
        if found and not _is_empty_config_value(value):
            return value

        env_value = os.getenv(key)
        if not _is_empty_config_value(env_value):
            return env_value

    return default


class MinecraftManager:
    def __init__(self, context: Context, config: Dict[str, Any]):
        self.context = context
        self.rcon_ip = str(_config_get(config, ["rcon_ip", "RCON_IP", "mc_rcon_ip"], "127.0.0.1"))
        self.rcon_port = int(_config_get(config, ["rcon_port", "RCON_PORT", "mc_rcon_port"], 25575))
        self.rcon_password = str(_config_get(config, ["rcon_password", "RCON_PASSWORD", "mc_rcon_password"], ""))
        self.rcon_timeout = float(_config_get(config, ["rcon_timeout", "RCON_TIMEOUT", "mc_rcon_timeout"], 5.0))
        self.admin_qq = set(_to_str_list(_config_get(config, ["mc_admin_qq", "ADMIN_QQ", "admin_qq"], [])))
        self.target_umo: Optional[str] = None
        logger.info(
            "[MC RCON] 配置状态: "
            f"ip={self.rcon_ip}, port={self.rcon_port}, "
            f"password={'已配置' if self.rcon_password else '未配置'}, "
            f"admin_count={len(self.admin_qq)}"
        )

    def is_admin(self, event: AstrMessageEvent) -> bool:
        try:
            return str(event.get_sender_id()) in self.admin_qq
        except Exception as exc:
            logger.error(f"[MC RCON] 权限检查失败: {exc}")
            return False

    def _build_rcon_packet(self, request_id: int, packet_type: int, payload: str) -> bytes:
        payload_bytes = payload.encode("utf-8") + b"\x00"
        size = 4 + 4 + len(payload_bytes) + 1
        return struct.pack(f"<iii{len(payload_bytes)}sb", size, request_id, packet_type, payload_bytes, 0)

    async def _read_rcon_response(self, reader: asyncio.StreamReader) -> Tuple[int, int, str]:
        size_bytes = await asyncio.wait_for(reader.readexactly(4), timeout=self.rcon_timeout)
        size = struct.unpack("<i", size_bytes)[0]
        if size > 4096:
            raise ValueError(f"RCON 包过大: {size}")

        remaining_bytes = await asyncio.wait_for(reader.readexactly(size), timeout=self.rcon_timeout)
        request_id, packet_type = struct.unpack("<ii", remaining_bytes[:8])
        payload = remaining_bytes[8:-2].decode("utf-8", errors="ignore")
        return request_id, packet_type, payload

    async def execute_rcon(self, command: str) -> Tuple[bool, str]:
        if not self.rcon_password:
            return False, "RCON 密码未配置，请检查 rcon_password 或 RCON_PASSWORD 配置后重载插件"

        writer: Optional[asyncio.StreamWriter] = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.rcon_ip, self.rcon_port),
                timeout=self.rcon_timeout,
            )

            writer.write(self._build_rcon_packet(1, SERVERDATA_AUTH, self.rcon_password))
            await writer.drain()

            auth_request_id, _, _ = await self._read_rcon_response(reader)
            if auth_request_id != 1:
                return False, "RCON 密码错误或认证失败"

            command_request_id = 300
            writer.write(self._build_rcon_packet(command_request_id, SERVERDATA_EXECCOMMAND, command))
            await writer.drain()

            response_request_id, _, payload = await self._read_rcon_response(reader)
            if response_request_id != command_request_id:
                return False, "RCON 响应异常"
            return True, payload
        except Exception as exc:
            logger.error(f"[MC RCON] 通信错误: {exc}")
            return False, str(exc)
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()

    async def send_to_mc(self, event: AstrMessageEvent, text: str) -> Optional[MessageEventResult]:
        self.target_umo = event.unified_msg_origin

        sender = event.get_sender_name()
        message = {
            "text": f"[Q群] {sender}: {text.replace(chr(10), ' ')}",
            "color": "#F99CAB",
            "italic": True,
        }
        command = f"tellraw @a {json.dumps(message, ensure_ascii=False)}"
        success, response = await self.execute_rcon(command)

        if not success:
            return MessageEventResult(chain=[Comp.Plain(f"发送失败：{response}")])

        try:
            group_id = event.get_group_id()
            bot = getattr(event, "bot", None)
            if group_id and bot:
                await bot.group_poke(
                    group_id=int(group_id),
                    user_id=int(event.get_sender_id()),
                    poke_type="ShowLove",
                )
                return None
        except Exception:
            pass

        return MessageEventResult(chain=[Comp.Plain("OK")])

    async def restart_mc_server(self, event: AstrMessageEvent) -> MessageEventResult:
        if not self.is_admin(event):
            return MessageEventResult(chain=[Comp.Plain("您没有权限执行此操作")])

        success, response = await self.execute_rcon("stop")
        if success:
            return MessageEventResult(chain=[Comp.Plain(f"已发送关闭指令 (stop)\n反馈: {response}")])
        return MessageEventResult(chain=[Comp.Plain(f"指令发送失败: {response}")])

    def account_info(self, event: AstrMessageEvent) -> MessageEventResult:
        qq_id = event.get_sender_id()
        is_admin = self.is_admin(event)
        result = MessageEventResult()
        result.chain = [
            Comp.Plain("=== 账户信息 ===\n"),
            Comp.Plain(f"QQ号: {qq_id}\n"),
            Comp.Plain(f"身份: {'管理员' if is_admin else '普通用户'}\n"),
            Comp.Plain(f"MC RCON: {'已配置' if self.rcon_password else '未配置'}\n"),
            Comp.Plain(f"当前群绑定状态: {'已绑定' if self.target_umo else '未绑定 (请发送 /tomc 激活)'}"),
        ]
        return result

    async def terminate(self):
        self.target_umo = None
        logger.info("[MC RCON] 模块已卸载")