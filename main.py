from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from datetime import datetime, timedelta
import json
import re
import asyncio
import time
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from enum import Enum

@register("GroupActivity", "AstrBot助手", "群成员活跃度统计与监控插件", "1.1.0")
class GroupActivityPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.storage_key = "group_activity_data"
        self.notification_key = "activity_notification_data"
        
        # 监控配置
        self.monitor_config = {
            'inactive_threshold': 7,  # 不活跃阈值（天）
            'check_interval': 24 * 3600,  # 检查间隔（秒）- 24小时
            'notify_cooldown': 3,  # 通知冷却时间（天）
            'enable_monitoring': True,  # 启用监控
        }
    
    async def initialize(self):
        """插件初始化"""
        logger.info("群活跃度统计与监控插件已加载")
        
        # 启动监控任务
        if self.monitor_config['enable_monitoring']:
            asyncio.create_task(self.monitor_inactive_users())
    
    async def terminate(self):
        """插件销毁"""
        logger.info("群活跃度统计与监控插件已卸载")

    # ===== 使用正确的事件过滤器 =====

    # 活跃度统计命令 - 只在群聊中响应
    @filter.command("activity")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def activity_command(self, event: AstrMessageEvent):
        """查询群成员活跃度排名"""
        group_id = event.get_group_id
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

    # 个人活跃度查询 - 只在群聊中响应
    @filter.command("myactivity")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def myactivity_command(self, event: AstrMessageEvent):
        """查询我的活跃度"""
        group_id = event.group.id
        user_id = event.sender.id
        
        activity_data = await self.get_activity_data(group_id)
        if not activity_data or user_id not in activity_data["members"]:
            yield event.plain_result("暂无你的活跃度数据")
            return
        
        member_data = activity_data["members"][user_id]
        result = self.format_member_stats(member_data, event.sender.name)
        yield event.plain_result(result)

    # 清空数据命令 - 只在群聊中响应
    @filter.command("cleardata")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
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
        await self.context.storage.delete(self.notification_key)
        yield event.plain_result("活跃度数据已清空")

    # 监控配置命令 - 只在群聊中响应
    @filter.command("monitor_config")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def monitor_config_command(self, event: AstrMessageEvent):
        """查看或设置监控配置（管理员）"""
        if not await self.is_admin(event):
            yield event.plain_result("需要管理员权限")
            return
        
        args = event.message_str.split()[1:]
        
        if not args:
            # 显示当前配置
            config_text = "📊 活跃度监控配置：\n"
            for key, value in self.monitor_config.items():
                config_text += f"{key}: {value}\n"
            config_text += "\n使用 /monitor_config set <参数> <值> 修改配置"
            yield event.plain_result(config_text)
            return
        
        if args[0] == "set" and len(args) >= 3:
            param = args[1]
            value = args[2]
            
            if param in self.monitor_config:
                # 类型转换
                if isinstance(self.monitor_config[param], bool):
                    self.monitor_config[param] = value.lower() in ["true", "1", "yes", "on"]
                elif isinstance(self.monitor_config[param], int):
                    self.monitor_config[param] = int(value)
                else:
                    self.monitor_config[param] = value
                
                yield event.plain_result(f"✅ 已更新 {param} = {self.monitor_config[param]}")
            else:
                yield event.plain_result(f"❌ 未知参数: {param}")

    # 消息事件处理 - 只处理群聊消息
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_group_message(self, event: AstrMessageEvent):
        """处理群消息事件"""
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
                "last_timestamp": time.time(),  # 新增时间戳
                "join_date": today
            }
        
        member = activity_data["members"][user_id]
        
        # 如果是新的一天，重置今日计数
        if member["last_date"] != today:
            member["today"] = 0
            member["last_date"] = today
        
        # 更新计数和时间戳
        member["total"] += 1
        member["today"] += 1
        member["last_timestamp"] = time.time()  # 更新最后活跃时间戳
        member["name"] = user_name  # 更新昵称
        
        # 保存数据
        await self.save_activity_data(activity_data)
        
        # 里程碑检查（可选）
        await self.check_milestones(event, member, user_id)

    # ===== 监控功能 =====

    async def monitor_inactive_users(self):
        """监控不活跃用户并发送通知"""
        while True:
            try:
                if self.monitor_config['enable_monitoring']:
                    await self.check_and_notify_inactive_users()
                await asyncio.sleep(self.monitor_config['check_interval'])
            except Exception as e:
                logger.error(f"监控任务出错: {e}")
                await asyncio.sleep(3600)  # 出错后1小时重试

    async def check_and_notify_inactive_users(self):
        """检查并通知不活跃用户"""
        try:
            # 获取所有群数据
            data_str = await self.context.storage.get(self.storage_key)
            if not data_str:
                return
                
            all_data = json.loads(data_str)
            current_time = time.time()
            inactive_threshold = self.monitor_config['inactive_threshold'] * 24 * 3600
            
            # 获取通知记录
            notification_data = await self.get_notification_data()
            
            for group_id, activity_data in all_data.items():
                if "members" not in activity_data:
                    continue
                    
                for user_id, member_data in activity_data["members"].items():
                    last_active = member_data.get("last_timestamp", 0)
                    if last_active == 0:
                        continue
                    
                    # 计算不活跃天数
                    inactive_days = (current_time - last_active) / (24 * 3600)
                    
                    if inactive_days >= self.monitor_config['inactive_threshold']:
                        # 检查通知冷却
                        last_notified = self.get_last_notification(notification_data, group_id, user_id)
                        if last_notified and (current_time - last_notified) < self.monitor_config['notify_cooldown'] * 24 * 3600:
                            continue
                            
                        # 发送通知
                        await self.send_inactive_notification(user_id, int(inactive_days), member_data["name"])
                        
                        # 记录通知时间
                        self.record_notification(notification_data, group_id, user_id, current_time)
                        logger.info(f"发送不活跃通知: 群{group_id} 用户{user_id} 不活跃{int(inactive_days)}天")
            
            # 保存通知记录
            await self.save_notification_data(notification_data)
            
        except Exception as e:
            logger.error(f"检查不活跃用户失败: {e}")

    async def send_inactive_notification(self, user_id: str, inactive_days: int, user_name: str):
        """发送不活跃通知私聊"""
        try:
            # 生成个性化的通知消息
            notification_msg = self.generate_notification_message(inactive_days, user_name)
            
            # 这里需要根据AstrBot的实际API实现私聊发送
            # 示例：await self.context.bot.send_private_msg(user_id=user_id, message=notification_msg)
            
            # 临时使用日志记录代替实际发送
            logger.info(f"【私聊通知】用户{user_id}({user_name}): {notification_msg}")
            
        except Exception as e:
            logger.error(f"发送私聊通知失败: {e}")

    def generate_notification_message(self, inactive_days: int, user_name: str) -> str:
        """生成不活跃通知消息"""
        if inactive_days <= 7:
            return (
                f"👋 {user_name}，好久不见！\n"
                f"注意到您已经{inactive_days}天没有在群里发言了。\n"
                f"快来群里和大家打个招呼吧，大家都想您了！💝"
            )
        elif inactive_days <= 14:
            return (
                f"🌻 {user_name}，想念您的发言！\n"
                f"您已经{inactive_days}天没有在群里活跃了。\n"
                f"群里最近有很多有趣的讨论，快来参与吧！✨"
            )
        else:
            return (
                f"🌟 {user_name}，特别提醒！\n"
                f"您已经{inactive_days}天没有在群里发言了。\n"
                f"我们很重视每一位成员，希望您能继续参与群内交流。\n"
                f"如果有任何问题或建议，也欢迎随时提出！🤗"
            )

    # ===== 数据存储辅助方法 =====

    async def get_notification_data(self) -> dict:
        """获取通知记录数据"""
        data_str = await self.context.storage.get(self.notification_key)
        return json.loads(data_str) if data_str else {}

    async def save_notification_data(self, data: dict):
        """保存通知记录数据"""
        await self.context.storage.set(self.notification_key, json.dumps(data))

    def get_last_notification(self, notification_data: dict, group_id: str, user_id: str) -> float:
        """获取上次通知时间"""
        if group_id in notification_data and user_id in notification_data[group_id]:
            return notification_data[group_id][user_id]
        return 0

    def record_notification(self, notification_data: dict, group_id: str, user_id: str, timestamp: float):
        """记录通知时间"""
        if group_id not in notification_data:
            notification_data[group_id] = {}
        notification_data[group_id][user_id] = timestamp

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
        data_str = await self.context.storage.get(self.storage_key)
        all_data = json.loads(data_str) if data_str else {}
        
        # 找到对应的group_id
        for gid, data in all_data.items():
            if data.get("members") == activity_data.get("members"):
                all_data[gid] = activity_data
                break
        
        await self.save_all_data(all_data)
    
    async def save_all_data(self, all_data: dict):
        """保存所有群的活跃度数据"""
        await self.context.storage.set(self.storage_key, json.dumps(all_data))

    # ===== 统计和展示方法 =====

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
        # 计算不活跃天数
        last_active = member_data.get("last_timestamp", 0)
        inactive_days = 0
        if last_active > 0:
            inactive_days = int((time.time() - last_active) / (24 * 3600))
        
        status_emoji = "🎉" if inactive_days == 0 else "👍" if inactive_days < 3 else "💤"
        
        return (
            f"👤 {user_name} 的活跃度统计：\n"
            f"{status_emoji} 状态: {'今日活跃' if inactive_days == 0 else f'{inactive_days}天未发言'}\n"
            f"💬 今日发言: {member_data['today']} 次\n"
            f"📅 最后发言: {member_data['last_date']}\n"
            f"⏰ 加入群聊: {member_data['join_date']}\n"
            f"🏆 总发言数: {member_data['total']} 次"
        )
    
    async def is_admin(self, event: AstrMessageEvent) -> bool:
        """检查是否是管理员"""
        # 根据实际平台API调整
        return hasattr(event.sender, 'role') and event.sender.role in ["admin", "owner"]
    
    async def check_milestones(self, event: AstrMessageEvent, member_data: dict, user_id: str):
        """检查里程碑"""
        milestones = [10, 50, 100, 500, 1000]
        if member_data["total"] in milestones:
            await event.reply(f"🎉 恭喜 {member_data['name']} 发言次数达到 {member_data['total']} 次！")

    # ===== 时间处理辅助方法 =====

    def is_this_week(self, date_str: str) -> bool:
        """检查日期是否在本周"""
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            now = datetime.now()
            start_of_week = now - timedelta(days=now.weekday())
            return date >= start_of_week
        except:
            return False
    
    def is_this_month(self, date_str: str) -> bool:
        """检查日期是否在本月"""
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            now = datetime.now()
            return date.year == now.year and date.month == now.month
        except:
            return False
    
    def get_this_week_count(self, member_data: dict) -> int:
        """获取本周发言次数（简化实现）"""
        # 实际实现需要更复杂的逻辑
        return member_data.get("today", 0)
    
    def get_this_month_count(self, member_data: dict) -> int:
        """获取本月发言次数（简化实现）"""
        # 实际实现需要更复杂的逻辑
        return member_data.get("today", 0)