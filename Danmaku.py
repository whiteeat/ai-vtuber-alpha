# -*- coding: utf-8 -*-
import ctypes
import asyncio
import multiprocessing

import http.cookies

import aiohttp

import submodules.blivedm.blivedm as blivedm
import submodules.blivedm.blivedm.models.web as web_models

from threading import Timer

from app_utils import *

class DanmakuProcess(multiprocessing.Process):
    def __init__(self, room_id, greeting_queue, chat_queue, thanks_queue, app_state, event_stop):
        super().__init__()

        self.room_id = room_id
        self.event_stop = event_stop
        self.enable_response = multiprocessing.Value(ctypes.c_bool, True)

        self.handler = ResponseHandler(greeting_queue, chat_queue, thanks_queue, app_state, self.enable_response)

        # https://github.com/BilibiliVideoDownload/BilibiliVideoDownload/wiki/%E8%8E%B7%E5%8F%96SESSDATA
        # 这里填一个已登录账号的cookie。不填cookie也可以连接，但是收到弹幕的用户名会打码，UID会变成0
        self.SESSDATA = ''
        self.session = None

    async def main(self):
        self.init_session()

        proc_name = self.name
        print(f"Initializing {proc_name}...")
        
        self.client = blivedm.BLiveClient(self.room_id, session=self.session)
        self.client.set_handler(self.handler)

        self.client.start()
        self.task_check_exit = asyncio.create_task(self.check_exit())

        try:
            await self.task_check_exit
        except Exception as e:
            print(e)
        finally:
            await self.session.close()

    def init_session(self):
        cookies = http.cookies.SimpleCookie()
        cookies['SESSDATA'] = self.SESSDATA
        cookies['SESSDATA']['domain'] = 'bilibili.com'

        self.session = aiohttp.ClientSession()
        self.session.cookie_jar.update_cookies(cookies)

    async def check_exit(self):
        while True:
            await asyncio.sleep(4)
            if self.event_stop.is_set():
                try:
                    print("DanmakuProcess should exit.")
                    self.client.stop()
                    await self.client.join()
                except Exception as e:
                    print(e)
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

        # self._CMD_CALLBACK_DICT['INTERACT_WORD'] = self.__interact_word_callback
        # self._CMD_CALLBACK_DICT['LIKE_INFO_V3_CLICK'] = self.__like_callback

        self.app_state = app_state
        self.greeting_queue = greeting_queue
        self.chat_queue = chat_queue
        self.thanks_queue = thanks_queue

        self.enable_response = enable_response
        self.should_thank_gift = True

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

    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
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

    async def _on_gift(self, client: blivedm.BLiveClient, message: web_models.GiftMessage):
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

                def set_should_thank_gift():
                    print("set_should_thank_gift is triggered!")
                    self.should_thank_gift = True

                if self.should_thank_gift:
                    if self.thanks_queue.full():
                        _ = self.thanks_queue.get()

                    self.thanks_queue.put(task)
                    self.should_thank_gift = False

                    t = Timer(10.0, set_should_thank_gift)
                    t.start()

    # async def _on_buy_guard(self, client: blivedm.BLiveClient, message: blivedm.GuardBuyMessage):
    #     print(f'[{client.room_id}] {message.username} 购买{message.gift_name}')

    # async def _on_super_chat(self, client: blivedm.BLiveClient, message: blivedm.SuperChatMessage):
    #     print(f'[{client.room_id}] 醒目留言 ¥{message.price} {message.uname}：{message.message}')