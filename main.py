from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from .core.join_head import QQGroupVerifyPlugin
from .core.minecraft_manager import MinecraftManager

@register("QQVerify", "SelfAbandonmen", "群成员动态验证插件", "0.0.2", "repo url")
class MyPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config
        self.join = None
        self.minecraft = None

    def _load_config(self):
        if self.config is not None:
            return self.config
        get_config = getattr(self.context, 'get_config', None)
        if get_config:
            return get_config()
        return {}
    
    async def initialize(self):
        config = self._load_config()
        self.join = QQGroupVerifyPlugin(self.context,config)
        self.minecraft = MinecraftManager(self.context, config)
        
        initialize = getattr(self.join, 'initialize', None)
        if initialize:
            await initialize()

    async def terminate(self):
        if self.join and hasattr(self.join, 'terminate'):
            await self.join.terminate()
        self.join = None
        if self.minecraft and hasattr(self.minecraft, 'terminate'):
            await self.minecraft.terminate()
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
        if self.minecraft:
            text = event.message_str.strip() if event.message_str else ""
            is_mc_reply = await self.minecraft.handle_qq_reply(event, text)
            if is_mc_reply:
                return

        if self.join:
            await self.join.handle_event(event)

        if self.join:
            await self.join.handle_event(event)
