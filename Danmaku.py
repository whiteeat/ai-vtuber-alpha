# -*- coding: utf-8 -*-
import ctypes
import asyncio
import multiprocessing

import submodules.blivedm.blivedm as blivedm

from app_utils import *

class DanmakuProcess(multiprocessing.Process):
    def __init__(self, room_id, greeting_queue, chat_queue, thanks_queue, app_state, event_stop):
        super().__init__()

        self.room_id = room_id
        self.event_stop = event_stop
        self.enable_response = multiprocessing.Value(ctypes.c_bool, True)

        self.handler = ResponseHandler(greeting_queue, chat_queue, thanks_queue, app_state, self.enable_response)

    async def main(self):
        proc_name = self.name
        print(f"Initializing {proc_name}...")
        
        # 如果SSL验证失败就把ssl设为False，B站真的有过忘续证书的情况
        self.client = blivedm.BLiveClient(self.room_id, ssl=True)
        self.client.add_handler(self.handler)

        self.client.start()
        self.task_check_exit = asyncio.create_task(self.check_exit())

        await self.task_check_exit

    async def check_exit(self):
        while True:
            await asyncio.sleep(4)
            if self.event_stop.is_set():
                try:
                    print("DanmakuProcess should exit.")
                    self.client.stop()
                    await self.client.join()
                finally:
                    await self.client.stop_and_close()
                break

    def set_response_enabled(self, value):
        self.enable_response.value = value

    def is_response_enabled(self):
        return self.enable_response.value

    def run(self):
        asyncio.run(self.main())
        print(f"{self.name} exits.")


class ResponseHandler(blivedm.BaseHandler): 
    def __init__(self, greeting_queue, chat_queue, thanks_queue, app_state, enable_response) -> None:
        super().__init__()

        self._CMD_CALLBACK_DICT['INTERACT_WORD'] = self.__interact_word_callback
        self._CMD_CALLBACK_DICT['LIKE_INFO_V3_CLICK'] = self.__like_callback

        self.app_state = app_state
        self.greeting_queue = greeting_queue
        self.chat_queue = chat_queue
        self.thanks_queue = thanks_queue

        self.enable_response = enable_response

    # 入场和关注消息回调
    async def __interact_word_callback(self, client: blivedm.BLiveClient, command: dict):
        user_name = command['data']['uname']
        msg_type = command['data']['msg_type']
        channel = 'default'

        if msg_type == 1:
            print(f"{user_name}进场")

            if self.app_state.value == AppState.CHAT:
                # msg = f"（{user_name}进入了你的直播间。）"
                # msg = f"主播好！我是{user_name}，来你的直播间了！"
                msg = f"主播好！我是{user_name}，我来了！"
                print(f"[{client.room_id} INTERACT_WORD] {msg}")

                # if self.is_response_enabled():
                    # task = ChatTask(user_name, msg, channel)

                    # if self.greeting_queue.full():
                    #     _ = self.greeting_queue.get()

                    # self.greeting_queue.put(task)

        elif msg_type == 2:
            print(f"{user_name}关注")
            if (self.app_state.value == AppState.CHAT or 
                self.app_state.value == AppState.SING):
                # msg = f"（{user_name}关注了你的直播间。）"
                msg = f"我是{user_name}，刚刚关注了你的直播间！"
                print(f"[INTERACT_WORD] {msg}")

                if self.enable_response.value:
                    task = ChatTask(user_name, msg, channel)

                    if self.thanks_queue.full():
                        _ = self.thanks_queue.get()

                    self.thanks_queue.put(task)


    # 点赞消息回调
    async def __like_callback(self, client: blivedm.BLiveClient, command: dict):
        user_name = command['data']['uname']
        print(f"{user_name}点赞")
        print(f"[LIKE] {user_name}")

        channel = 'default'
        # msg = f"我是{user_name}，刚刚在你的直播间点了赞哦！"
        msg = f"我是{user_name}，给你点赞！"
        if self.enable_response.value:
            task = ChatTask(user_name, msg, channel)

            if self.thanks_queue.full():
                _ = self.thanks_queue.get()

            self.thanks_queue.put(task)

    async def _on_danmaku(self, client: blivedm.BLiveClient, message: blivedm.DanmakuMessage):
        user_name = message.uname
        msg = message.msg

        print(f'[{client.room_id} DANMU] {user_name}：{msg}')
        if self.app_state.value == AppState.CHAT:
            channel = 'chat'
            if self.enable_response.value:
                if self.chat_queue.full():
                    _ = self.chat_queue.get()

                task = ChatTask(user_name, msg, channel)
                self.chat_queue.put(task)

    async def _on_gift(self, client: blivedm.BLiveClient, message: blivedm.GiftMessage):
        user_name = message.uname
        gift_name = message.gift_name
        gift_num = message.num

        print(f'[{client.room_id} GIFT] {user_name} 赠送{gift_name}x{gift_num}'
              f' （{message.coin_type}瓜子x{message.total_coin}）')
        
        if (self.app_state.value == AppState.CHAT or 
            self.app_state.value == AppState.SING):

            channel = 'default'
        
            # msg = f"（{user_name}投喂了{gift_num}个{gift_name}礼物给你。）"
            msg = f"我是{user_name}，刚刚投喂了{gift_num}个{gift_name}礼物给你！"
            if self.enable_response.value:
                task = ChatTask(user_name, msg, channel)

                if self.thanks_queue.full():
                    _ = self.thanks_queue.get()

                self.thanks_queue.put(task)

    # async def _on_buy_guard(self, client: blivedm.BLiveClient, message: blivedm.GuardBuyMessage):
    #     print(f'[{client.room_id}] {message.username} 购买{message.gift_name}')

    # async def _on_super_chat(self, client: blivedm.BLiveClient, message: blivedm.SuperChatMessage):
    #     print(f'[{client.room_id}] 醒目留言 ¥{message.price} {message.uname}：{message.message}')