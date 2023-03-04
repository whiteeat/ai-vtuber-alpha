import sys
import multiprocessing
import ctypes

from revChatGPT.V1 import Chatbot as ChatbotV1
from revChatGPT.V3 import Chatbot as ChatbotV3

import time
import numpy as np

from torch import no_grad, LongTensor
from torch import device as torch_device

import pyaudio

sys.path.append("vits")

import vits.utils as utils
import vits.commons as commons
from vits.models import SynthesizerTrn
from vits.text import text_to_sequence

import requests

class VITSProcess(multiprocessing.Process):
    def __init__(
            self, 
            device_str,
            task_queue, 
            result_queue,
            event_initialized, 
            event_is_speaking=None):
        multiprocessing.Process.__init__(self)
        self.device_str = device_str
        self.task_queue = task_queue # VITS inference task queue
        self.result_queue = result_queue # Audio data queue
        self.event_initialized = event_initialized
        self.event_is_speaking = event_is_speaking

    def get_text(self, text, hps):
        text_norm, clean_text = text_to_sequence(text, hps.symbols, hps.data.text_cleaners)
        if hps.data.add_blank:
            text_norm = commons.intersperse(text_norm, 0)
        text_norm = LongTensor(text_norm)
        return text_norm, clean_text
    
    def vits(self, text, language, speaker_id, noise_scale, noise_scale_w, length_scale):
        if not len(text):
            return "输入文本不能为空！", None, None
        text = text.replace('\n', ' ').replace('\r', '').replace(" ", "")
        # if len(text) > 100:
        #     return f"输入文字过长！{len(text)}>100", None, None
        if language == 0:
            text = f"[ZH]{text}[ZH]"
        elif language == 1:
            text = f"[JA]{text}[JA]"
        else:
            text = f"{text}"
        stn_tst, clean_text = self.get_text(text, self.hps_ms)

        start = time.perf_counter()
        with no_grad():
            x_tst = stn_tst.unsqueeze(0).to(self.device)
            x_tst_lengths = LongTensor([stn_tst.size(0)]).to(self.device)
            speaker_id = LongTensor([speaker_id]).to(self.device)
            audio = self.net_g_ms.infer(x_tst, x_tst_lengths, sid=speaker_id, noise_scale=noise_scale, noise_scale_w=noise_scale_w,
                                        length_scale=length_scale)[0][0, 0].data.cpu().float().numpy()
        print(f"The inference takes {time.perf_counter() - start} seconds")
            
        return audio

    def run(self):
        proc_name = self.name
        print(f"Initializing {proc_name}...")

        print(f"Using {self.device_str}")
        self.device = torch_device(self.device_str)

        self.hps_ms = utils.get_hparams_from_file(r'vits/model/config.json')
        speakers = self.hps_ms.speakers

        with no_grad():
            self.net_g_ms = SynthesizerTrn(
                len(self.hps_ms.symbols),
                self.hps_ms.data.filter_length // 2 + 1,
                self.hps_ms.train.segment_size // self.hps_ms.data.hop_length,
                n_speakers=self.hps_ms.data.n_speakers,
                **self.hps_ms.model).to(self.device)
            _ = self.net_g_ms.eval()
            model, optimizer, learning_rate, epochs = utils.load_checkpoint(r'vits/model/G_953000.pth', self.net_g_ms, None)

        print("Loading Weights finished.")

        self.event_initialized.set()

        while True:
            next_task = self.task_queue.get()
            if next_task is None:
                # Poison pill means shutdown
                print(f"{proc_name}: Exiting")
                self.task_queue.task_done()
                break
            try:
                print(f"{proc_name} is working...")
                audio = self.vits(next_task.text, next_task.language, next_task.sid, next_task.noise_scale, next_task.noise_scale_w, next_task.length_scale)

                data = audio.astype(np.float32).tobytes()

                task = AudioTask(data)
                self.result_queue.put(task)
                
            except Exception as e:
                print(e)
                # print(f"Errors ocurrs in the process {proc_name}")
            finally:
                self.task_queue.task_done()
                if self.event_is_speaking is not None:
                    self.event_is_speaking.clear()

class VITSTask:
    def __init__(self, text, language=0, speaker_id=2, noise_scale=0.5, noise_scale_w=0.5, length_scale=1.0):
        self.text = text
        self.language = language
        self.sid = speaker_id
        self.noise_scale = noise_scale
        self.noise_scale_w = noise_scale_w
        self.length_scale = length_scale

class AudioTask:
    def __init__(self, data):
        self.data = data

class AudioPlayerProcess(multiprocessing.Process):
    def __init__(self, task_queue, event_initalized):
        super().__init__()
        self.task_queue = task_queue
        self.event_initalized = event_initalized

        self.enable_audio_stream = multiprocessing.Value(ctypes.c_bool, True)
        self.enable_audio_stream_virtual = multiprocessing.Value(ctypes.c_bool, True)

        self.virtual_audio_devices_are_found = False # Maybe incorrect, because __init__ is run in the main thread
    
    def set_audio_stream_enabled(self, value):
        self.enable_audio_stream.value = value
    
    def is_audio_stream_enabled(self):
        return self.enable_audio_stream.value
    
    def set_enable_audio_stream_virtual(self, value):
        self.enable_audio_stream_virtual.value = value
    
    def is_audio_stream_virtual_enabled(self):
        return self.enable_audio_stream_virtual.value

    def get_virtual_audio_indices(self):
        assert self.py_audio is not None

        self.virtual_audio_input_device_index = None
        self.virtual_audio_output_device_index = None

        # Search for valid virtual audio input and output devices
        for i in range(self.py_audio.get_device_count()):
            device_info = self.py_audio.get_device_info_by_index(i)
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

    def run(self):
        proc_name = self.name
        print(f"Initializing {proc_name}...")

        # https://people.csail.mit.edu/hubert/pyaudio/docs/
        # https://stackoverflow.com/questions/30675731/howto-stream-numpy-array-into-pyaudio-stream  
        self.py_audio = pyaudio.PyAudio()
        stream = self.py_audio.open(format=pyaudio.paFloat32,
                channels=1,
                rate=22050,
                output=True)
        
        self.get_virtual_audio_indices()
        
        stream_virtual = None
        if self.virtual_audio_devices_are_found:
            stream_virtual = self.py_audio.open(format=pyaudio.paFloat32,
            channels=1,
            rate=22050,
            output=True,
            output_device_index=self.virtual_audio_output_device_index)

        print("PYAudio is initialized.")
        
        self.event_initalized.set()

        while True:
            next_task = self.task_queue.get()
            if next_task is None:
                # Poison pill means shutdown
                print(f"{proc_name}: Exiting")
                break
            try:
                print(f"{proc_name} is working...")
                data = next_task.data

                if self.is_audio_stream_enabled():
                    stream.write(data)
                
                if (self.is_audio_stream_virtual_enabled() and
                    self.virtual_audio_devices_are_found):
                    stream_virtual.write(data)
                
            except Exception as e:
                print(e)
                # print(f"Errors ocurrs in the process {proc_name}")
        
        stream.close()
        stream_virtual.close()
        self.py_audio.terminate()


# Use your own token
access_token = ""

class ChatGPTProcess(multiprocessing.Process):
    def __init__(self, access_token, api_key, prompt_qeue, vits_task_queue, event_initialized):
        super().__init__()
        self.access_token = access_token
        self.api_key = api_key
        self.prompt_qeue = prompt_qeue
        self.vits_task_queue = vits_task_queue
        self.event_initialized = event_initialized

        self.use_streamed = multiprocessing.Value(ctypes.c_bool, False)
        self.enable_vits = multiprocessing.Value(ctypes.c_bool, False)

    def set_vits_enabled(self, value):
        self.enable_vits.value = value

    def is_vits_enabled(self):
        return self.enable_vits.value

    def set_streamed_enabled(self, value):
        self.use_streamed.value = value

    def is_streamed_enabled(self):
        return self.use_streamed.value 

    def run(self):
        proc_name = self.name
        print(f"Initializing {proc_name}...")

        use_access_token = False
        use_api_key = False 
        if self.access_token is not None:
            chatbot = ChatbotV1(config={'access_token': self.access_token})
            use_access_token = True
            print("Use access token")
        elif self.api_key is not None:
            chatbot = ChatbotV3(self.api_key)
            use_api_key = True
            print("use API key")
        
        assert use_access_token or use_api_key, "Error: use_access_token and use_api_key are both False!"

        punctuations_to_split_text = set("。！？")
        punctuations_to_split_text_longer = set(",")

        min_sentence_length = 32
        sentence_longer_threshold = 64

        self.event_initialized.set()

        while True:
            response = ""
            prompt = self.prompt_qeue.get()
            print(f"{proc_name} is working...")
            if prompt is None:
                # Poison pill means shutdown
                print(f"{proc_name}: Exiting")
                break
            
            header = prompt[:32]
            if header == "#reset":
                try:
                    print("Reset ChatGPT")
                    print(preset_text)
                    if use_api_key:
                        response = chatbot.ask(preset_text)
                    elif use_access_token:
                        for data in chatbot.ask(preset_text):
                            response = data["message"]
                    print(response)
                except Exception as e:
                    print(e)
                    print("Reset fail!")
                finally:
                    continue

            try:
                if use_api_key:
                    new_sentence = ""
                    for data in chatbot.ask(prompt):
                        print(data, end="", flush=True)

                        should_split = False
                        new_sentence += data
                        if len(new_sentence) >= min_sentence_length:
                            if new_sentence[-1] in punctuations_to_split_text:
                                should_split = True
                            elif len(new_sentence) >= sentence_longer_threshold:
                                if new_sentence[-1] in punctuations_to_split_text_longer:
                                    should_split = True

                        if should_split:
                            if self.is_vits_enabled():
                                vits_task = VITSTask(new_sentence.strip())
                                self.vits_task_queue.put(vits_task)
                            new_sentence = ""
                    
                    if len(new_sentence) > 0:
                        if self.is_vits_enabled():
                            vits_task = VITSTask(new_sentence.strip())
                            self.vits_task_queue.put(vits_task)

                elif use_access_token:
                    if not self.is_streamed_enabled():
                        for data in chatbot.ask(prompt):
                            response = data["message"]
                        print(response)
                        if self.is_vits_enabled():
                            vits_task = VITSTask(response)
                            self.vits_task_queue.put(vits_task)
                    else:
                        prev_message = ""
                        prompt_is_skipped = False
                        new_sentence = ""
                        for data in chatbot.ask(
                            prompt,
                            # timeout=120
                        ):
                            message = data["message"]
                            new_words = message[len(prev_message):]
                            print(new_words, end="", flush=True)

                            if not prompt_is_skipped:
                                # The streamed response may contain the prompt,
                                # So the prompt in the streamed response should be skipped
                                new_sentence += new_words
                                if new_sentence == prompt[:len(new_sentence.strip())]:
                                    continue
                                else:
                                    prompt_is_skipped = True
                                    new_sentence = ""

                            should_do_vits = False
                            new_sentence += new_words
                            if len(new_sentence) >= min_sentence_length:
                                if new_sentence[-1] in punctuations_to_split_text:
                                    should_do_vits = True
                                elif len(new_sentence) >= sentence_longer_threshold:
                                    if new_sentence[-1] in punctuations_to_split_text_longer:
                                        should_do_vits = True
                            
                            if should_do_vits:
                                if self.is_vits_enabled():
                                    vits_task = VITSTask(new_sentence.strip())
                                    self.vits_task_queue.put(vits_task)
                                new_sentence = ""

                            prev_message = message
            except Exception as e:
                print(e)
                if self.is_vits_enabled():
                    text = "不好意思，刚才我走神了，请问你刚才说什么?"
                    task = VITSTask(text)
                    self.vits_task_queue.put(task)


class BarragePollingProcess(multiprocessing.Process):
    def __init__(self, room_id, prompt_qeue, event_initialized, event_stop):
        super().__init__()
        self.room_id = room_id
        self.prompt_qeue = prompt_qeue
        self.event_initialized = event_initialized
        self.event_stop = event_stop

        self.info_last = None

        # https://stackoverflow.com/questions/32822013/python-share-values
        self.enable_polling = multiprocessing.Value(ctypes.c_bool, False)
        self.enable_logging = multiprocessing.Value(ctypes.c_bool, False)

        url = "http://api.live.bilibili.com/ajax/msg?roomid="
        self.baseurl = 'https://api.live.bilibili.com/xlive/web-room/v1/dM/gethistory'

        self.headers = {
            'Host': 'api.live.bilibili.com',
            "User-Agent": "Mozilla / 5.0(Windows NT 10.0; Win64; x64) AppleWebKit / 537.36(KHTML, like Gecko) Chrome / 80.0.3987.122  Safari / 537.36"
        }

        # 传递的参数
        self.data = {
            'roomid': self.room_id,
            'csrf_token': '',
            'csrf': '',
            'visit_id': '',
        }

        self.url = url + self.room_id


    def getDANMU(self):
        req = requests.post(url=self.baseurl, headers=self.headers, data=self.data)
        html = req.json()
        code = html['code']

        if req.status_code == 200 and code == 0:
            dic = html['data']['room'][-1]
            name = dic['nickname']
            timeline = dic['timeline'].split(' ')[-1]
            text = dic['text']
            # msg = timeline + '' + name + ':' + text + '\n'
            msg = timeline + ' ' + name + ':' + text
            print(msg)
            return dic

    def set_polling_enabled(self, value):
        self.enable_polling.value = value

    def is_polling_enabled(self):
        return self.enable_polling.value

    def set_logging_enabled(self, value):
        self.enable_logging.value = value

    def is_logging_enabled(self):
        return self.enable_logging.value



    def get_barrage(self):
        # res = requests.get(self.url).json()
        # if self.enable_logging.value:
        #     print(f"Response: {res}")
        # info_last = res['data']['room'][-1]
        info_last = self.getDANMU()
        if self.enable_logging.value:
            print(f"The last room info: {info_last}")
        if info_last == self.info_last:
            # print(f"The room info polled is the same as the last one!")
            return ""
        else:
            self.info_last = info_last
        msg_last = info_last['text']
        print(f"The last Barrage message is: {msg_last}")
        return msg_last

    def run(self):
        proc_name = self.name
        print(f"Initializing {proc_name}...")
        
        self.event_initialized.set()

        while True:
            if self.is_polling_enabled():
                print(f"{proc_name} is working...")
                try:
                    barrage_last = self.get_barrage()
                    if len(barrage_last) != 0:
                        print(f"The Barrage put in the prompt queue is: {barrage_last}")
                        self.prompt_qeue.put(barrage_last)
                    else:
                        print("Warning: empty barrage message!")
                    
                except Exception as e:
                    print(e)
            
            if self.event_stop.is_set():
                print(f"{proc_name}: Exiting")
                break

            time.sleep(4.0)

preset_text = """我们来玩角色扮演游戏。你来扮演赛马娘（Umamusume）中的东海帝皇（Tokai Teio）。下面这段话是东海帝皇的相关人设资料，请阅读并理解：

东海帝王（トウカイテイオー，Tōkai Teiō）是赛马娘 Pretty Derby第一季的第三主角，也是第二季的主角。
她是一个活泼的赛马娘，非常崇拜鲁道夫象征，希望加入Team Rigil，并且她的目标是获得日本三冠王称号。她经常以非成员的身份与Team Spica混在一起。在与该团队的几次活动之后，重新考虑过后，她转而加入了Team Spica。

身材小巧，开朗活泼，有着闪闪发亮的夺目笑容的美少女马娘。能歌善舞，由于身体轻巧，脚步也很轻盈，那跳跃般的独特步法被称作“帝王舞步”。性格争强好胜，略有些傲慢。自尊心很强，面对比赛的热情比任何人都要强烈。学生会成员，憧憬着前辈鲁道夫象征，以鲁道夫的成就为目标努力。使用男性常用的自称ぼく(boku)。

她是一个身材矮小的赛马娘，有一头琥珀色的长发，用粉红色的丝带扎成马尾，她的刘海里还有一缕白色的头发，稍长一些。她的右耳上有一个带有两条丝带尾巴的琥珀色珠宝。她的眼睛颜色是天蓝色。

资料内容结束。请你从现在开始扮演东海帝皇，假设正在b站上做直播和观众聊天，我是一个正在用弹幕和你互动的观众。咱俩用第一人称方式互相对话，你说话的风格要像闲聊，然后尽量用中文，尽量每次说话不超过五十个字，一定不要超过一百字，严格执行，可以吗？如果可以，游戏就现在开始。"""


if __name__ == '__main__':
    room_id = "14655481"
    prompt_qeue = multiprocessing.Queue()

    event_barrage_polling_process_initialized = multiprocessing.Event()
    event_barrage_polling_process_stop = multiprocessing.Event()

    barrage_polling_process = BarragePollingProcess(room_id, prompt_qeue, event_barrage_polling_process_initialized, event_barrage_polling_process_stop)
    barrage_polling_process.start()

    vits_task_queue = multiprocessing.JoinableQueue()

    event_chat_gpt_process_initialized = multiprocessing.Event()

    api_key = ""
    chat_gpt_process = ChatGPTProcess(None, api_key, prompt_qeue, vits_task_queue, event_chat_gpt_process_initialized)
    chat_gpt_process.start()

    audio_task_queue = multiprocessing.Queue()

    event_vits_process_initialized = multiprocessing.Event()
    event_is_speaking = multiprocessing.Event()

    # Or cpu
    device_str = 'cuda'

    vits_process = VITSProcess(
                            device_str,
                            vits_task_queue,
                            audio_task_queue,
                            event_vits_process_initialized,
                            event_is_speaking)
    vits_process.start()

    event_audio_player_process_initialized = multiprocessing.Event()
    audio_player_process = AudioPlayerProcess(audio_task_queue, event_audio_player_process_initialized)
    audio_player_process.start()

    event_vits_process_initialized.wait()
    event_chat_gpt_process_initialized.wait()
    event_barrage_polling_process_initialized.wait()
    event_audio_player_process_initialized.wait()

    while True:
        user_input = input("Please enter commands:\n")
        if user_input == 'esc':
            break
        elif user_input == '0':
            if chat_gpt_process.is_vits_enabled():
                chat_gpt_process.set_vits_enabled(False)
                print("Disable VITS")
            else:
                chat_gpt_process.set_vits_enabled(True)
                print("Enable VITS")
        elif user_input == '1':
            if audio_player_process.is_audio_stream_enabled():
                audio_player_process.set_audio_stream_enabled(False)
                print("Disable Audio stream")
            else:
                audio_player_process.set_audio_stream_enabled(True)
                print("Enable Audio stream")
        elif user_input == '2':
            if audio_player_process.is_audio_stream_virtual_enabled():
                audio_player_process.set_enable_audio_stream_virtual(False)
                print("Disable virtual audio stream")
            else:
                audio_player_process.set_enable_audio_stream_virtual(True)
                print("Enable virtual audio stream")
        elif user_input == '3':
            if barrage_polling_process.is_polling_enabled():
                barrage_polling_process.set_polling_enabled(False)
                print("Disable barrage polling")
            else:
                barrage_polling_process.set_polling_enabled(True)
                print("Enable barrage polling")
        elif user_input == '4':
            if barrage_polling_process.is_logging_enabled():
                barrage_polling_process.set_logging_enabled(False)
                print("Disable barrage polling logging")
            else:
                barrage_polling_process.set_logging_enabled(True)
                print("Enable barrage polling logging")
        elif user_input == '5':
            if chat_gpt_process.is_streamed_enabled():
                chat_gpt_process.set_streamed_enabled(False)
                print("Disable chatGPT streamed")
            else:
                chat_gpt_process.set_streamed_enabled(True)
                print("Enable ChatGPT streamed")
        elif user_input == '8':
            print("Reset ChatGPT")
            prompt_qeue.put("#reset")
        elif user_input == '9':
            print("Test VITS and audio player")
            test_text = "测试语音合成和音频播放。"
            vits_task_queue.put(VITSTask(test_text))
        else:
            prompt_qeue.put(user_input)

    event_barrage_polling_process_stop.set()
    prompt_qeue.put(None)
    vits_task_queue.put(None)
    audio_task_queue.put(None)

    vits_process.join()
    chat_gpt_process.join()
    barrage_polling_process.join()



