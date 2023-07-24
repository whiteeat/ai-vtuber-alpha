from bilibili_api import live, sync

room_id = ""
room = live.LiveDanmaku(room_id)

@room.on('DANMU_MSG')
async def on_danmaku(event):
    # 收到弹幕
    # print(event)
    msg = event["data"]["info"][1]
    print(msg)

@room.on('SEND_GIFT')
async def on_gift(event):
    # 收到礼物
    print(event)

sync(room.connect())