from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .core.join_head import QQGroupVerifyPlugin
from .core.minecraft_manager import MinecraftManager


class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.join = None
        self.minecraft = None

    async def initialize(self):
        self.join = QQGroupVerifyPlugin(self.context, self.config)
        self.minecraft = MinecraftManager(self.context, self.config)

    async def terminate(self):
        try:
            if self.join:
                await self.join.terminate()
        finally:
            self.join = None
            try:
                if self.minecraft:
                    await self.minecraft.terminate()
            finally:
                self.minecraft = None

    @filter.command("tomc")
    async def tomc_command(self, event: AstrMessageEvent, text: str):
        """发送消息到 MC。"""
        event.stop_event()
        if self.minecraft:
            result = await self.minecraft.send_to_mc(event, text)
            if result:
                yield result

    @filter.command("mcrestart")
    async def restart_mc_server(self, event: AstrMessageEvent):
        """通过 RCON 关闭 MC 服务端。"""
        event.stop_event()
        if self.minecraft:
            yield await self.minecraft.restart_mc_server(event)

    @filter.command("myid")
    async def show_my_id(self, event: AstrMessageEvent):
        """显示账户信息。"""
        event.stop_event()
        if self.minecraft:
            yield self.minecraft.account_info(event)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_event(self, event: AstrMessageEvent):
        """监听入群并且下发数字动态验证"""
        if self.join:
            await self.join.handle_event(event)
