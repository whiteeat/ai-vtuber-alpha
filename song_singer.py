import multiprocessing
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
        self.stream_thread = None
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

            self.playing = True

            bgm_wave = wave.open(self.song_dict['bgm'], 'rb')
            vox_wave = wave.open(self.song_dict['vox'], 'rb')
            stream_bgm = self.pau.open(format=self.pau.get_format_from_width(bgm_wave.getsampwidth()),
                            channels=bgm_wave.getnchannels(),
                            rate=bgm_wave.getframerate(),
                            output=True)

            stream_vox = self.pau.open(format=self.pau.get_format_from_width(vox_wave.getsampwidth()),
                                       channels=vox_wave.getnchannels(),
                                       rate=vox_wave.getframerate(),
                                       output=True)
        
            stream_virtual = self.pau.open(format=self.pau.get_format_from_width(vox_wave.getsampwidth()),
                        channels=vox_wave.getnchannels(),
                        rate=vox_wave.getframerate(),
                        output=True,  # 测试时耳机播
                        output_device_index=self.virtual_audio_output_device_index)
            
            junk = None
            init_junk = True
            while self.playing:
                if not self.paused:
                    bgm_data = bgm_wave.readframes(self.CHUNK)
                    vox_data = vox_wave.readframes(self.CHUNK)
                    bgm_size = len(bgm_data)
                    vox_size = len(vox_data)
                    
                    if init_junk:
                        junk = bytes(vox_size)
                        init_junk = False

                    if bgm_size != 0:
                        stream_bgm.write(bgm_data)
                    if vox_size != 0:
                        if self.interrupted:
                            stream_vox.write(junk)
                        else:
                            stream_vox.write(vox_data)
                            # Write vox data into virtual audio device to drive lip sync animation
                            stream_virtual.write(vox_data)

                    if vox_size == 0 and bgm_size == 0:
                        break
                else:
                    time.sleep(0.1)

            vox_wave.close()
            bgm_wave.close()
            stream_vox.close()
            stream_bgm.close()
            self.playing = False
            self.song_list.cur_song_index = -1

            if self.on_stop is not None:
                self.on_stop()

    def play(self, query: str):
        self.song_dict = self.song_list.search_song(query)

        success = False
        if self.song_dict:
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
        self.loop_thread = None
        self.looping = False

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
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.fadeout(1000)

    def start(self):
        self.loop_thread = threading.Thread(target=self.loop_music, daemon=True)
        self.loop_thread.start()

    def loop_music(self):
        if not self.music_files:
            print("无纯音乐文件！")
        else:
            self.looping = True
            first_time = True
            while self.looping:
                try:
                    if -1 == self.song_list.cur_song_index:
                        if first_time:
                            self.play()
                            first_time = False
                        if not pygame.mixer.music.get_busy():
                            self.next()
                    else:  # the song is playing
                        self.stop()
                        first_time = True
                    time.sleep(0.5)
                except Exception as e:
                    print(f"loop_music报错:{e}")
                    self.looping = False
    
    def quit(self):
        self.looping = False

        if self.loop_thread is not None and self.loop_thread.is_alive():
            self.loop_thread.join()
        
        pygame.mixer.quit()
        

class Display:
    def __init__(self, song_list: SongList):
        self.song_list = song_list
        # self.screen_width = 620
        self.screen_width = 1024
        self.screen_height = 360
        pygame.init()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('SimHei', 40)
        self.title_font = pygame.font.SysFont('幼圆', 48)
        self.screen = None
        self.pos_y = self.screen_height / 2

        self.display_thread = None
        self.is_running = False

    def draw_cur_song_name(self):
        y = 30
        pygame.draw.rect(self.screen, (0, 0, 0), (0, 0, 620, 100), width=0)
        cur_show_index = self.song_list.cur_song_index
        if -1 == cur_show_index:
            color = (255, 255, 0)
            text = self.font.render(f"发弹幕\"点歌+序号\"点歌（如:点歌3）", True, color)
            # text = self.font.render(f"弹幕'点歌X'(如:点歌3/点歌爱你)", True, color)
            self.screen.blit(text, (10, y))
        else:
            color = (0, 255, 255)
            abbr = self.song_list.song_dicts[cur_show_index]['abbr']
            editor = self.song_list.song_dicts[cur_show_index]['editor']
            if editor == '_':
                title = abbr
            else:
                title = abbr + ' ' + editor
            text = self.title_font.render(f"★" + title + f"★", True, color)
            self.screen.blit(text, (10, y))

    def draw_vox_file_list(self, _y):
        for i in range(len(self.song_list.song_dicts)):
            if i == self.song_list.cur_song_index:
                color = (0, 255, 127)
            else:
                color = (255, 255, 255)
            text = self.font.render(f'{i + 1}.' + self.song_list.song_dicts[i]['abbr'], True, color)
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
            text = self.font.render(self.song_list.song_dicts[i]['abbr'], True, color)
            self.screen.blit(text, (self.screen_width / 2, y))
            y += 25

    def start(self):
        self.display_thread = threading.Thread(target=self.display_list, daemon=True)
        self.display_thread.start()

    def quit(self):
        self.is_running = False

        if self.display_thread is not None and self.display_thread.is_alive():
            self.display_thread.join()

    def display_list(self):
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("优俊歌者")
        y = self.pos_y
        self.is_running = True
        while self.is_running:  # T/F
            try:
                y -= 2
                if y < len(self.song_list.song_dicts) * -40:
                    y = self.pos_y
                self.screen.fill(color=(0, 0, 0))
                self.draw_vox_file_list(y)
                # self.draw_bgm_file_list()
                self.draw_cur_song_name()
                pygame.display.update()

                # https://stackoverflow.com/questions/28206034/pygame-window-not-responding-when-clicked
                # https://stackoverflow.com/questions/44254458/pygame-needs-for-event-in-pygame-event-get-in-order-not-to-crash
                # pygame.event.pump()
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()

                self.clock.tick(30)
            except Exception as e:
                print(f"display_list报错:{e}")
                self.is_running = False  # False


class SongMixer:
    def __init__(self):
        self.song_list = SongList()
        self.song_plr = SongPlayer(_song_list=self.song_list)
        self.pure_music = PureMusic(self.song_list)
        self.display = Display(self.song_list)

    def run_threads(self):
        self.pure_music.start()
        self.display.start()

    def set_on_play_event(self, func):
        self.song_plr.on_play = func

    def set_on_stop_event(self, func):
        self.song_plr.on_stop = func

    def set_interrupted(self, flag):
        self.song_plr.interrupted = flag

    def close(self):
        self.display.quit()
        self.pure_music.quit()
        self.song_plr.close()

    def run(self, _msg: str = None):
        should_exit = False
        try:
            if len(self.song_list.song_dicts) != 0:
                command = _msg
                if command.startswith("点歌"):
                    if self.song_plr.playing:
                        print("正在播放，不可换歌！")
                    else:
                        query = command[2:]
                        if -1 != self.song_list.cur_song_index:
                            self.song_plr.stop()

                        self.song_plr.play(query)

                elif command.startswith("#切歌"):
                    if self.song_plr.playing:
                        self.song_plr.stop()
                    else:
                        print("请先'点歌X'(如:点歌8/点歌Win)")
                elif command == "#打断唱歌":
                    self.set_interrupted(True)
                elif command == "#继续唱歌":
                    self.set_interrupted(False)
                elif "#暂停" == command:
                    self.song_plr.pause()
                elif "#继续" == command:
                    self.song_plr.resume()
                elif "#退出" == command:
                    should_exit = True
                else:
                    print("无效命令！")
            else:
                print("歌单为空！")
                should_exit = True
        except Exception as e:
            print(f"报menu错:{e}")
            should_exit = True
        finally:
            return should_exit

    def cmd_menu(self):
        while True:
            try:
                if len(self.song_list.song_dicts) != 0:
                    command = input("请输入命令：点歌X(X:歌名/序号) 切歌 辣条 歌唱 暂停 继续 退出")
                    if command == "esc":
                        break
                    should_exit = self.run(command)
                    if should_exit:
                        break
                else:
                    print("歌单为空！")
                    break
            except Exception as e:
                print(f"报menu错:{e}")
                break

        self.close()


class SongSingerProcess(multiprocessing.Process):
    def __init__(self, sing_queue, cmd_queue, event_init):
        super().__init__()
        self.sing_queue = sing_queue
        self.cmd_queue = cmd_queue
        self.event_init = event_init

    def run(self):
        song_mixer = SongMixer()
        song_mixer.run_threads()
        proc_name = self.name
        print(f"Initializing {proc_name}...")

        song_mixer.set_on_play_event(self.on_start_singing)
        song_mixer.set_on_stop_event(self.on_stop_singing)

        self.event_init.set()

        while True:
            print(f"{proc_name} is working...")
            # if not self.sing_queue.empty():
            cmd_sing = self.sing_queue.get()
            print("Singer gets a task from sing_queue.")
            if cmd_sing is None:
                print(f"{proc_name}: Exiting")
                break

            song_mixer.run(cmd_sing)

        song_mixer.close()

    def on_start_singing(self):
        self.cmd_queue.put("#唱歌开始")

    def on_stop_singing(self):
        self.cmd_queue.put("#唱歌结束")


class SongSingerTestProcess(multiprocessing.Process):
    def __init__(self, sing_queue):
        super().__init__()
        self.sing_queue = sing_queue

    def run(self):
        song_mixer = SongMixer()
        song_mixer.run_threads()
        proc_name = self.name
        print(f"Initializing {proc_name}...")

        while True:
            print(f"{proc_name} is working...")
            cmd_sing = self.sing_queue.get()
            print("Singer gets a task from sing_queue.")
            if cmd_sing is None:
                print(f"{proc_name}: Exiting")
                break

            should_exit = song_mixer.run(cmd_sing)
            if should_exit:
                break

        song_mixer.close()


if __name__ == '__main__':
    sing_queue = multiprocessing.Queue(maxsize=4)

    song_singer_test_process = SongSingerTestProcess(sing_queue)

    song_singer_test_process.start()

    cmd = input("输入命令1or2：1、指令菜单 2、暴力测试")

    if cmd == '1':
        while True:
            cmd = input("请输入命令：点歌X(X:歌名/序号) #切歌 #暂停 #继续 #退出")
            sing_queue.put(cmd)
            
            if not song_singer_test_process.is_alive():
                break

    elif cmd == '2':
        count = 8
        while True:
            x = ['#切歌', '点歌End', '点歌Tear']
            msg = random.sample(x, 1)[0]
            print(f"当前弹幕：{msg}")
            sing_queue.put(msg)
            time.sleep(1)
            count = count - 1
            if count == 0:
                sing_queue.put(None)
                break 
    else:
        print("无效命令！！！")
        sing_queue.put(None)

    print("退出")