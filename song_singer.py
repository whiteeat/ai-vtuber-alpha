import multiprocessing
import random
import threading
import pyaudio
import pygame
import wave
import os
import time

evt_thd_trigger = threading.Event()


class SongList:
    def __init__(self):
        self.song_dir = rf"music/"
        self.names: list = []
        self.vox_files: list = []
        self.bgm_files: list = []
        self.song_dicts: list = []  # 本地音乐字典列表：id name vox bgm
        self.load_song_files()
        self.cur_song_index = -1

    def load_song_files(self):
        file_path = self.song_dir
        for filename in os.listdir(file_path):
            if filename.endswith('.wav') or filename.endswith('.mp3'):
                if filename[:-4].endswith('Vox'):
                    self.names.append(filename[:-7])
                    filename = file_path + filename
                    self.vox_files.append(filename)
                if filename[:-4].endswith('Bgm'):
                    filename = file_path + filename
                    self.bgm_files.append(filename)
        if len(self.vox_files) == len(self.bgm_files):
            for song_index in range(len(self.vox_files)):
                song_id = song_index + 1
                self.song_dicts.append({'id': song_id,
                                        'name': self.names[song_index],
                                        'vox': self.vox_files[song_index],
                                        'bgm': self.bgm_files[song_index]})

    def search_song(self, query: str = None):
        try:
            if query is None or query == '':
                print("请输入：‘点歌X’(如：点歌1/点歌Tear)")
                return None
            else:
                if self.vox_files and self.bgm_files and self.song_dicts:
                    for song_dict in self.song_dicts:
                        if query == str(song_dict['id']):
                            self.cur_song_index = song_dict['id'] - 1
                            return song_dict
                        elif query in song_dict['vox'] and query in song_dict['bgm']:
                            self.cur_song_index = song_dict['id'] - 1
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
            vox_stream = self.pau.open(format=self.pau.get_format_from_width(vox_wave.getsampwidth()),
                                       channels=vox_wave.getnchannels(),
                                       rate=vox_wave.getframerate(),
                                       output=True,  # 测试时耳机播
                                       output_device_index=self.virtual_audio_output_device_index)
            bgm_wave = wave.open(self.song_dict['bgm'], 'rb')
            bgm_stream = self.pau.open(format=self.pau.get_format_from_width(bgm_wave.getsampwidth()),
                                       channels=bgm_wave.getnchannels(),
                                       rate=bgm_wave.getframerate(),
                                       output=True)

            while self.playing:
                if not self.paused:
                    vox_data = vox_wave.readframes(self.CHUNK)

                    if len(vox_data) != 0:
                        vox_data = self.change_volume(vox_data, self.vox_volume)
                        vox_stream.write(vox_data)
                    bgm_data = bgm_wave.readframes(self.CHUNK)

                    if len(bgm_data) != 0:
                        bgm_data = self.change_volume(bgm_data, self.bgm_volume)
                        bgm_stream.write(bgm_data)

                    if len(vox_data) == 0 and len(bgm_data) == 0:
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
            if filename.endswith('Msc.wav') or filename.endswith('Msc.mp3'):
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
        self.screen_width = 600
        self.screen_height = 720
        pygame.init()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('SimHei', 20)
        self.title_font = pygame.font.SysFont('幼圆', 22)
        self.screen = None

    def draw_cur_song_name(self):
        y = 20
        cur_show_index = self.song_list.cur_song_index
        if -1 == cur_show_index:
            color = (255, 255, 0)
            text = self.font.render(f"弹幕'点歌X'(如:点歌3/点歌Tea)", True, color)
            text_rect = text.get_rect(center=(self.screen_width / 4, y))
            self.screen.blit(text, text_rect)
        else:
            color = (0, 255, 255)
            current_song = self.song_list.vox_files[cur_show_index][6:-7]
            text = self.title_font.render(f"★" + current_song + f"★", True, color)
            text_rect = text.get_rect(center=(self.screen_width / 4, y))
            self.screen.blit(text, text_rect)

    def draw_vox_file_list(self):
        y = 50
        for i in range(len(self.song_list.vox_files)):
            if i == self.song_list.cur_song_index:
                color = (0, 255, 127)
            else:
                color = (255, 255, 255)
            text = self.font.render(f'{i + 1}.' + self.song_list.vox_files[i][6:-7], True, color)
            self.screen.blit(text, (10, y))
            y += 25

    def draw_bgm_file_list(self):
        y = 50
        for i in range(len(self.song_list.bgm_files)):
            if i == self.song_list.cur_song_index:
                color = (127, 255, 0)
            else:
                color = (255, 255, 255)
            text = self.font.render(self.song_list.bgm_files[i][6:-7], True, color)
            self.screen.blit(text, (self.screen_width / 2, y))
            y += 25

    def display_list(self):
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("优俊歌者")
        while evt_thd_trigger.isSet():  # T/F
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    evt_thd_trigger.clear()  # False
            try:
                self.screen.fill(color=(0, 127, 255))
                self.draw_cur_song_name()
                self.draw_vox_file_list()
                self.draw_bgm_file_list()
                pygame.display.update()
                self.clock.tick(30)
            except Exception as e:
                print(f"display_list报错:{e}")
                evt_thd_trigger.clear()  # False


class SongMixer:
    def __init__(self):
        self.song_list = SongList()
        self.song_plr = SongPlayer(_song_list=self.song_list)
        self.pure_music = PureMusic(self.song_list)
        self.pure_music_thread = None
        self.display = Display(self.song_list)
        self.display_thread = None

    def run_threads(self):
        evt_thd_trigger.set()  # True
        self.pure_music_thread = threading.Thread(target=self.pure_music.loop_music, daemon=True)
        self.pure_music_thread.start()
        self.display_thread = threading.Thread(target=self.display.display_list, daemon=True)
        self.display_thread.start()

    def set_on_play_event(self, func):
        self.song_plr.on_play = func

    def set_on_stop_event(self, func):
        self.song_plr.on_stop = func

    def run(self, _msg: str = None):
        try:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.song_plr.close()
                    evt_thd_trigger.clear()  # False
                    self.pure_music_thread.join()
                    self.display_thread.join()
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

                elif command.startswith("666切歌"):
                    if self.song_plr.playing:
                        self.song_plr.stop()
                    else:
                        print("请先'点歌X'(如:点歌3/点歌Tea)")
                elif "666辣条" == command:
                    self.song_plr.set_volume(vox_volume=0.0, bgm_volume=0.8)
                elif "666歌唱" == command:
                    self.song_plr.set_volume(vox_volume=1.0, bgm_volume=1.0)
                elif "666暂停" == command:
                    self.song_plr.pause()
                elif "666继续" == command:
                    self.song_plr.resume()
                elif "666退出" == command:
                    self.song_plr.close()
                    evt_thd_trigger.clear()  # False
                    self.pure_music_thread.join()
                    self.display_thread.join()
                    pygame.mixer.quit()
                    pygame.quit()
                else:
                    print("无效命令！")
            else:
                print("歌单为空！")
                evt_thd_trigger.clear()  # False
                self.pure_music_thread.join()
                self.display_thread.join()
                pygame.mixer.quit()
                pygame.quit()
        except Exception as e:
            print(f"报menu错:{e}")
            self.song_plr.close()
            evt_thd_trigger.clear()  # False
            self.pure_music_thread.join()
            self.display_thread.join()
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
                        pygame.mixer.quit()
                        pygame.quit()
                if len(self.song_list.song_dicts) != 0:
                    command = input("请输入命令：点歌X(X:歌名/序号) 切歌 辣条 歌唱 暂停 继续 退出")
                    if command.startswith("点歌"):
                        query = command[2:]
                        if self.song_plr.playing:
                            self.song_plr.stop()

                        success = self.song_plr.play(query)

                    elif command.startswith("切歌"):
                        if self.song_plr.playing:
                            self.song_plr.stop()
                        else:
                            print("请先'点歌X'(如:点歌3/点歌Tea)")
                    elif "辣条" == command:
                        self.song_plr.set_volume(vox_volume=0.0, bgm_volume=0.8)
                    elif "歌唱" == command:
                        self.song_plr.set_volume(vox_volume=1.0, bgm_volume=1.0)
                    elif "暂停" == command:
                        self.song_plr.pause()
                    elif "继续" == command:
                        self.song_plr.resume()
                    elif "退出" == command:
                        self.song_plr.close()
                        evt_thd_trigger.clear()  # False
                        self.pure_music_thread.join()
                        self.display_thread.join()
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
                    pygame.mixer.quit()
                    pygame.quit()
                    break
            except Exception as e:
                print(f"报menu错:{e}")
                self.song_plr.close()
                evt_thd_trigger.clear()  # False
                self.pure_music_thread.join()
                self.display_thread.join()
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
                    pygame.mixer.quit()
                    pygame.quit()
            x = ['切歌', '点歌', '点歌嫩叠', '点歌End', '点歌Tear']
            msg = random.sample(x, 1)[0]
            print(f"当前弹幕：{msg}")
            song_mixer.run(msg)
            time.sleep(1)
    else:
        print("无效命令！！！")
