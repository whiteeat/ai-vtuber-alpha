import multiprocessing
import ctypes
import random
import threading
import pyaudio
import pygame
import wave
import os
import time


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

    def __init__(self, song_list: SongList, is_vox: bool):
        self.song_list = song_list
        self.is_vox = is_vox
        self.virtual_audio_output_device_index = None
        self.virtual_audio_input_device_index = None
        self.virtual_audio_devices_are_found = False
        self.search_name = None
        self.pau = pyaudio.PyAudio()
        self.get_device_indices()
        self.song_dict = None
        self.wavefile = None
        self.stream = None
        self.volume = 1.0
        self.playing = False
        self.paused = False
        self.stream_thread = threading.Thread(target=self.stream_audio)

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

    def change_volume(self, data) -> bytes:
        volume = min(1.0, max(0.0, self.volume))
        data = bytearray(data)
        for i in range(0, len(data), 2):
            sample = int.from_bytes(data[i:i + 2], byteorder='little', signed=True)
            sample = int(sample * volume)
            data[i:i + 2] = sample.to_bytes(2, byteorder='little', signed=True)
        return bytes(data)

    def stream_audio(self):
        if self.virtual_audio_devices_are_found and self.is_vox:
            self.wavefile = wave.open(self.song_dict['vox'], 'rb')
            self.stream = self.pau.open(format=self.pau.get_format_from_width(self.wavefile.getsampwidth()),
                                        channels=self.wavefile.getnchannels(),
                                        rate=self.wavefile.getframerate(),
                                        output=True,  # 测试时耳机播
                                        output_device_index=self.virtual_audio_output_device_index)
        elif self.virtual_audio_devices_are_found and not self.is_vox:
            self.wavefile = wave.open(self.song_dict['bgm'], 'rb')
            self.stream = self.pau.open(format=self.pau.get_format_from_width(self.wavefile.getsampwidth()),
                                        channels=self.wavefile.getnchannels(),
                                        rate=self.wavefile.getframerate(),
                                        output=True)
        data = self.wavefile.readframes(self.CHUNK)
        while self.playing and data:
            if not self.paused:
                data = self.change_volume(data)
                self.stream.write(data)
                data = self.wavefile.readframes(self.CHUNK)
        self.wavefile.rewind()
        self.stream.close()
        self.playing = False
        self.song_list.cur_song_index = -1

    def play(self, query: str):
        self.song_dict = self.song_list.search_song(query)
        if self.song_dict:
            self.playing = True
            self.stream_thread = threading.Thread(target=self.stream_audio)
            self.stream_thread.start()
            print(f"SONG:{self.song_dict['name']} is playing...")

    def set_volume(self, volume):
        self.volume = volume

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


class Display:
    def __init__(self, song_list: SongList):
        pygame.init()
        self.song_list = song_list
        self.font = pygame.font.SysFont('SimHei', 28)
        self.screen_width = 960
        self.screen_height = 720
        self.clock = pygame.time.Clock()
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("优俊歌者")

    def draw_cur_song_name(self):
        y = 20
        cur_show_index = self.song_list.cur_song_index
        if -1 == cur_show_index:
            color = (255, 255, 0)
            text = self.font.render(f"发弹幕'点歌X'(如:点歌3/点歌Tea)", True, color)
            text_rect = text.get_rect(center=(self.screen_width / 4, y))
            self.screen.blit(text, text_rect)
        else:
            color = (0, 255, 255)
            current_song = self.song_list.vox_files[cur_show_index][6:-7]
            text = self.font.render(f"★" + current_song + f"★", True, color)
            text_rect = text.get_rect(center=(self.screen_width / 5, y))
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
            y += 30

    def draw_bgm_file_list(self):
        y = 50
        for i in range(len(self.song_list.bgm_files)):
            if i == self.song_list.cur_song_index:
                color = (127, 255, 0)
            else:
                color = (255, 255, 255)
            text = self.font.render(self.song_list.bgm_files[i][6:-7], True, color)
            self.screen.blit(text, (self.screen_width / 2, y))
            y += 30

    def display_list(self):
        while True:
            try:
                self.screen.fill((0, 127, 255))
                self.draw_cur_song_name()
                self.draw_vox_file_list()
                self.draw_bgm_file_list()
                pygame.display.flip()
                self.clock.tick(30)
            except Exception as e:
                print(f"display_list报错:{e}")


class SongMixer:
    def __init__(self):
        self.song_list = SongList()
        self.vox_plr = SongPlayer(is_vox=True, song_list=self.song_list)
        self.bgm_plr = SongPlayer(is_vox=False, song_list=self.song_list)
        self.display = Display(self.song_list)
        self.display_thread = None

    def run_display(self):
        self.display_thread = threading.Thread(target=self.display.display_list, daemon=True)
        self.display_thread.start()

    def run(self, _msg: str = None):
        try:
            if self.song_list.song_dicts != [{}]:
                command = _msg
                if command.startswith("点歌"):
                    if self.vox_plr.playing or self.bgm_plr.playing:
                        print("正在播放，不可换歌！")
                    else:
                        query = command[2:]
                        if -1 != self.song_list.cur_song_index:
                            self.vox_plr.stop()
                            self.bgm_plr.stop()
                        self.vox_plr.play(query)
                        self.bgm_plr.play(query)
                elif command.startswith("666切歌"):
                    if -1 != self.song_list.cur_song_index:
                        self.vox_plr.stop()
                        self.bgm_plr.stop()
                    else:
                        print("请先'点歌X'(如:点歌3/点歌Tea)")
                elif "666辣条" == command:
                    self.vox_plr.set_volume(0.0)
                    self.bgm_plr.set_volume(0.8)
                elif "666歌唱" == command:
                    self.vox_plr.set_volume(1.0)
                    self.bgm_plr.set_volume(1.0)
                elif "666暂停" == command:
                    self.vox_plr.pause()
                    self.bgm_plr.pause()
                elif "666继续" == command:
                    self.vox_plr.resume()
                    self.bgm_plr.resume()
                elif "666退出" == command:
                    self.vox_plr.close()
                    self.bgm_plr.close()
                    self.display_thread.join()
                    pygame.quit()
                else:
                    print("无效命令！")
            else:
                self.vox_plr.close()
                self.bgm_plr.close()
                self.display_thread.join()
                pygame.quit()
                print("歌单为空！")
        except Exception as e:
            print(f"报menu错:{e}")

    def cmd_menu(self):
        while True:
            try:
                while True:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            pygame.quit()
                    break
                if self.song_list.song_dicts != [{}]:
                    command = input("请输入命令：点歌X(X:歌名/序号) 切歌 辣条 歌唱 暂停 继续 退出")
                    if command.startswith("点歌"):
                        query = command[2:]
                        if -1 != self.song_list.cur_song_index:
                            self.vox_plr.stop()
                            self.bgm_plr.stop()
                        self.vox_plr.play(query)
                        self.bgm_plr.play(query)
                    elif command.startswith("切歌"):
                        if -1 != self.song_list.cur_song_index:
                            self.vox_plr.stop()
                            self.bgm_plr.stop()
                        else:
                            print("请先'点歌X'(如:点歌3/点歌Tea)")
                    elif "辣条" == command:
                        self.vox_plr.set_volume(0.0)
                        self.bgm_plr.set_volume(0.8)
                    elif "歌唱" == command:
                        self.vox_plr.set_volume(1.0)
                        self.bgm_plr.set_volume(1.0)
                    elif "暂停" == command:
                        self.vox_plr.pause()
                        self.bgm_plr.pause()
                    elif "继续" == command:
                        self.vox_plr.resume()
                        self.bgm_plr.resume()
                    elif "退出" == command:
                        self.vox_plr.close()
                        self.bgm_plr.close()
                        self.display_thread.join()
                        pygame.quit()
                        break
                    else:
                        print("无效命令！")
                else:
                    self.vox_plr.close()
                    self.bgm_plr.close()
                    self.display_thread.join()
                    pygame.quit()
                    print("歌单为空！")
            except Exception as e:
                print(f"报menu错:{e}")


class SongSingerProcess(multiprocessing.Process):
    def __init__(self, chat_queue, thanks_queue, event_init):
        super().__init__()
        self.chat_queue = chat_queue
        self.msg = None
        self.thanks_queue = thanks_queue
        self.event_init = event_init
        self.singer = None
        self.enable_audio_stream_virtual = multiprocessing.Value(ctypes.c_bool, True)

    def run(self):
        song_mixer = SongMixer()
        song_mixer.run_display()
        proc_name = self.name
        print(f"Initializing {proc_name}...")
        self.event_init.set()
        print(f"{proc_name} is working...")
        while True:
            if not self.chat_queue.empty():
                print("Singer gets a task from chat_queue.")
                task = self.chat_queue.get()
                if task is None:
                    print(f"{proc_name}: Exiting")
                    break
                self.msg = task.message
                song_mixer.run(self.msg)
                while True:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            pygame.quit()
                    break


if __name__ == '__main__':
    song_mixer = SongMixer()
    song_mixer.run_display()
    cmd = input("输入命令1or2：1、指令菜单 2、暴力测试")
    if cmd == '1':
        song_mixer.cmd_menu()
    elif cmd == '2':
        while True:
            x = ['切歌', '点歌', '点歌嫩叠', '点歌End', '点歌Tear']
            msg = random.sample(x, 1)[0]
            print(f"当前弹幕：{msg}")
            song_mixer.run(msg)
            time.sleep(1)
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                break
    else:
        print("无效命令！！！")
