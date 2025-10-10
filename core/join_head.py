import asyncio
import random
import re
from typing import Dict, Any, Tuple
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context


def _safe_format(template: str, **kwargs: Any) -> str:
    """
    使用格式化字符串。
    """
    class SafeDict(dict):
        def __missing__(self, key):
            return f'{{{key}}}'

    return template.format_map(SafeDict(kwargs))


class QQGroupVerifyPlugin:
    def __init__(self, context: Context, config: Dict[str, Any]):
        self.context = context
        self.config = config

        # --- 时间控制 ---
        self.verification_timeout = config.get("verification_timeout", 120)
        self.kick_countdown_warning_time = config.get("kick_countdown_warning_time", 15)
        self.kick_delay = config.get("kick_delay", 5)

        #消息模板模板 ---
        self.new_member_prompt = config.get(
            "new_member_prompt",
            "{at_user} 欢迎加入本群！请在 {timeout} 分钟内@我并回答下面的问题以完成验证：\n{question}"
        )
        self.welcome_message = config.get(
            "welcome_message",
            "{at_user} 验证成功，欢迎你的加入！\n1.请仔细阅读群公告\n2.群文件下载整合包自带IP\n3.白名单添加，群聊发送指令 “/绑定 您的ID”\n最后祝您玩得愉快"
        )
        self.wrong_answer_prompt = config.get(
            "wrong_answer_prompt",
            "{at_user} 答案错误，请重新回答验证。这是你的新问题：\n{question}"
        )
        self.countdown_warning_prompt = config.get(
            "countdown_warning_prompt",
            "{at_user} 验证即将超时，请尽快查看我的验证消息进行人机验证！"
        )
        self.failure_message = config.get(
            "failure_message",
            "{at_user} 验证超时，你将在 {countdown} 秒后被请出本群。"
        )
        self.kick_message = config.get(
            "kick_message",
            "{at_user} 因未在规定时间内完成验证，已被请出本群。"
        )
        self.pending: Dict[str, Dict[str, Any]] = {}

    def _generate_math_problem(self) -> Tuple[str, int]:
        """动态数学问题"""
        problem_type = random.choice(['addition', 'subtraction', 'multiplication', 'division', 'sequence'])
        
        if problem_type == 'addition':
            # 加法问题
            num1 = random.randint(100, 200)
            num2 = random.randint(10, 200)
            answer = num1 + num2
            question = f"{num1} + {num2} = ?"
            return question, answer
            
        elif problem_type == 'subtraction':
            # 减法问题
            num1 = random.randint(20, 100)
            num2 = random.randint(10, num1)
            answer = num1 - num2
            question = f"{num1} - {num2} = ?"
            return question, answer
            
        elif problem_type == 'multiplication':
            # 乘法问题
            num1 = random.randint(20, 100)
            num2 = random.randint(50, 100)
            answer = num1 * num2
            question = f"{num1} × {num2} = ?"
            return question, answer
            
        elif problem_type == 'division':
            # 整除法问题
            divisor = random.randint(2, 10)
            quotient = random.randint(3, 15)
            dividend = divisor * quotient
            answer = quotient
            question = f"{dividend} ÷ {divisor} = ?"
            return question, answer
            
        else:
            # 隐藏数列问题
            start = random.randint(1, 10)
            step = random.randint(2, 5)
            length = random.randint(4, 6)
            
            # 隐藏其中一个
            sequence = [start + i * step for i in range(length)]
            hidden_index = random.randint(1, length - 2)
            hidden_value = sequence[hidden_index]
            
            # 构建问题字符串
            seq_str = ""
            for i, num in enumerate(sequence):
                if i == hidden_index:
                    seq_str += "?, "
                else:
                    seq_str += f"{num}, "
            
            question = f"找出数列中的缺失数字：{seq_str.rstrip(', ')}"
            answer = hidden_value
            return question, answer

    async def handle_event(self, event: AstrMessageEvent):
        raw = event.message_obj.raw_message
        post_type = raw.get("post_type")

        if post_type == "notice":
            if raw.get("notice_type") == "group_increase":
                await self._process_new_member(event)
            elif raw.get("notice_type") == "group_decrease":
                await self._process_member_decrease(event)
        
        elif post_type == "message" and raw.get("message_type") == "group":
            await self._process_verification_message(event)

    async def _process_new_member(self, event: AstrMessageEvent):
        """处理新成员入群"""
        raw = event.message_obj.raw_message
        uid = str(raw.get("user_id"))
        gid = raw.get("group_id")
        await self._start_verification_process(event, uid, gid, is_new_member=True)

    async def _start_verification_process(self, event: AstrMessageEvent, uid: str, gid: int, is_new_member: bool):
        """为用户启动或重启验证流程"""
        if uid in self.pending:
            old_task = self.pending[uid].get("task")
            if old_task and not old_task.done():
                old_task.cancel()

        question, answer = self._generate_math_problem()
        logger.info(f"[QQ Verify] 为用户 {uid} 在群 {gid} 生成验证问题: {question} (答案: {answer})")

        nickname = uid
        try:
            user_info = await event.bot.api.call_action("get_group_member_info", group_id=gid, user_id=int(uid))
            nickname = user_info.get("card", "") or user_info.get("nickname", uid)
        except Exception as e:
            logger.warning(f"[QQ Verify] 获取用户 {uid} 昵称失败: {e}")

        task = asyncio.create_task(self._timeout_kick(event.bot, uid, gid, nickname))
        self.pending[uid] = {"gid": gid, "answer": answer, "task": task}

        at_user = f"[CQ:at,qq={uid}]"
        
        format_args = {
            "at_user": at_user,
            "member_name": nickname,
            "question": question,
            "timeout": self.verification_timeout // 60,
            "countdown": self.kick_delay
        }
        
        if is_new_member:
            prompt_message = _safe_format(self.new_member_prompt, **format_args)
        else:
            prompt_message = _safe_format(self.wrong_answer_prompt, **format_args)

        await event.bot.api.call_action("send_group_msg", group_id=gid, message=prompt_message)

    async def _process_verification_message(self, event: AstrMessageEvent):
        """处理群消息以进行验证"""
        uid = str(event.get_sender_id())
        if uid not in self.pending:
            return
        
        raw = event.message_obj.raw_message
        gid = self.pending[uid]["gid"]

        bot_id = str(event.get_self_id())
        message_segs = raw.get("message", [])
        if not isinstance(message_segs, list):
            return

        at_me = any(seg.get("type") == "at" and str(seg.get("data", {}).get("qq")) == bot_id for seg in message_segs)

        if not at_me:
            return
        
        text_without_at = re.sub(r'\[CQ:at,qq=\d+\]', '', event.message_str).strip()
        numbers_found = re.findall(r'\d+', text_without_at)
        
        if not numbers_found:
            return

        try:
            user_answer = int(numbers_found[-1])
        except (ValueError, TypeError):
            return

        correct_answer = self.pending[uid].get("answer")

        if user_answer == correct_answer:
            logger.info(f"[QQ Verify] 用户 {uid} 在群 {gid} 验证成功。")
            self.pending[uid]["task"].cancel()
            self.pending.pop(uid, None)

            nickname = raw.get("sender", {}).get("card", "") or raw.get("sender", {}).get("nickname", uid)
            
            welcome_msg = _safe_format(
                self.welcome_message, 
                at_user=f"[CQ:at,qq={uid}]", 
                member_name=nickname
            )
            await event.bot.api.call_action("send_group_msg", group_id=gid, message=welcome_msg)
            event.stop_event()
        else:
            logger.info(f"[QQ Verify] 用户 {uid} 在群 {gid} 回答错误。重新生成问题。")
            await self._start_verification_process(event, uid, gid, is_new_member=False)
            event.stop_event()

    async def _process_member_decrease(self, event: AstrMessageEvent):
        """处理成员离开"""
        uid = str(event.message_obj.raw_message.get("user_id"))
        if uid in self.pending:
            self.pending[uid]["task"].cancel()
            self.pending.pop(uid, None)
            logger.info(f"[QQ Verify] 待验证用户 {uid} 已离开，清理其验证状态。")

    # 移除了对 Bot 的类型提示，以确保兼容性
    async def _timeout_kick(self, bot, uid: str, gid: int, nickname: str):
        """处理超时、警告和踢出的协程"""
        try:
            wait_time = self.verification_timeout - self.kick_countdown_warning_time
            if self.kick_countdown_warning_time > 0 and wait_time > 0:
                await asyncio.sleep(wait_time)
                if uid not in self.pending: return
                
                at_user = f"[CQ:at,qq={uid}]"
                warning_msg = _safe_format(
                    self.countdown_warning_prompt, 
                    at_user=at_user, 
                    member_name=nickname
                )
                try:
                    await bot.api.call_action("send_group_msg", group_id=gid, message=warning_msg)
                except Exception as e:
                    logger.warning(f"[QQ Verify] 发送超时警告失败: {e}")
                
                await asyncio.sleep(self.kick_countdown_warning_time)
            else:
                await asyncio.sleep(self.verification_timeout)

            if uid not in self.pending: return

            at_user = f"[CQ:at,qq={uid}]"
            failure_msg = _safe_format(
                self.failure_message, 
                at_user=at_user, 
                member_name=nickname, 
                countdown=self.kick_delay
            )
            await bot.api.call_action("send_group_msg", group_id=gid, message=failure_msg)
            
            await asyncio.sleep(self.kick_delay)

            if uid not in self.pending: return
            
            await bot.api.call_action("set_group_kick", group_id=gid, user_id=int(uid), reject_add_request=False)
            logger.info(f"[QQ Verify] 用户 {uid} ({nickname}) 验证超时，已从群 {gid} 踢出。")
            
            kick_msg = _safe_format(
                self.kick_message, 
                at_user=at_user, 
                member_name=nickname
            )
            await bot.api.call_action("send_group_msg", group_id=gid, message=kick_msg)

        except asyncio.CancelledError:
            logger.info(f"[QQ Verify] 踢出任务已取消 (用户 {uid})。")
        except Exception as e:
            logger.error(f"[QQ Verify] 踢出流程发生错误 (用户 {uid}): {e}")
        finally:
            self.pending.pop(uid, None)