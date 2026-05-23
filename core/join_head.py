import asyncio
import random
import re
from typing import Dict, Any, Tuple
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from .config_utils import config_get, config_int, config_str


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
        self.pending: Dict[str, Dict[str, Any]] = {}
        self.reload_config(config)

    def reload_config(self, config: Dict[str, Any]):
        self.config = config
        configs = [config]

        # --- 时间控制 ---
        self.verification_timeout = config_int(configs, ["verification_timeout"], 120)
        self.kick_countdown_warning_time = config_int(configs, ["kick_countdown_warning_time"], 15)
        self.kick_delay = config_int(configs, ["kick_delay"], 5)
        self.max_wrong_attempts = config_int(configs, ["max_wrong_attempts"], 3)
        self.verification_difficulty = config_str(configs, ["verification_difficulty"], "normal").lower()
        self.verification_message_mode = config_str(configs, ["verification_message_mode"], "group").lower()

        #消息模板模板 ---
        self.new_member_prompt = config_get(
            configs,
            ["new_member_prompt"],
            "{at_user} 欢迎加入本群！请在 {timeout} 分钟内@我并回答下面的问题以完成验证：\n{question}"
        )
        self.welcome_message = config_get(
            configs,
            ["welcome_message"],
            "{at_user} 验证成功，欢迎你的加入！\n1.请仔细阅读群公告\n2.群文件下载整合包自带IP\n3.白名单添加，群聊发送指令 “/绑定 您的ID”\n最后祝您玩得愉快"
        )
        self.wrong_answer_prompt = config_get(
            configs,
            ["wrong_answer_prompt"],
            "{at_user} 答案错误，请重新回答验证。这是你的新问题：\n{question}"
        )
        self.wrong_answer_limit_prompt = config_get(
            configs,
            ["wrong_answer_limit_prompt"],
            "{at_user} 答案错误次数过多，你将在 {countdown} 秒后被请出本群。"
        )
        self.private_verification_notice_prompt = config_get(
            configs,
            ["private_verification_notice_prompt"],
            "{at_user} 验证题已通过私聊发送，请在 {timeout} 分钟内完成验证。"
        )
        self.private_message_failed_prompt = config_get(
            configs,
            ["private_message_failed_prompt"],
            "{at_user} 私聊发送失败，请在群内 @我 回答下面的问题完成验证：\n{question}"
        )
        self.countdown_warning_prompt = config_get(
            configs,
            ["countdown_warning_prompt"],
            "{at_user} 验证即将超时，请尽快查看我的验证消息进行人机验证！"
        )
        self.failure_message = config_get(
            configs,
            ["failure_message"],
            "{at_user} 验证超时，你将在 {countdown} 秒后被请出本群。"
        )
        self.kick_message = config_get(
            configs,
            ["kick_message"],
            "{at_user} 因未在规定时间内完成验证，已被请出本群。"
        )
        logger.info(
            "[QQ Verify] 配置已加载: "
            f"timeout={self.verification_timeout}, difficulty={self.verification_difficulty}, "
            f"message_mode={self.verification_message_mode}, max_wrong_attempts={self.max_wrong_attempts}"
        )

    def _pending_key(self, gid: Any, uid: str) -> str:
        return f"{gid}:{uid}"

    def _get_raw_message(self, event: AstrMessageEvent) -> Dict[str, Any]:
        raw = event.message_obj.raw_message
        if isinstance(raw, dict):
            return raw
        return {}

    def _get_bot(self, event: AstrMessageEvent) -> Any:
        return getattr(event, "bot", None)

    def _find_private_pending_keys(self, uid: str) -> list[str]:
        return [key for key, item in self.pending.items() if item.get("uid") == uid]

    def _generate_math_problem(self) -> Tuple[str, int]:
        """动态数学问题"""
        if self.verification_difficulty == "easy":
            problem_type = random.choice(['addition', 'subtraction'])
        elif self.verification_difficulty == "hard":
            problem_type = random.choice(['addition', 'subtraction', 'multiplication', 'division', 'sequence'])
        else:
            problem_type = random.choice(['addition', 'subtraction', 'division'])
        
        if problem_type == 'addition':
            if self.verification_difficulty == "hard":
                num1 = random.randint(100, 200)
                num2 = random.randint(10, 200)
            else:
                num1 = random.randint(10, 80)
                num2 = random.randint(10, 80)
            answer = num1 + num2
            question = f"{num1} + {num2} = ?"
            return question, answer
            
        elif problem_type == 'subtraction':
            if self.verification_difficulty == "hard":
                num1 = random.randint(80, 200)
                num2 = random.randint(10, num1)
            else:
                num1 = random.randint(20, 100)
                num2 = random.randint(10, num1)
            answer = num1 - num2
            question = f"{num1} - {num2} = ?"
            return question, answer
            
        elif problem_type == 'multiplication':
            num1 = random.randint(12, 30)
            num2 = random.randint(12, 30)
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
        raw = self._get_raw_message(event)
        post_type = raw.get("post_type")

        if post_type == "notice":
            if raw.get("notice_type") == "group_increase":
                await self._process_new_member(event)
            elif raw.get("notice_type") == "group_decrease":
                await self._process_member_decrease(event)
        
        elif post_type == "message":
            if raw.get("message_type") == "group":
                await self._process_group_verification_message(event)
            elif raw.get("message_type") == "private":
                await self._process_private_verification_message(event)

    async def _process_new_member(self, event: AstrMessageEvent):
        """处理新成员入群"""
        raw = self._get_raw_message(event)
        uid = str(raw.get("user_id"))
        gid = raw.get("group_id")
        if gid is None:
            logger.warning(f"[QQ Verify] 新成员 {uid} 入群事件缺少群号，已忽略。")
            return
        await self._start_verification_process(event, uid, gid, is_new_member=True)

    async def _start_verification_process(self, event: AstrMessageEvent, uid: str, gid: Any, is_new_member: bool):
        """为用户启动或重启验证流程"""
        key = self._pending_key(gid, uid)
        attempts = 0
        if key in self.pending:
            attempts = int(self.pending[key].get("attempts", 0))
            old_task = self.pending[key].get("task")
            if old_task and not old_task.done():
                old_task.cancel()

        question, answer = self._generate_math_problem()
        logger.info(f"[QQ Verify] 为用户 {uid} 在群 {gid} 生成验证问题: {question} (答案: {answer})")

        bot = self._get_bot(event)
        if not bot:
            logger.warning("[QQ Verify] 无法获取 Bot 实例，跳过本次验证流程。")
            return

        nickname = uid
        try:
            user_info = await bot.api.call_action("get_group_member_info", group_id=gid, user_id=int(uid))
            nickname = user_info.get("card", "") or user_info.get("nickname", uid)
        except Exception as e:
            logger.warning(f"[QQ Verify] 获取用户 {uid} 昵称失败: {e}")

        task = asyncio.create_task(self._timeout_kick(bot, key, uid, gid, nickname))
        self.pending[key] = {"gid": gid, "uid": uid, "answer": answer, "attempts": attempts, "task": task}

        at_user = f"[CQ:at,qq={uid}]"
        
        format_args = {
            "at_user": at_user,
            "member_name": nickname,
            "question": question,
            "timeout": self.verification_timeout // 60,
            "countdown": self.kick_delay,
            "wrong_attempts": attempts,
            "remaining_attempts": max(self.max_wrong_attempts - attempts, 0) if self.max_wrong_attempts > 0 else "不限"
        }
        
        await self._send_verification_prompt(bot, uid, gid, nickname, format_args, is_new_member)

    async def _send_verification_prompt(
        self,
        bot,
        uid: str,
        gid: Any,
        nickname: str,
        format_args: Dict[str, Any],
        is_new_member: bool
    ):
        group_prompt = _safe_format(
            self.new_member_prompt if is_new_member else self.wrong_answer_prompt,
            **format_args
        )
        private_args = dict(format_args)
        private_args["at_user"] = nickname
        private_prompt = _safe_format(
            self.new_member_prompt if is_new_member else self.wrong_answer_prompt,
            **private_args
        )

        mode = self.verification_message_mode
        if mode not in {"group", "private", "hybrid"}:
            logger.warning(f"[QQ Verify] 未知验证消息模式 {mode}，已回退为 group。")
            mode = "group"

        if mode == "group":
            await bot.api.call_action("send_group_msg", group_id=gid, message=group_prompt)
            return

        try:
            await bot.api.call_action("send_private_msg", user_id=int(uid), message=private_prompt)
            if is_new_member:
                notice_msg = _safe_format(self.private_verification_notice_prompt, **format_args)
                await bot.api.call_action("send_group_msg", group_id=gid, message=notice_msg)
            return
        except Exception as exc:
            logger.warning(f"[QQ Verify] 向用户 {uid} 发送私聊验证失败: {exc}")
            if mode == "private":
                failed_msg = _safe_format(self.private_message_failed_prompt, **format_args)
                await bot.api.call_action("send_group_msg", group_id=gid, message=failed_msg)
                return

        await bot.api.call_action("send_group_msg", group_id=gid, message=group_prompt)

    async def _process_group_verification_message(self, event: AstrMessageEvent):
        """处理群消息以进行验证"""
        uid = str(event.get_sender_id())
        raw = self._get_raw_message(event)
        gid = raw.get("group_id")
        if gid is None:
            return
        key = self._pending_key(gid, uid)
        if key not in self.pending:
            return
        
        pending_item = self.pending[key]
        gid = pending_item["gid"]

        bot_id = str(event.get_self_id())
        message_segs = raw.get("message", [])
        if not isinstance(message_segs, list):
            return

        at_me = any(seg.get("type") == "at" and str(seg.get("data", {}).get("qq")) == bot_id for seg in message_segs)

        if not at_me:
            return

        await self._process_answer(event, key, re.sub(r'\[CQ:at,qq=\d+\]', '', event.message_str).strip(), raw)

    async def _process_private_verification_message(self, event: AstrMessageEvent):
        """处理私聊消息以进行验证"""
        uid = str(event.get_sender_id())
        keys = self._find_private_pending_keys(uid)
        if not keys:
            return

        if len(keys) > 1:
            bot = self._get_bot(event)
            if bot:
                await bot.api.call_action("send_private_msg", user_id=int(uid), message="你当前在多个群有待验证记录，请回到对应群里 @我 回答。")
            event.stop_event()
            return

        await self._process_answer(event, keys[0], event.message_str.strip(), self._get_raw_message(event))

    async def _process_answer(self, event: AstrMessageEvent, key: str, answer_text: str, raw: Dict[str, Any]):
        pending_item = self.pending.get(key)
        if not pending_item:
            return

        uid = str(event.get_sender_id())
        gid = pending_item["gid"]
        text_without_at = answer_text
        numbers_found = re.findall(r'\d+', text_without_at)
        
        if not numbers_found:
            return

        try:
            user_answer = int(numbers_found[-1])
        except (ValueError, TypeError):
            return

        correct_answer = pending_item.get("answer")

        if user_answer == correct_answer:
            logger.info(f"[QQ Verify] 用户 {uid} 在群 {gid} 验证成功。")
            pending_item["task"].cancel()
            self.pending.pop(key, None)

            nickname = raw.get("sender", {}).get("card", "") or raw.get("sender", {}).get("nickname", uid)
            
            welcome_msg = _safe_format(
                self.welcome_message, 
                at_user=f"[CQ:at,qq={uid}]", 
                member_name=nickname
            )
            bot = self._get_bot(event)
            if bot:
                await bot.api.call_action("send_group_msg", group_id=gid, message=welcome_msg)
            event.stop_event()
        else:
            pending_item["attempts"] = int(pending_item.get("attempts", 0)) + 1
            logger.info(f"[QQ Verify] 用户 {uid} 在群 {gid} 回答错误，当前错误次数: {pending_item['attempts']}。")
            if self.max_wrong_attempts > 0 and pending_item["attempts"] >= self.max_wrong_attempts:
                bot = self._get_bot(event)
                if bot:
                    await self._kick_after_wrong_limit(bot, key, uid, gid, raw)
            else:
                await self._start_verification_process(event, uid, gid, is_new_member=False)
            event.stop_event()

    async def _process_member_decrease(self, event: AstrMessageEvent):
        """处理成员离开"""
        raw = self._get_raw_message(event)
        uid = str(raw.get("user_id"))
        gid = raw.get("group_id")
        if gid is None:
            return
        key = self._pending_key(gid, uid)
        if key in self.pending:
            self.pending[key]["task"].cancel()
            self.pending.pop(key, None)
            logger.info(f"[QQ Verify] 待验证用户 {uid} 已离开，清理其验证状态。")

    async def _kick_after_wrong_limit(self, bot, key: str, uid: str, gid: int, raw: Dict[str, Any]):
        item = self.pending.get(key)
        if not item:
            return

        task = item.get("task")
        if task and not task.done():
            item["task"] = None
            task.cancel()

        nickname = raw.get("sender", {}).get("card", "") or raw.get("sender", {}).get("nickname", uid)
        at_user = f"[CQ:at,qq={uid}]"
        limit_msg = _safe_format(
            self.wrong_answer_limit_prompt,
            at_user=at_user,
            member_name=nickname,
            countdown=self.kick_delay,
            max_wrong_attempts=self.max_wrong_attempts
        )
        await bot.api.call_action("send_group_msg", group_id=gid, message=limit_msg)
        await asyncio.sleep(self.kick_delay)

        if key not in self.pending:
            return

        await bot.api.call_action("set_group_kick", group_id=gid, user_id=int(uid), reject_add_request=False)
        kick_msg = _safe_format(self.kick_message, at_user=at_user, member_name=nickname)
        await bot.api.call_action("send_group_msg", group_id=gid, message=kick_msg)
        self.pending.pop(key, None)

    # 移除了对 Bot 的类型提示，以确保兼容性
    async def _timeout_kick(self, bot, key: str, uid: str, gid: int, nickname: str):
        """处理超时、警告和踢出的协程"""
        try:
            wait_time = self.verification_timeout - self.kick_countdown_warning_time
            if self.kick_countdown_warning_time > 0 and wait_time > 0:
                await asyncio.sleep(wait_time)
                if key not in self.pending:
                    return
                
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

            if key not in self.pending:
                return

            at_user = f"[CQ:at,qq={uid}]"
            failure_msg = _safe_format(
                self.failure_message, 
                at_user=at_user, 
                member_name=nickname, 
                countdown=self.kick_delay
            )
            await bot.api.call_action("send_group_msg", group_id=gid, message=failure_msg)
            
            await asyncio.sleep(self.kick_delay)

            if key not in self.pending:
                return
            
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
            item = self.pending.get(key)
            if item and item.get("task") is asyncio.current_task():
                self.pending.pop(key, None)

    async def terminate(self):
        for item in list(self.pending.values()):
            task = item.get("task")
            if task and not task.done():
                task.cancel()
        self.pending.clear()
        logger.info("[QQ Verify] 已清理所有待验证任务。")