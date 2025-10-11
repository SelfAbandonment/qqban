from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from .core.join_head import QQGroupVerifyPlugin

@register("QQVerify", "SelfAbandonmen", "群成员动态验证插件", "0.0.2", "repo url")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.join = None
    
    async def initialize(self):
        config = self.context.get_config()
        self.join = QQGroupVerifyPlugin(self.context,config)
        
        if hasattr(self.join, 'initialize'):
            await self.join.initialize()

    async def terminate(self):
        # 清理资源
        if self.join and hasattr(self.join, 'terminate'):
            await self.join.terminate()
        self.join = None
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_event(self, event: AstrMessageEvent):
        """监听入群并且下发数字动态验证"""
        if self.join:
            await self.join.handle_event(event)