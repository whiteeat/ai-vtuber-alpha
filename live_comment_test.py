import os
import requests

import asyncio
import zlib
from aiowebsocket.converses import AioWebSocket
import json

room_id = "14655481"
baseurl_http = "http://api.live.bilibili.com/ajax/msg?roomid="
baseurl_https = "https://api.live.bilibili.com/xlive/web-room/v1/dM/gethistory"


def get_live_comment_http(url):
    res = requests.get(url)
    content = res.json()
    code = content['code']
    print(content)

    if res.status_code == 200 and code == 0:
        info_last = content['data']['room'][-1]
        name = info_last['nickname']
        timeline = info_last['timeline'].split(' ')[-1]
        text = info_last['text']
        msg = timeline + ' ' + name + ':' + text
        return msg
    
    return None

def get_live_comment_https(url, headers, data):
    res = requests.post(url, headers, data)
    content = res.json()
    code = content['code']
    print(content)

    if res.status_code == 200 and code == 0:
        info_last = content['data']['room'][-1]
        name = info_last['nickname']
        timeline = info_last['timeline'].split(' ')[-1]
        text = info_last['text']
        msg = timeline + ' ' + name + ':' + text
        return msg

    return None


async def startup(room_id):
    # https://blog.csdn.net/Sharp486/article/details/122466308
    remote = 'ws://broadcastlv.chat.bilibili.com:2244/sub'

    data_raw = '000000{headerLen}0010000100000007000000017b22726f6f6d6964223a{roomid}7d'
    data_raw = data_raw.format(headerLen=hex(27 + len(room_id))[2:],
                            roomid=''.join(map(lambda x: hex(ord(x))[2:], list(room_id))))

    async with AioWebSocket(remote) as aws:
        converse = aws.manipulator
        await converse.send(bytes.fromhex(data_raw))
        task_recv = asyncio.create_task(recvDM(converse))
        task_heart_beat = asyncio.create_task(sendHeartBeat(converse))
        tasks = [task_recv, task_heart_beat]
        await asyncio.wait(tasks)

async def sendHeartBeat(websocket):
    hb='00 00 00 10 00 10 00 01  00 00 00 02 00 00 00 01'

    while True:
        await asyncio.sleep(30)
        await websocket.send(bytes.fromhex(hb))
        print('[Notice] Sent HeartBeat.')

async def recvDM(websocket):
    while True:
        recv_text = await websocket.receive()

        if recv_text == None:
            recv_text = b'\x00\x00\x00\x1a\x00\x10\x00\x01\x00\x00\x00\x08\x00\x00\x00\x01{"code":0}'

        printDM(recv_text)

def printDM(data):
    # ????????????????????????????????????????????????
    packetLen = int(data[:4].hex(), 16)
    ver = int(data[6:8].hex(), 16)
    op = int(data[8:12].hex(), 16)

    # ?????????????????????????????????????????????????????????????????????????????????????????????????????????
    if (len(data) > packetLen):
        printDM(data[packetLen:])
        data = data[:packetLen]

    # ????????????????????? zlib ????????????????????????????????????????????????
    if (ver == 2):
        data = zlib.decompress(data[16:])
        printDM(data)
        return

    # ver ???1????????????????????????????????????????????????????????????op ???3?????????????????????????????????
    if (ver == 1):
        if (op == 3):
            print('[RENQI]  {}'.format(int(data[16:].hex(), 16)))
        return


    # ver ??????2?????????1??????????????????0???????????????????????? json ?????????
    # op ???5??????????????????????????????cmd ????????????????????????
    if (op == 5):
        try:
            jd = json.loads(data[16:].decode('utf-8', errors='ignore'))
            if (jd['cmd'] == 'DANMU_MSG'):
                print('[DANMU] ', jd['info'][2][1], ': ', jd['info'][1])
            elif (jd['cmd'] == 'SEND_GIFT'):
                print('[GITT]', jd['data']['uname'], ' ', jd['data']['action'], ' ', jd['data']['num'], 'x',
                      jd['data']['giftName'])
            elif (jd['cmd'] == 'LIVE'):
                print('[Notice] LIVE Start!')
            elif (jd['cmd'] == 'PREPARING'):
                print('[Notice] LIVE Ended!')
            else:
                print('[OTHER] ', jd['cmd'])
        except Exception as e:
            print(e)
            pass

if __name__ == '__main__':
    USE_HTTP = False
    USE_HTTPS = False

    while False:
        if USE_HTTP:
            try:
                url_http = baseurl_http + room_id
                msg = get_live_comment_http(url_http)
                print(msg)
            except Exception as e:
                print(e)
        
        elif USE_HTTPS:
            try:
                headers = {
                    'Host': 'api.live.bilibili.com',
                    "User-Agent": "Mozilla / 5.0(Windows NT 10.0; Win64; x64) AppleWebKit / 537.36(KHTML, like Gecko) Chrome / 80.0.3987.122  Safari / 537.36"
                }

                # ???????????????
                data = {
                    'roomid': room_id,
                    'csrf_token': '',
                    'csrf': '',
                    'visit_id': '',
                }
                msg = get_live_comment_https(baseurl_https, headers, data)
                print(msg)
            except Exception as e:
                print(e)
        
        os.system("pause")

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(startup(room_id))
    except Exception as e:
        print(e)
        print('??????')


