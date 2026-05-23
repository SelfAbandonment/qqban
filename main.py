from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from .core.join_head import QQGroupVerifyPlugin
from .core.minecraft_manager import MinecraftManager

@register("QQVerify", "SelfAbandonmen", "群成员动态验证插件", "0.0.2", "repo url")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.join = None
        self.minecraft = None

    def _load_config(self):
        return self.context.get_config()
    
    async def initialize(self):
        config = self._load_config()
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

    @filter.command("qqverify_reload")
    async def reload_plugin_config(self, event: AstrMessageEvent):
        """重新读取插件配置。"""
        if self.minecraft and self.minecraft.admin_qq and not self.minecraft.is_admin(event):
            yield MessageEventResult(chain=[Comp.Plain("您没有权限执行此操作")])
            return

        config = self._load_config()
        if self.join and hasattr(self.join, 'reload_config'):
            self.join.reload_config(config)
        if self.minecraft and hasattr(self.minecraft, 'reload_config'):
            self.minecraft.reload_config(config)
        yield MessageEventResult(chain=[Comp.Plain("QQVerify 配置已重新读取")])

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_event(self, event: AstrMessageEvent):
        """监听入群并且下发数字动态验证"""
        if self.join:
            await self.join.handle_event(event)