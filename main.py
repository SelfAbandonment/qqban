from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from datetime import datetime, timedelta
import json
import re

@register("GroupActivity", "AstrBot助手", "群成员活跃度统计插件", "1.0.0")
class GroupActivityPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.storage_key = "group_activity_data"
    
    async def initialize(self):
        """插件初始化"""
        logger.info("群活跃度统计插件已加载")
    
    async def terminate(self):
        """插件销毁"""
        logger.info("群活跃度统计插件已卸载")

    # 活跃度统计命令
    @filter.command("activity")
    async def activity_command(self, event: AstrMessageEvent):
        """查询群成员活跃度排名"""
        if not event.group:
            yield event.plain_result("此功能仅在群聊中可用")
            return
        
        group_id = event.group.id
        args = event.message_str.split()[1:]  # 获取命令参数
        
        period = "今日"
        page = 1
        
        if args:
            if args[0] in ["今日", "本周", "本月", "全部"]:
                period = args[0]
            if len(args) > 1 and args[1].isdigit():
                page = int(args[1])
        
        activity_data = await self.get_activity_data(group_id)
        if not activity_data:
            yield event.plain_result("暂无活跃度数据")
            return
        
        result = self.generate_ranking(activity_data, period, page)
        yield event.plain_result(result)

    # 个人活跃度查询
    @filter.command("myactivity")
    async def myactivity_command(self, event: AstrMessageEvent):
        """查询我的活跃度"""
        if not event.group:
            yield event.plain_result("此功能仅在群聊中可用")
            return
        
        group_id = event.group.id
        user_id = event.sender.id
        
        activity_data = await self.get_activity_data(group_id)
        if not activity_data or user_id not in activity_data["members"]:
            yield event.plain_result("暂无你的活跃度数据")
            return
        
        member_data = activity_data["members"][user_id]
        result = self.format_member_stats(member_data, event.sender.name)
        yield event.plain_result(result)

    # 清空数据命令（管理员）
    @filter.command("cleardata")
    async def cleardata_command(self, event: AstrMessageEvent):
        """清空活跃度数据（管理员）"""
        if not await self.is_admin(event):
            yield event.plain_result("需要管理员权限才能执行此操作")
            return
        
        args = event.message_str.split()[1:]
        if not args or args[0] != "confirm":
            yield event.plain_result("确认清空所有活跃度数据？此操作不可逆！请使用 /cleardata confirm")
            return
        
        await self.context.storage.delete(self.storage_key)
        yield event.plain_result("活跃度数据已清空")

    # 消息事件处理 - 使用更通用的消息过滤器
    @filter.message()
    async def handle_message(self, event: AstrMessageEvent):
        """处理消息事件"""
        # 只在群聊中记录
        if not event.group:
            return

        group_id = event.group.id
        user_id = event.sender.id
        user_name = event.sender.name or str(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        
        activity_data = await self.get_activity_data(group_id, create_if_missing=True)
        
        # 初始化成员数据
        if user_id not in activity_data["members"]:
            activity_data["members"][user_id] = {
                "name": user_name,
                "total": 0,
                "today": 0,
                "last_date": today,
                "join_date": today
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
        
        # 里程碑检查（可选）
        await self.check_milestones(event, member, user_id)

    # 群成员加入事件 - 使用成员加入过滤器
    @filter.member_join()
    async def handle_member_join(self, event: AstrMessageEvent):
        """处理新成员加入事件"""
        if not event.group:
            return
            
        group_id = event.group.id
        user_id = event.sender.id
        user_name = event.sender.name or str(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        
        activity_data = await self.get_activity_data(group_id, create_if_missing=True)
        
        # 添加新成员
        activity_data["members"][user_id] = {
            "name": user_name,
            "total": 0,
            "today": 0,
            "last_date": today,
            "join_date": today
        }
        
        await self.save_activity_data(activity_data)

    # ===== 辅助方法 =====
    
    async def get_activity_data(self, group_id: str, create_if_missing: bool = False) -> dict:
        """获取活跃度数据"""
        data_str = await self.context.storage.get(self.storage_key)
        all_data = json.loads(data_str) if data_str else {}
        
        if group_id not in all_data and create_if_missing:
            all_data[group_id] = {
                "members": {},
                "group_name": f"群{group_id}"
            }
            await self.save_all_data(all_data)
        
        return all_data.get(group_id, {})
    
    async def save_activity_data(self, activity_data: dict):
        """保存单个群的活跃度数据"""
        # 需要先获取所有数据，更新后再保存
        data_str = await self.context.storage.get(self.storage_key)
        all_data = json.loads(data_str) if data_str else {}
        
        # 更新group_name（如果群名发生变化）
        if activity_data.get("members"):
            # 假设第一个成员的数据中有群ID
            group_id = next(iter(activity_data["members"].values()))["group_id"]
            all_data[group_id] = activity_data
        
        await self.save_all_data(all_data)
    
    async def save_all_data(self, all_data: dict):
        """保存所有群的活跃度数据"""
        await self.context.storage.set(self.storage_key, json.dumps(all_data))
    
    def generate_ranking(self, activity_data: dict, period: str, page: int) -> str:
        """生成活跃度排名"""
        members = list(activity_data["members"].items())
        page_size = 10
        start_index = (page - 1) * page_size
        
        # 根据周期筛选和排序
        filtered_members = []
        for user_id, data in members:
            if period == "今日" and data["today"] > 0:
                filtered_members.append((user_id, data))
            elif period == "本周" and self.is_this_week(data["last_date"]):
                filtered_members.append((user_id, data))
            elif period == "本月" and self.is_this_month(data["last_date"]):
                filtered_members.append((user_id, data))
            elif period == "全部":
                filtered_members.append((user_id, data))
        
        # 排序
        filtered_members.sort(key=lambda x: self.get_count_by_period(x[1], period), reverse=True)
        
        if not filtered_members:
            return f"暂无{period}活跃度数据"
        
        # 分页
        page_members = filtered_members[start_index:start_index + page_size]
        total_pages = (len(filtered_members) + page_size - 1) // page_size
        
        result = f"📊 {activity_data.get('group_name', '未知群')} {period}活跃度排名\n"
        result += f"📅 统计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        for i, (user_id, data) in enumerate(page_members):
            rank = start_index + i + 1
            count = self.get_count_by_period(data, period)
            result += f"{rank}. {data['name']} - {count}条\n"
        
        if total_pages > 1:
            result += f"\n第{page}页/共{total_pages}页，使用 /activity {period} {page + 1} 查看下一页"
        
        return result
    
    def get_count_by_period(self, member_data: dict, period: str) -> int:
        """根据周期获取计数"""
        if period == "今日":
            return member_data["today"]
        elif period == "本周":
            return self.get_this_week_count(member_data)
        elif period == "本月":
            return self.get_this_month_count(member_data)
        else:
            return member_data["total"]
    
    def format_member_stats(self, member_data: dict, user_name: str) -> str:
        """格式化成员统计信息"""
        return (
            f"👤 {user_name} 的活跃度统计：\n"
            f"💬 今日发言: {member_data['today']} 次\n"
            f"📅 最后发言: {member_data['last_date']}\n"
            f"⏰ 加入群聊: {member_data['join_date']}\n"
            f"🏆 总发言数: {member_data['total']} 次"
        )
    
    async def is_admin(self, event: AstrMessageEvent) -> bool:
        """检查是否是管理员"""
        # 根据实际平台API调整
        return event.sender.role in ["admin", "owner"]
    
    async def check_milestones(self, event: AstrMessageEvent, member_data: dict, user_id: str):
        """检查里程碑"""
        milestones = [10, 50, 100, 500, 1000]
        if member_data["total"] in milestones:
            await event.reply(f"🎉 恭喜 {member_data['name']} 发言次数达到 {member_data['total']} 次！")
    
    # 时间处理辅助方法
    def is_this_week(self, date_str: str) -> bool:
        """检查日期是否在本周"""
        date = datetime.strptime(date_str, "%Y-%m-%d")
        now = datetime.now()
        start_of_week = now - timedelta(days=now.weekday())
        return date >= start_of_week
    
    def is_this_month(self, date_str: str) -> bool:
        """检查日期是否在本月"""
        date = datetime.strptime(date_str, "%Y-%m-%d")
        now = datetime.now()
        return date.year == now.year and date.month == now.month
    
    def get_this_week_count(self, member_data: dict) -> int:
        """获取本周发言次数（简化实现）"""
        # 实际实现需要更复杂的逻辑
        return member_data["today"]  # 简化处理
    
    def get_this_month_count(self, member_data: dict) -> int:
        """获取本月发言次数（简化实现）"""
        # 实际实现需要更复杂的逻辑
        return member_data["today"]  # 简化处理