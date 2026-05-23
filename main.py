from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from .core.join_head import QQGroupVerifyPlugin
from .core.minecraft_manager import MinecraftManager

@register("QQVerify", "SelfAbandonmen", "群成员动态验证插件", "0.0.2", "repo url")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.join = None
        self.minecraft = None
    
    async def initialize(self):
        config = self.context.get_config()
        self.join = QQGroupVerifyPlugin(self.context,config)
        self.minecraft = MinecraftManager(self.context, config)
        
        initialize = getattr(self.join, 'initialize', None)
        if initialize:
            await initialize()

    async def terminate(self):
        # 清理资源
        if self.join and hasattr(self.join, 'terminate'):
            await self.join.terminate()
        self.join = None
        if self.minecraft and hasattr(self.minecraft, 'terminate'):
            await self.minecraft.terminate()
        self.minecraft = None

    @filter.command("tomc")
    async def tomc_command(self, event: AstrMessageEvent, text: str):
        """发送消息到 MC。"""
        if self.minecraft:
            result = await self.minecraft.send_to_mc(event, text)
            if result:
                yield result

    @filter.command("mcrestart")
    async def restart_mc_server(self, event: AstrMessageEvent):
        """通过 RCON 关闭 MC 服务端。"""
        if self.minecraft:
            yield await self.minecraft.restart_mc_server(event)

    @filter.command("myid")
    async def show_my_id(self, event: AstrMessageEvent):
        """显示账户信息。"""
        if self.minecraft:
            yield self.minecraft.account_info(event)

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_event(self, event: AstrMessageEvent):
        """监听入群并且下发数字动态验证"""
        if self.join:
            await self.join.handle_event(event)