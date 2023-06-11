import multiprocessing
import random
import threading
import pyaudio
import pygame
import wave
import os
import time
import websockets
import json
import asyncio

evt_thd_trigger = threading.Event()


class SongList:
    def __init__(self):
        self.song_dir = rf"music/"
        self.names: list = []
        self.vox_files: list = []
        self.bgm_files: list = []
        self.song_dicts: list = []  # 本地音乐字典列表：id name vox bgm
        self.load_song_text()
        self.cur_song_index = -1

    def load_song_text(self):
        try:
            file_path = self.song_dir
            with open('songs.txt', 'rb') as f:
                lines = [line.strip() for line in f.readlines()]
            for line in lines:
                song_info = line.decode().strip().split(",")
                song = {
                    'id': song_info[0],
                    'name': song_info[1],
                    'abbr': song_info[2],
                    'artist': song_info[3],
                    'editor': song_info[4],
                    'vox': file_path + song_info[1] + "Vox.wav",
                    'bgm': file_path + song_info[1] + "Bgm.wav"
                }
                self.song_dicts.append(song)
        except Exception as e:
            print(f"load_song_text报错:{e}")

    def search_song(self, query: str = None):
        try:
            if query is None or query == '':
                print("请输入：‘点歌X’(如：点歌1/点歌Tear)")
                return None
            else:
                if self.song_dicts:
                    for song_dict in self.song_dicts:
                        if query == song_dict['id']:
                            self.cur_song_index = int(song_dict['id']) - 1
                            return song_dict
                        elif query in song_dict['vox'] and query in song_dict['bgm']:
                            self.cur_song_index = int(song_dict['id']) - 1
                            return song_dict
                    else:
                        self.cur_song_index = -1
                        print("抱歉！未找到该歌曲~")
                        return None
        except Exception as e:
            print(f"search_song报错:{e}")


class SongPlayer:
    CHUNK = 1024

    def __init__(self, _song_list: SongList):
        self.song_list = _song_list
        self.virtual_audio_output_device_index = None
        self.virtual_audio_input_device_index = None
        self.virtual_audio_devices_are_found = False
        self.pau = pyaudio.PyAudio()
        self.get_device_indices()
        self.song_dict = None
        self.vox_volume = 1.0
        self.bgm_volume = 1.0
        self.playing = False
        self.paused = False
        self.stream_thread = threading.Thread(target=self.stream_audio)
        # Events
        self.on_play = None
        self.on_stop = None
        self.interrupted = False

    def get_device_indices(self) -> None:
        assert self.pau is not None
        self.virtual_audio_input_device_index = None
        self.virtual_audio_output_device_index = None
        for i in range(self.pau.get_device_count()):
            device_info = self.pau.get_device_info_by_index(i)
            if ("CABLE Output" in device_info['name'] and
                    device_info['hostApi'] == 0):
                assert device_info['index'] == i
                self.virtual_audio_input_device_index = i
            if ("CABLE Input" in device_info['name'] and
                    device_info['hostApi'] == 0):
                assert device_info['index'] == i
                self.virtual_audio_output_device_index = i
        if (self.virtual_audio_input_device_index is None or
                self.virtual_audio_output_device_index is None):
            print("Error: no valid virtual audio devices found!!!")
            self.virtual_audio_devices_are_found = False
        else:
            self.virtual_audio_devices_are_found = True

    def change_volume(self, data, _volume) -> bytes:
        volume = min(1.0, max(0.0, _volume))
        data = bytearray(data)
        for i in range(0, len(data), 2):
            sample = int.from_bytes(data[i:i + 2], byteorder='little', signed=True)
            sample = int(sample * volume)
            data[i:i + 2] = sample.to_bytes(2, byteorder='little', signed=True)
        return bytes(data)

    def stream_audio(self):
        if self.virtual_audio_devices_are_found:
            if self.on_play is not None:
                self.on_play()

            vox_wave = wave.open(self.song_dict['vox'], 'rb')
            bgm_wave = wave.open(self.song_dict['bgm'], 'rb')
            vox_stream = self.pau.open(format=self.pau.get_format_from_width(vox_wave.getsampwidth()),
                                       channels=vox_wave.getnchannels(),
                                       rate=vox_wave.getframerate(),
                                       output=True,  # 测试时耳机播
                                       output_device_index=self.virtual_audio_output_device_index)
            bgm_stream = self.pau.open(format=self.pau.get_format_from_width(bgm_wave.getsampwidth()),
                                       channels=bgm_wave.getnchannels(),
                                       rate=bgm_wave.getframerate(),
                                       output=True)
            
            junk = None
            init_junk = True
            while self.playing:
                if not self.paused:
                    vox_data = vox_wave.readframes(self.CHUNK)
                    bgm_data = bgm_wave.readframes(self.CHUNK)
                    vox_size = len(vox_data)
                    bgm_size = len(bgm_data)

                    if init_junk:
                        junk = bytes(vox_size)
                        init_junk = False

                    if vox_size != 0:
                        if self.interrupted:
                            vox_stream.write(junk)
                        else:
                            vox_stream.write(vox_data)
                    if bgm_size != 0:
                        bgm_stream.write(bgm_data)
                    if vox_size == 0 and bgm_size == 0:
                        break
                else:
                    time.sleep(0.1)

            vox_wave.close()
            bgm_wave.close()
            vox_stream.close()
            bgm_stream.close()
            self.playing = False
            self.song_list.cur_song_index = -1

            if self.on_stop is not None:
                self.on_stop()

    def play(self, query: str):
        self.song_dict = self.song_list.search_song(query)

        success = False
        if self.song_dict:
            self.playing = True
            self.stream_thread = threading.Thread(target=self.stream_audio)
            self.stream_thread.start()
            print(f"SONG:{self.song_dict['name']} is playing...")
            success = True
        else:
            if self.on_stop is not None:
                self.on_stop()

        return success

    def set_volume(self, vox_volume, bgm_volume):
        self.vox_volume = vox_volume
        self.bgm_volume = bgm_volume

    def stop(self):
        self.playing = False
        self.song_list.cur_song_index = -1

        # https://www.codecademy.com/resources/docs/python/threading/is-alive
        if self.stream_thread is not None and self.stream_thread.is_alive():
            self.stream_thread.join()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def close(self):
        self.stop()
        self.pau.terminate()


class PureMusic:
    def __init__(self, _song_list: SongList):
        pygame.mixer.init()
        self.song_list = _song_list
        self.music_dir = rf"music/"
        self.music_files: list = []
        self.load_music_files()
        self.cur_music_index = 0
        self.paused = False

    def load_music_files(self):
        # 获取当前目录下的所有音频文件
        file_path = self.music_dir
        for filename in os.listdir(file_path):
            if filename.endswith('Msc.mp3') or filename.endswith('Msc.wav'):
                filename = file_path + filename
                self.music_files.append(filename)

    def display_list(self):
        for music_path in self.music_files:
            print(f"{music_path}")

    def play(self):
        cur_music = self.music_files[self.cur_music_index]
        pygame.mixer.music.load(cur_music)
        pygame.mixer.music.play()

    def next(self):
        self.cur_music_index = (self.cur_music_index + 1) % len(self.music_files)
        self.play()

    def stop(self):
        pygame.mixer.music.fadeout(1000)

    def loop_music(self):
        if not self.music_files:
            print("无纯音乐文件！")
        else:
            first_time = True
            while evt_thd_trigger.isSet():
                try:
                    if -1 == self.song_list.cur_song_index:
                        if first_time:
                            self.play()
                            first_time = False
                        if not pygame.mixer.music.get_busy() and not self.paused:
                            self.next()
                    else:  # the song is playing
                        self.stop()
                        first_time = True
                    time.sleep(0.5)
                except Exception as e:
                    print(f"loop_music报错:{e}")
                    evt_thd_trigger.clear()


class Display:
    def __init__(self, song_list: SongList):
        self.song_list = song_list
        # self.screen_width = 620
        self.screen_width = 1000
        self.screen_height = 720
        pygame.init()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('SimHei', 40)
        self.title_font = pygame.font.SysFont('幼圆', 48)
        self.screen = None
        self.pos_y = self.screen_height / 2

    def draw_cur_song_name(self):
        y = 30
        # pygame.draw.rect(self.screen, (0, 127, 255), (0, 0, 620, 40), width=0)
        pygame.draw.rect(self.screen, (0, 0, 0), (0, 0, 620, 100), width=0)
        cur_show_index = self.song_list.cur_song_index
        if -1 == cur_show_index:
            color = (255, 255, 0)
            text = self.font.render(f"弹幕'点歌X'(如:点歌3/点歌哈基)", True, color)
            # text_rect = text.get_rect(center=(self.screen_width / 4, y))
            # self.screen.blit(text, text_rect)
            self.screen.blit(text, (10, y))
        else:
            color = (0, 255, 255)
            current_song = self.song_list.song_dicts[cur_show_index]['abbr'] + ' ' + \
                           self.song_list.song_dicts[cur_show_index]['artist'] + ' ' + \
                           self.song_list.song_dicts[cur_show_index]['editor']
            text = self.title_font.render(f"★" + current_song + f"★", True, color)
            # text_rect = text.get_rect(center=(self.screen_width / 4, y))
            # self.screen.blit(text, text_rect)
            self.screen.blit(text, (10, y))

    def draw_vox_file_list(self, _y):
        for i in range(len(self.song_list.song_dicts)):
            if i == self.song_list.cur_song_index:
                color = (0, 255, 127)
            else:
                color = (255, 255, 255)
            text = self.font.render(f'{i + 1}.' + self.song_list.song_dicts[i]['name'], True, color)
            ztx, zty, ztw, zth = text.get_rect()
            pos_rect = pygame.Rect(10, _y, ztw, zth)
            self.screen.blit(text, (pos_rect.x, pos_rect.y))
            _y += 50

    def draw_bgm_file_list(self):
        y = 50
        for i in range(len(self.song_list.song_dicts)):
            if i == self.song_list.cur_song_index:
                color = (127, 255, 0)
            else:
                color = (255, 255, 255)
            text = self.font.render(self.song_list.song_dicts[i]['name'], True, color)
            self.screen.blit(text, (self.screen_width / 2, y))
            y += 25

    def display_list(self):
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("优俊歌者")
        y = self.pos_y
        while evt_thd_trigger.isSet():  # T/F
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    evt_thd_trigger.clear()  # False
            try:
                y -= 2
                if y < len(self.song_list.song_dicts) * -25:
                    y = self.pos_y
                # self.screen.fill(color=(0, 127, 255))
                self.screen.fill(color=(0, 0, 0))
                self.draw_vox_file_list(y)
                # self.draw_bgm_file_list()
                self.draw_cur_song_name()
                pygame.display.update()
                self.clock.tick(30)
            except Exception as e:
                print(f"display_list报错:{e}")
                evt_thd_trigger.clear()  # False


class EmojiPlayer:
    def __init__(self, _song_list: SongList):
        self.song_list = _song_list

    def start_thread_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    async def request_token(self, websocket, plugin_name, plugin_developer, plugin_icon=None):
        request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "TokenRequestID",
            "messageType": "AuthenticationTokenRequest",
            "data": {
                "pluginName": plugin_name,
                "pluginDeveloper": plugin_developer,
                "pluginIcon": plugin_icon
            }
        }

        await websocket.send(json.dumps(request))
        response = await websocket.recv()
        json_response = json.loads(response)

        if json_response["messageType"] == "AuthenticationTokenResponse":
            return json_response["data"]["authenticationToken"]
        else:
            return None

    async def authenticate(self, websocket, plugin_name, plugin_developer, authentication_token):
        request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "AuthenticationRequestID",
            "messageType": "AuthenticationRequest",
            "data": {
                "pluginName": plugin_name,
                "pluginDeveloper": plugin_developer,
                "authenticationToken": authentication_token
            }
        }

        await websocket.send(json.dumps(request))
        response = await websocket.recv()
        json_response = json.loads(response)

        if json_response["messageType"] == "AuthenticationResponse":
            return json_response["data"]["authenticated"]
        else:
            return False

    async def request_trigger_hotkey(self, websocket, hotkey_id):
        request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "SomeID",
            "messageType": "HotkeyTriggerRequest",
            "data": {
                "hotkeyID": hotkey_id,
            }
        }

        await websocket.send(json.dumps(request))
        response = await websocket.recv()
        json_response = json.loads(response)

        if json_response["messageType"] == "HotkeyTriggerResponse":
            return json_response["data"]["hotkeyID"]
        else:
            return None

    async def play_emoji(self):
        uri = "ws://localhost:8001"
        async with websockets.connect(uri) as websocket:
            plugin_name = "My Cool Plugin"
            plugin_developer = "My Name"
            authentication_token = await self.request_token(websocket, plugin_name, plugin_developer)

            if authentication_token:
                print(f"Token: {authentication_token}")
                is_authenticated = await self.authenticate(websocket, plugin_name, plugin_developer,
                                                           authentication_token)
                print(f"Authenticated: {is_authenticated}")
            else:
                print("Token request failed")

            is_once = False
            is_finished = True
            while True:
                try:
                    if websocket is not None:
                        if -1 == self.song_list.cur_song_index:
                            is_once = True
                            hotkey_clear = '7f83b2e85bf34a6d97c5615578c47343'
                            triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_clear)
                            await asyncio.sleep(2)
                            hotkey_shock = '7debc6a385594274add1b51f392bfd20'
                            triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_shock)
                            await asyncio.sleep(0.1)
                            if is_finished:
                                is_finished = False
                                hotkey_clear = '7f83b2e85bf34a6d97c5615578c47343'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_clear)
                                hotkey_sakura = '6f9267fd4bbd4e8185b3df79d402e6d6'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sakura)
                                await asyncio.sleep(2)
                                hotkey_happy = '8bf6ffd23d8a439490d8166fc0025d95'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_happy)
                                await asyncio.sleep(2)
                        else:
                            is_finished = True
                            if is_once:
                                is_once = False
                                hotkey_clear = '7f83b2e85bf34a6d97c5615578c47343'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_clear)
                                hotkey_roger = '15d08dd5ba4e48349d6417e52fafc746'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_roger)
                                await asyncio.sleep(1)
                                hotkey_sparkle = '27af9687b7fd42f8969d1367ccee7c2b'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sparkle)
                                await asyncio.sleep(1)
                                hotkey_clear = '7f83b2e85bf34a6d97c5615578c47343'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_clear)
                            if self.song_list.cur_song_index in range(2):  # 1 2
                                hotkey_clear = '7f83b2e85bf34a6d97c5615578c47343'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_clear)
                                hotkey_sing = 'b1211cc396984fbca6efeba0f1791406'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sing)
                                await asyncio.sleep(3)
                                hotkey_sing_cry = '755e376639404e4a82e8590554f8838b'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sing_cry)
                                await asyncio.sleep(3)
                            elif self.song_list.cur_song_index in range(2, 3):  # 3
                                hotkey_clear = '7f83b2e85bf34a6d97c5615578c47343'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_clear)
                                hotkey_hachimi = 'f0e10b6c88cd49b983626d75b44c3095'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_hachimi)
                                await asyncio.sleep(3)
                                hotkey_hachimi_love = '1d057977c90a496fab69b3148f06f9f1'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_hachimi_love)
                                await asyncio.sleep(3)
                            elif self.song_list.cur_song_index in range(3, 4):  # 4
                                hotkey_clear = '7f83b2e85bf34a6d97c5615578c47343'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_clear)
                                hotkey_hachimi = 'f0e10b6c88cd49b983626d75b44c3095'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_hachimi)
                                await asyncio.sleep(3)
                                hotkey_hachimi_sparkle = '619d30d61a2c40a6a45228fab317d29b'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_hachimi_sparkle)
                                await asyncio.sleep(3)
                            elif self.song_list.cur_song_index in range(4, 5):  # 5
                                hotkey_clear = '7f83b2e85bf34a6d97c5615578c47343'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_clear)
                                hotkey_hachimi = 'f0e10b6c88cd49b983626d75b44c3095'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_hachimi)
                                await asyncio.sleep(3)
                                hotkey_hachimi_sakura = '131420f6803e4faca6eba8beb435be4d'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_hachimi_sakura)
                                await asyncio.sleep(3)
                            elif 0 == self.song_list.cur_song_index % 3:
                                hotkey_clear = '7f83b2e85bf34a6d97c5615578c47343'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_clear)
                                hotkey_sing = 'b1211cc396984fbca6efeba0f1791406'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sing)
                                await asyncio.sleep(1)
                                hotkey_sing_happy = 'dc6ff1661a6f4fa3bb0f913a03871524'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sing_happy)
                                await asyncio.sleep(2)
                                hotkey_sing_love = '0f0dee7c4a55465ebd5a479b01630eb3'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sing_love)
                                await asyncio.sleep(3)
                            elif 1 == self.song_list.cur_song_index % 3:
                                hotkey_clear = '7f83b2e85bf34a6d97c5615578c47343'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_clear)
                                hotkey_sing = 'b1211cc396984fbca6efeba0f1791406'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sing)
                                await asyncio.sleep(1)
                                hotkey_sing_happy = 'dc6ff1661a6f4fa3bb0f913a03871524'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sing_happy)
                                await asyncio.sleep(2)
                                hotkey_sing_sakura = 'f8efa02ce45b47ab91e5a2915cd53097'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sing_sakura)
                                await asyncio.sleep(3)
                            else:  # 3余2
                                hotkey_clear = '7f83b2e85bf34a6d97c5615578c47343'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_clear)
                                hotkey_sing = 'b1211cc396984fbca6efeba0f1791406'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sing)
                                await asyncio.sleep(1)
                                hotkey_sing_happy = 'dc6ff1661a6f4fa3bb0f913a03871524'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sing_happy)
                                await asyncio.sleep(2)
                                hotkey_sing_sparkle = '674428b2db4b4aea8d8f987d99fd32ce'
                                triggered_hotkey = await self.request_trigger_hotkey(websocket, hotkey_sing_sparkle)
                                await asyncio.sleep(3)

                    else:
                        print("websocket为空！")
                        break
                except Exception as e:
                    print(f"play_emoji报错:{e}")
                    break


class SongMixer:
    def __init__(self):
        self.song_list = SongList()
        self.song_plr = SongPlayer(_song_list=self.song_list)
        self.pure_music = PureMusic(self.song_list)
        self.pure_music_thread = None
        self.display = Display(self.song_list)
        self.display_thread = None
        self.emoji_player = EmojiPlayer(self.song_list)
        self.emoji_player_thread = None
        self.is_thd_started = False
        self.new_loop = asyncio.new_event_loop()

    def run_threads(self):
        evt_thd_trigger.set()  # True
        self.pure_music_thread = threading.Thread(target=self.pure_music.loop_music, daemon=True)
        self.pure_music_thread.start()
        self.display_thread = threading.Thread(target=self.display.display_list, daemon=True)
        self.display_thread.start()
        # new_loop = asyncio.new_event_loop()
        self.emoji_player_thread = threading.Thread(target=self.emoji_player.start_thread_loop, args=(self.new_loop,),
                                                    daemon=True)
        self.emoji_player_thread.start()
        asyncio.run_coroutine_threadsafe(self.emoji_player.play_emoji(), self.new_loop)

    def set_on_play_event(self, func):
        self.song_plr.on_play = func

    def set_on_stop_event(self, func):
        self.song_plr.on_stop = func

    def set_interrupted(self, flag):
        self.song_plr.interrupted = flag

    def run(self, _msg: str = None):
        try:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.song_plr.close()
                    evt_thd_trigger.clear()  # False
                    self.pure_music_thread.join()
                    self.display_thread.join()
                    self.new_loop.close()
                    self.emoji_player_thread.join()
                    pygame.mixer.quit()
                    pygame.quit()
            if len(self.song_list.song_dicts) != 0:
                command = _msg
                if command.startswith("点歌"):
                    if self.song_plr.playing:
                        print("正在播放，不可换歌！")
                    else:
                        query = command[2:]
                        if -1 != self.song_list.cur_song_index:
                            self.song_plr.stop()

                        success = self.song_plr.play(query)
                        self.is_thd_started = success

                elif command.startswith("666切歌"):
                    if self.song_plr.playing:
                        self.song_plr.stop()
                    else:
                        print("请先'点歌X'(如:点歌8/点歌Win)")
                elif command == "#打断唱歌":
                    self.set_interrupted(True)
                elif command == "#继续唱歌":
                    self.set_interrupted(False)
                elif "666辣条" == command:
                    self.song_plr.set_volume(vox_volume=0.0, bgm_volume=0.8)
                elif "666歌唱" == command:
                    self.song_plr.set_volume(vox_volume=1.0, bgm_volume=1.0)
                elif "666暂停" == command:
                    self.song_plr.pause()
                elif "666继续" == command:
                    self.song_plr.resume()
                elif "666退出" == command:
                    if self.is_thd_started:
                        self.song_plr.close()
                    evt_thd_trigger.clear()  # False
                    self.pure_music_thread.join()
                    self.display_thread.join()
                    self.new_loop.close()
                    self.emoji_player_thread.join()
                    pygame.mixer.quit()
                    pygame.quit()
                else:
                    print("无效命令！")
            else:
                print("歌单为空！")
                evt_thd_trigger.clear()  # False
                self.pure_music_thread.join()
                self.display_thread.join()
                self.new_loop.close()
                self.emoji_player_thread.join()
                pygame.mixer.quit()
                pygame.quit()
        except Exception as e:
            print(f"报menu错:{e}")
            self.song_plr.close()
            evt_thd_trigger.clear()  # False
            self.pure_music_thread.join()
            self.display_thread.join()
            self.new_loop.close()
            self.emoji_player_thread.join()
            pygame.mixer.quit()
            pygame.quit()

    def cmd_menu(self):
        while True:
            try:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.song_plr.close()
                        evt_thd_trigger.clear()  # False
                        self.pure_music_thread.join()
                        self.display_thread.join()
                        self.new_loop.close()
                        self.emoji_player_thread.join()
                        pygame.mixer.quit()
                        pygame.quit()
                if len(self.song_list.song_dicts) != 0:
                    command = input("请输入命令：点歌X(X:歌名/序号) 切歌 辣条 歌唱 暂停 继续 退出")
                    if command.startswith("点歌"):
                        query = command[2:]
                        if self.song_plr.playing:
                            self.song_plr.stop()

                        success = self.song_plr.play(query)
                        self.is_thd_started = success

                    elif command.startswith("切歌"):
                        if self.song_plr.playing:
                            self.song_plr.stop()
                        else:
                            print("请先'点歌X'(如:点歌8/点歌Win)")
                    elif "辣条" == command:
                        self.song_plr.set_volume(vox_volume=0.0, bgm_volume=0.8)
                    elif "歌唱" == command:
                        self.song_plr.set_volume(vox_volume=1.0, bgm_volume=1.0)
                    elif "暂停" == command:
                        self.song_plr.pause()
                    elif "继续" == command:
                        self.song_plr.resume()
                    elif "退出" == command:
                        if self.is_thd_started:
                            self.song_plr.close()
                        evt_thd_trigger.clear()  # False
                        self.pure_music_thread.join()
                        self.display_thread.join()
                        self.new_loop.close()
                        self.emoji_player_thread.join()
                        pygame.mixer.quit()
                        pygame.quit()
                        break
                    else:
                        print("无效命令！")
                else:
                    print("歌单为空！")
                    evt_thd_trigger.clear()  # False
                    self.pure_music_thread.join()
                    self.display_thread.join()
                    self.new_loop.close()
                    self.emoji_player_thread.join()
                    pygame.mixer.quit()
                    pygame.quit()
                    break
            except Exception as e:
                print(f"报menu错:{e}")
                self.song_plr.close()
                evt_thd_trigger.clear()  # False
                self.pure_music_thread.join()
                self.display_thread.join()
                self.new_loop.close()
                self.emoji_player_thread.join()
                pygame.mixer.quit()
                pygame.quit()
                break


class SongSingerProcess(multiprocessing.Process):
    def __init__(self, sing_queue, cmd_queue, event_init):
        super().__init__()
        self.sing_queue = sing_queue
        self.cmd_queue = cmd_queue
        self.event_init = event_init

        # self.enable_audio_stream_virtual = multiprocessing.Value(ctypes.c_bool, True)

    def run(self):
        song_mixer = SongMixer()
        song_mixer.run_threads()
        proc_name = self.name
        print(f"Initializing {proc_name}...")

        song_mixer.set_on_play_event(self.on_start_singing)
        song_mixer.set_on_stop_event(self.on_stop_singing)

        self.event_init.set()

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    song_mixer.song_plr.close()
                    evt_thd_trigger.clear()  # False
                    song_mixer.pure_music_thread.join()
                    song_mixer.display_thread.join()
                    song_mixer.new_loop.close()
                    song_mixer.emoji_player_thread.join()
                    pygame.mixer.quit()
                    pygame.quit()

            print(f"{proc_name} is working...")
            # if not self.sing_queue.empty():
            print("Singer gets a task from sing_queue.")
            cmd_sing = self.sing_queue.get()
            if cmd_sing is None:
                print(f"{proc_name}: Exiting")
                song_mixer.song_plr.close()
                evt_thd_trigger.clear()
                song_mixer.pure_music_thread.join()
                song_mixer.display_thread.join()
                song_mixer.new_loop.close()
                song_mixer.emoji_player_thread.join()
                pygame.mixer.quit()
                pygame.quit()
                break

            song_mixer.run(cmd_sing)

    def on_start_singing(self):
        self.cmd_queue.put("#唱歌开始")

    def on_stop_singing(self):
        self.cmd_queue.put("#唱歌结束")


if __name__ == '__main__':
    song_mixer = SongMixer()
    song_mixer.run_threads()
    cmd = input("输入命令1or2：1、指令菜单 2、暴力测试")
    if cmd == '1':
        song_mixer.cmd_menu()
    elif cmd == '2':
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    song_mixer.song_plr.close()
                    evt_thd_trigger.clear()  # False
                    song_mixer.pure_music_thread.join()
                    song_mixer.display_thread.join()
                    song_mixer.new_loop.close()
                    song_mixer.emoji_player_thread.join()
                    pygame.mixer.quit()
                    pygame.quit()
            x = ['切歌', '点歌', '点歌嫩叠', '点歌End', '点歌Tear']
            msg = random.sample(x, 1)[0]
            print(f"当前弹幕：{msg}")
            song_mixer.run(msg)
            time.sleep(1)
    else:
        print("无效命令！！！")
