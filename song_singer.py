import multiprocessing
import ctypes
import queue
import threading
import pyaudio
import pygame
import wave
import os
# import queue
import random
import threading
import pyaudio
import pygame
import wave
import os
import time

"""python实现：总体歌单"""


class SongList:
    def __init__(self):
        self.song_dir = rf"music/"  # 本地音乐库的路径
        self.vox_files: list = []
        self.bgm_files: list = []
        self.load_vox_files()
        self.load_bgm_files()
        self.song_files: tuple = tuple(zip(self.vox_files, self.bgm_files))

    def load_vox_files(self):
        # 获取当前目录下的所有音频文件
        file_path = self.song_dir
        for filename in os.listdir(file_path):
            if filename.endswith('Vox.wav') or filename.endswith('Vox.mp3'):
                filename = file_path + filename
                self.vox_files.append(filename)

    def load_bgm_files(self):
        # 获取当前目录下的所有音频文件
        file_path = self.song_dir
        for filename in os.listdir(file_path):
            if filename.endswith('Bgm.wav') or filename.endswith('Bgm.mp3'):
                filename = file_path + filename
                self.bgm_files.append(filename)


"""pygame实现：显示"""


class Display:
    def __init__(self, song_list):
        pygame.init()
        self.song_list = song_list
        self.font = pygame.font.SysFont('SimHei', 20)
        self.screen_width = 640
        self.screen_height = 640
        self.clock = pygame.time.Clock()
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("歌者帝宝")
        self.cur_song_index = 0

    def draw(self):
        self.screen.fill((255, 255, 255))

        current_song = self.playlist.get_current_song()

        text_surface = self.font.render(current_song, True, (0, 0, 0))
        text_rect = text_surface.get_rect(center=(self.width / 2, self.height / 2))
        self.screen.blit(text_surface, text_rect)

        pygame.display.flip()

    def draw_vox_file_list(self):
        y = 50
        for i in range(len(self.song_list.vox_files)):
            if i == self.cur_song_index:
                color = (0, 255, 127)
            else:
                color = (255, 255, 255)
            text = self.font.render(f'{i + 1}.' + self.song_list.vox_files[i][6:-7], True, color)
            self.screen.blit(text, (10, y))
            y += 20

    def draw_bgm_file_list(self):
        y = 50
        for i in range(len(self.song_list.bgm_files)):
            if i == self.cur_song_index:
                color = (127, 255, 0)
            else:
                color = (255, 255, 255)
            text = self.font.render(self.song_list.bgm_files[i][6:-7], True, color)
            self.screen.blit(text, (self.screen_width / 2, y))
            y += 20

    def display_list(self):
        # while True:
        try:
            self.screen.fill((0, 0, 255))
            self.draw_vox_file_list()
            self.draw_bgm_file_list()
            pygame.display.flip()
            self.clock.tick(30)
        except Exception as e:
            print(f"display_list报错:{e}")


"""pyaudio实现：随时播放和暂停1个wav音频"""


class SongPlayer:
    CHUNK = 1024

    def __init__(self, song_list: SongList, is_vox: bool):
        self.is_vox = is_vox
        self.audio_output_device_index = None
        self.audio_input_device_index = None
        self.audio_devices_are_found = False
        self.virtual_audio_output_device_index = None
        self.virtual_audio_input_device_index = None
        self.virtual_audio_devices_are_found = False
        self.song_list = song_list
        self.search_name = None
        self.pau = pyaudio.PyAudio()
        self.get_device_indices()
        self.is_song_found = False
        self.cur_song_file = None
        self.wavefile = None
        self.stream = None
        self.volume = 1.0
        self.playing = False
        self.paused = False
        self.thread = None

    def get_device_indices(self):
        assert self.pau is not None
        self.virtual_audio_input_device_index = None
        self.virtual_audio_output_device_index = None
        # Search for valid audio input and output devices
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
            if ("麦克风" in device_info['name'] and
                    device_info['hostApi'] == 0):
                assert device_info['index'] == i
                self.audio_input_device_index = i
            if ("扬声器" in device_info['name'] and
                    device_info['hostApi'] == 0):
                assert device_info['index'] == i
                self.audio_output_device_index = i
        if (self.virtual_audio_input_device_index is None or
                self.virtual_audio_output_device_index is None):
            print("Error: no valid virtual audio devices found!!!")
            self.virtual_audio_devices_are_found = False
        else:
            self.virtual_audio_devices_are_found = True
        if (self.audio_input_device_index is None or
                self.audio_output_device_index is None):
            print("Error: no valid audio devices found!!!")
            self.audio_devices_are_found = False
        else:
            self.audio_devices_are_found = True

    def search_song(self):
        try:
            if self.song_list.vox_files and self.song_list.bgm_files:
                self.is_song_found = False
                song_index = 0
                for filename in self.song_list.vox_files:
                    self.song_list.cur_song_index = song_index
                    if self.search_name in filename:
                        self.is_song_found = True
                        if self.is_vox:
                            self.cur_song_file = self.song_list.vox_files[self.song_list.cur_song_index]
                            print(f"VOICE:{self.cur_song_file[6:-7]} is playing...")
                        else:
                            self.cur_song_file = self.song_list.bgm_files[self.song_list.cur_song_index]
                            print(f"MUSIC:{self.cur_song_file[6:-7]} is playing...")
                        print(f"Index:{self.song_list.cur_song_index}")
                        break
                    song_index += 1
                else:
                    print("抱歉，未找到该歌曲。")
        except Exception as e:
            print(f"search_song报错:{e}")

    def change_volume(self, data):
        volume = min(1.0, max(0.0, self.volume))
        data = bytearray(data)
        for i in range(0, len(data), 2):
            sample = int.from_bytes(data[i:i + 2], byteorder='little', signed=True)
            sample = int(sample * volume)
            data[i:i + 2] = sample.to_bytes(2, byteorder='little', signed=True)
        return bytes(data)

    def stream_audio(self):
        self.wavefile = wave.open(self.cur_song_file, 'rb')
        if self.audio_devices_are_found and self.is_vox:
            self.stream = self.pau.open(format=self.pau.get_format_from_width(self.wavefile.getsampwidth()),
                                        channels=self.wavefile.getnchannels(),
                                        rate=self.wavefile.getframerate(),
                                        output=True,
                                        output_device_index=self.virtual_audio_output_device_index)  # virtual_audio_output_device_index
        elif self.virtual_audio_devices_are_found and not self.is_vox:
            self.stream = self.pau.open(format=self.pau.get_format_from_width(self.wavefile.getsampwidth()),
                                        channels=self.wavefile.getnchannels(),
                                        rate=self.wavefile.getframerate(),
                                        output=True,
                                        output_device_index=self.audio_output_device_index)
        data = self.wavefile.readframes(self.CHUNK)
        while self.playing and data:
            if not self.paused:
                data = self.change_volume(data)
                self.stream.write(data)
                data = self.wavefile.readframes(self.CHUNK)
        self.wavefile.rewind()

    def play(self, search_name: str = None):
        self.playing = True
        self.search_name = search_name
        if self.search_name == '':
            print("请输入：‘点歌歌曲名’")
        else:
            self.search_song()
            if self.is_song_found:
                self.thread = threading.Thread(target=self.stream_audio)
                self.thread.start()

    def set_volume(self, volume):
        self.volume = volume

    def stop(self):
        self.playing = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def close(self):
        self.stop()
        self.thread.join()
        self.stream.close()
        self.pau.terminate()


class SongMixer:
    def __init__(self, _msg: str = None):
        self.msg = _msg
        self.song_list = SongList()
        self.vox_plr = SongPlayer(is_vox=True, song_list=self.song_list)
        self.bgm_plr = SongPlayer(is_vox=False, song_list=self.song_list)
        self.display = Display(self.song_list)
        # self.display_thread = threading.Thread(target=self.display.display_list(), daemon=True)
        # self.run_menu_thread = threading.Thread(target=self.run_menu(), daemon=True)

    def run_menu(self):
        while True:
            try:
                if self.song_list.song_files != ():
                    self.display.display_list()
                    # command = self.msg
                    command = input("请输入命令：")
                    if command.startswith("点歌"):
                        song_name = command[2:]
                        self.vox_plr.play(song_name)
                        self.bgm_plr.play(song_name)
                    elif "切歌" in command:
                        self.vox_plr.stop()
                        self.bgm_plr.stop()
                    elif "感谢" in command:
                        self.vox_plr.set_volume(0.0)
                        self.bgm_plr.set_volume(0.8)
                    elif "歌唱" in command:
                        self.vox_plr.set_volume(1.0)
                        self.bgm_plr.set_volume(1.0)
                    elif "暂停" in command:
                        self.vox_plr.pause()
                        self.bgm_plr.pause()
                    elif "继续" in command:
                        self.vox_plr.resume()
                        self.bgm_plr.resume()
                    elif "退出" in command:
                        self.vox_plr.close()
                        self.bgm_plr.close()
                        pygame.quit()
                        break
                    else:
                        print("无效命令！")
                else:
                    print("歌单为空！")
                    break
            except Exception as e:
                print(f"报menu错:{e}")
                continue


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
        proc_name = self.name
        print(f"Initializing {proc_name}...")

        self.event_init.set()

        print(f"{proc_name} is working...")

        while True:
            if not self.chat_queue.empty():
                print("Singer gets a task from chat_queue.")
                task = self.chat_queue.get()
                if task is None:
                    # Poison pill means shutdown
                    print(f"{proc_name}: Exiting")
                    break
                self.msg = task.message
                song_mixer = SongMixer(self.msg)
                song_mixer.run_menu()


if __name__ == '__main__':
    x = ['点歌', '切歌', '点歌Tear', '点歌不知道', '点歌End', '点歌win', '点歌win']
    msg = random.sample(x, 1)[0]
    song_mixer = SongMixer(msg)
    song_mixer.run_menu()