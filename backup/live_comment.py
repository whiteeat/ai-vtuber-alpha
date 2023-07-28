class LiveCommentProcess(multiprocessing.Process):
    def __init__(self, room_id, greeting_queue, chat_queue, thanks_queue, app_state, event_initialized, event_stop):
        super().__init__()
        self.room_id = room_id

        self.greeting_queue = greeting_queue
        self.chat_queue = chat_queue
        self.thanks_queue = thanks_queue

        self.event_initialized = event_initialized
        self.event_stop = event_stop
        self.app_state = app_state

        self.enable_response = multiprocessing.Value(ctypes.c_bool, False)

    def set_response_enabled(self, value):
        self.enable_response.value = value

    def is_response_enabled(self):
        return self.enable_response.value

    async def startup(self, room_id):
        # https://blog.csdn.net/Sharp486/article/details/122466308
        remote = 'ws://broadcastlv.chat.bilibili.com:2244/sub'

        data_raw = '000000{headerLen}0010000100000007000000017b22726f6f6d6964223a{roomid}7d'
        data_raw = data_raw.format(headerLen=hex(27 + len(room_id))[2:],
                                   roomid=''.join(map(lambda x: hex(ord(x))[2:], list(room_id))))

        async with AioWebSocket(remote) as aws:
            converse = aws.manipulator
            await converse.send(bytes.fromhex(data_raw))
            task_recv = asyncio.create_task(self.recvDM(converse))
            task_heart_beat = asyncio.create_task(self.sendHeartBeat(converse))
            tasks = [task_recv, task_heart_beat]
            await asyncio.wait(tasks)

    async def sendHeartBeat(self, websocket):
        hb = '00 00 00 10 00 10 00 01  00 00 00 02 00 00 00 01'

        while True:
            await asyncio.sleep(30)
            await websocket.send(bytes.fromhex(hb))
            print('[Notice] Sent HeartBeat.')

            if self.event_stop.is_set():
                print("sendHeartBeat ends.")
                break

    async def recvDM(self, websocket):
        while True:
            recv_text = await websocket.receive()

            if recv_text == None:
                recv_text = b'\x00\x00\x00\x1a\x00\x10\x00\x01\x00\x00\x00\x08\x00\x00\x00\x01{"code":0}'

            # if self.app_state.value == AppState.CHAT:
            self.processDM(recv_text)

            if self.event_stop.is_set():
                print("recvDM ends.")
                break

    def processDM(self, data):
        # 获取数据包的长度，版本和操作类型
        packetLen = int(data[:4].hex(), 16)
        ver = int(data[6:8].hex(), 16)
        op = int(data[8:12].hex(), 16)

        # 有的时候可能会两个数据包连在一起发过来，所以利用前面的数据包长度判断，
        if (len(data) > packetLen):
            self.processDM(data[packetLen:])
            data = data[:packetLen]

        # 有时会发送过来 zlib 压缩的数据包，这个时候要去解压。
        if (ver == 2):
            data = zlib.decompress(data[16:])
            self.processDM(data)
            return

        # ver 为1的时候为进入房间后或心跳包服务器的回应。op 为3的时候为房间的人气值。
        if (ver == 1):
            if (op == 3):
                print('[RENQI]  {}'.format(int(data[16:].hex(), 16)))
            return

        # ver 不为2也不为1目前就只能是0了，也就是普通的 json 数据。
        # op 为5意味着这是通知消息，cmd 基本就那几个了。
        if (op == 5):
            try:
                jd = json.loads(data[16:].decode('utf-8', errors='ignore'))

                print(f"jd['cmd'] is: {jd['cmd']}")
                if (jd['cmd'] == 'DANMU_MSG'):
                    if self.app_state.value == AppState.CHAT:
                        user_name = jd['info'][2][1]
                        msg = jd['info'][1]
                        print('[DANMU] ', user_name, ': ', msg)

                        channel = 'chat'
                        if self.is_response_enabled():
                            if self.chat_queue.full():
                                _ = self.chat_queue.get()

                            task = ChatTask(user_name, msg, channel)
                            self.chat_queue.put(task)

                elif (jd['cmd'] == 'SEND_GIFT'):
                    if (self.app_state.value == AppState.CHAT or 
                        self.app_state.value == AppState.SING):
                        print('[GITT]', jd['data']['uname'], ' ', jd['data']['action'], ' ', jd['data']['num'], 'x',
                            jd['data']['giftName'])
                        user_name = jd['data']['uname']
                        gift_num = jd['data']['num']
                        gift_name = jd['data']['giftName']
                        channel = 'default'
                    
                        # msg = f"（{user_name}投喂了{gift_num}个{gift_name}礼物给你。）"
                        msg = f"我是{user_name}，刚刚投喂了{gift_num}个{gift_name}礼物给你！"
                        if self.is_response_enabled():
                            task = ChatTask(user_name, msg, channel)

                            if self.thanks_queue.full():
                                _ = self.thanks_queue.get()

                            self.thanks_queue.put(task)

                elif (jd['cmd'] == 'LIKE_INFO_V3_CLICK'):
                    user_name = jd['data']['uname']
                    print(f"[LIKE] {user_name}")
                    channel = 'default'
                    msg = f"我是{user_name}，刚刚在你的直播间点了赞哦！"
                    if self.is_response_enabled():
                        task = ChatTask(user_name, msg, channel)

                        if self.thanks_queue.full():
                            _ = self.thanks_queue.get()

                        self.thanks_queue.put(task)

                elif (jd['cmd'] == 'LIVE'):
                    print('[Notice] LIVE Start!')
                elif (jd['cmd'] == 'PREPARING'):
                    print('[Notice] LIVE Ended!')
                elif (jd['cmd'] == 'INTERACT_WORD'):
                    user_name = jd['data']['uname']
                    msg_type = jd['data']['msg_type']
                    channel = 'default'
                    # 进场
                    if msg_type == 1:
                        if self.app_state.value == AppState.CHAT:
                            # msg = f"（{user_name}进入了你的直播间。）"
                            # msg = f"主播好！我是{user_name}，来你的直播间了！"
                            msg = f"主播好！我是{user_name}，我来了！"
                            print(f"[INTERACT_WORD] {msg}")

                            # if self.is_response_enabled():
                                # task = ChatTask(user_name, msg, channel)

                                # if self.greeting_queue.full():
                                #     _ = self.greeting_queue.get()

                                # self.greeting_queue.put(task)

                    # 关注
                    elif msg_type == 2:
                        if (self.app_state.value == AppState.CHAT or 
                            self.app_state.value == AppState.SING):
                            # msg = f"（{user_name}关注了你的直播间。）"
                            msg = f"我是{user_name}，刚刚关注了你的直播间！"
                            print(f"[INTERACT_WORD] {msg}")

                            if self.is_response_enabled():
                                task = ChatTask(user_name, msg, channel)

                                if self.thanks_queue.full():
                                    _ = self.thanks_queue.get()

                                self.thanks_queue.put(task)
                else:
                    print('[OTHER] ', jd['cmd'])
            except Exception as e:
                print(e)
                pass

    def run(self):
        proc_name = self.name
        print(f"Initializing {proc_name}...")

        self.event_initialized.set()

        print(f"{proc_name} is working...")
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.startup(self.room_id))
            print(f"{proc_name} exits.")
        except Exception as e:
            print(e)
            print('退出')