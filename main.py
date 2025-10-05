from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from datetime import datetime
import json
import time

@register("GroupActivity", "AstrBot助手", "简化版群活跃度统计插件", "1.0.0")
class SimpleGroupActivityPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.storage_key = "simple_group_activity_data"
    
    async def initialize(self):
        """插件初始化"""
        logger.info("简化版群活跃度插件已加载")

    # 活跃度统计命令
    @filter.command("activity")
    async def activity_command(self, event: AstrMessageEvent):
        """查询群成员活跃度排名"""
        if not event.get_group():
            yield event.plain_result("此功能仅在群聊中可用")
            return
        
        group_id = event.get_group_id()
        activity_data = await self.get_activity_data(group_id)
        
        if not activity_data:
            yield event.plain_result("暂无活跃度数据")
            return
        
        result = self.generate_simple_ranking(activity_data)
        yield event.plain_result(result)

    # 个人活跃度查询
    @filter.command("myactivity")
    async def myactivity_command(self, event: AstrMessageEvent):
        """查询我的活跃度"""
        if not event.get_group():
            yield event.plain_result("此功能仅在群聊中可用")
            return
        
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        
        activity_data = await self.get_activity_data(group_id)
        if not activity_data or user_id not in activity_data["members"]:
            yield event.plain_result("暂无你的活跃度数据")
            return
        
        member_data = activity_data["members"][user_id]
        result = self.format_simple_stats(member_data, event.sender.name)
        yield event.plain_result(result)

    # 消息事件处理
    @filter.message()
    async def handle_message(self, event: AstrMessageEvent):
        """处理消息事件"""
        if not event.get_group():
            return

        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        user_name = event.get_sender_name() or str(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        
        activity_data = await self.get_activity_data(group_id, create_if_missing=True)
        
        # 初始化成员数据
        if user_id not in activity_data["members"]:
            activity_data["members"][user_id] = {
                "name": user_name,
                "total": 0,
                "today": 0,
                "last_date": today
            }
        
        member = activity_data["members"][user_id]
        
        # 如果是新的一天，重置今日计数
        if member["last_date"] != today:
            member["today"] = 0
            member["last_date"] = today
        
        # 更新计数
        member["total"] += 1
        member["today"] += 1
        member["name"] = user_name  # 更新昵称
        
        # 保存数据
        await self.save_activity_data(activity_data)

    # ===== 简化的辅助方法 =====
    
    async def get_activity_data(self, group_id: str, create_if_missing: bool = False) -> dict:
        """获取活跃度数据"""
        data_str = await self.context.storage.get(self.storage_key)
        all_data = json.loads(data_str) if data_str else {}
        
        if group_id not in all_data and create_if_missing:
            all_data[group_id] = {"members": {}}
            await self.save_all_data(all_data)
        
        return all_data.get(group_id, {})
    
    async def save_activity_data(self, activity_data: dict):
        """保存活跃度数据"""
        # 简化的保存逻辑，实际使用时需要更完整的实现
        data_str = await self.context.storage.get(self.storage_key)
        all_data = json.loads(data_str) if data_str else {}
        
        # 找到对应的group_id并更新
        for gid in all_data:
            if gid == activity_data.get("group_id", ""):
                all_data[gid] = activity_data
                break
        
        await self.save_all_data(all_data)
    
    async def save_all_data(self, all_data: dict):
        """保存所有数据"""
        await self.context.storage.set(self.storage_key, json.dumps(all_data))

    def generate_simple_ranking(self, activity_data: dict) -> str:
        """生成简化的活跃度排名"""
        members = list(activity_data["members"].items())
        
        # 按总发言数排序
        sorted_members = sorted(members, key=lambda x: x[1]["total"], reverse=True)
        
        result = "📊 群活跃度排名（总发言数）\n\n"
        
        for i, (data) in enumerate(sorted_members[:10]):  # 只显示前10名
            result += f"{i+1}. {data['name']} - {data['total']}条\n"
        
        # 添加今日活跃度提示
        today_active = sum(1 for _, data in members if data["today"] > 0)
        result += f"\n今日活跃成员: {today_active}人"
        
        return result
    
    def format_simple_stats(self, member_data: dict, user_name: str) -> str:
        """格式化简化的成员统计信息"""
        return (
            f"👤 {user_name} 的活跃度：\n"
            f"💬 今日发言: {member_data['today']} 次\n"
            f"📅 最后发言: {member_data['last_date']}\n"
            f"🏆 总发言数: {member_data['total']} 次"
        )