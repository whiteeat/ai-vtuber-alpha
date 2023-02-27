import sys
import multiprocessing
import ctypes

from revChatGPT.V1 import Chatbot

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
            device,
            task_queue, 
            event_enable_audio_stream,
            event_enable_audio_stream_vitrual,
            event_initialized, 
            event_is_speaking=None):
        multiprocessing.Process.__init__(self)
        self.device_str = device_str
        self.task_queue = task_queue
        self.event_enable_audio_stream = event_enable_audio_stream
        self.event_enable_audio_stream_vitrual = event_enable_audio_stream_vitrual
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

        # Maybe should use Multithreading to play audio.

        # https://people.csail.mit.edu/hubert/pyaudio/docs/
        # https://stackoverflow.com/questions/30675731/howto-stream-numpy-array-into-pyaudio-stream  
        py_audio = pyaudio.PyAudio()
        stream = py_audio.open(format=pyaudio.paFloat32,
                channels=1,
                rate=22050,
                output=True)
        
        virtual_audio_input_device_index = None
        virtual_audio_output_device_index = None

        # Search for valid virtual audio input and output devices
        for i in range(py_audio.get_device_count()):
            device_info = py_audio.get_device_info_by_index(i)
            if ("CABLE Output" in device_info['name'] and
                device_info['hostApi'] == 0):
                assert device_info['index'] == i 
                virtual_audio_input_device_index = i
            
            if ("CABLE Input" in device_info['name'] and
                device_info['hostApi'] == 0):
                assert device_info['index'] == i
                virtual_audio_output_device_index = i

        virtual_audio_devices_are_found = True
        if (virtual_audio_input_device_index is None or
            virtual_audio_output_device_index is None):
            print("Error: no valid virtual audio devices found!!!")
            virtual_audio_devices_are_found = False

        if virtual_audio_devices_are_found:
            stream_virtual = py_audio.open(format=pyaudio.paFloat32,
                    channels=1,
                    rate=22050,
                    output=True,
                    output_device_index=virtual_audio_output_device_index)

        print("PYAudio is initialized.")

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

                data = audio.astype(np.float32).tostring()
                if self.event_enable_audio_stream.is_set():
                    stream.write(data)
                
                if (self.event_enable_audio_stream_vitrual.is_set() and
                    virtual_audio_devices_are_found):
                    stream_virtual.write(data)
                
            except Exception as e:
                print(e)
                # print(f"Errors ocurrs in the process {proc_name}")
            finally:
                self.task_queue.task_done()
                if self.event_is_speaking is not None:
                    self.event_is_speaking.clear()

        stream.close()
        py_audio.terminate()
        return

class VITSTask:
    def __init__(self, text, language=0, speaker_id=2, noise_scale=0.5, noise_scale_w=0.5, length_scale=1.0):
        self.text = text
        self.language = language
        self.sid = speaker_id
        self.noise_scale = noise_scale
        self.noise_scale_w = noise_scale_w
        self.length_scale = length_scale

# Use your own token
access_token = ""

class ChatGPTProcess(multiprocessing.Process):
    def __init__(self, access_token, prompt_qeue, vits_task_queue, event_enable_vits, event_initialized):
        super().__init__()
        self.access_token = access_token
        self.prompt_qeue = prompt_qeue
        self.vits_task_queue = vits_task_queue
        self.event_enable_vits = event_enable_vits
        self.event_initialized = event_initialized

        self.use_streamed = multiprocessing.Value(ctypes.c_bool, False)

    def set_streamed_enabled(self, value):
        self.use_streamed.value = value

    def is_streamed_enabled(self):
        return self.use_streamed.value 

    def run(self):
        proc_name = self.name
        print(f"Initializing {proc_name}...")

        chatbot = Chatbot(config={'access_token': self.access_token})

        self.event_initialized.set()

        while True:
            print(f"{proc_name} is working...")
            response = ""
            prompt = self.prompt_qeue.get()
            if prompt is None:
                # Poison pill means shutdown
                print(f"{proc_name}: Exiting")
                break
            
            if not self.is_streamed_enabled():
                for data in chatbot.ask(prompt):
                    response = data["message"]
                print(response)
                if self.event_enable_vits.is_set():
                    vits_task = VITSTask(response)
                    self.vits_task_queue.put(vits_task)
            else:
                # WIP...
                prev_text = ""
                for data in chatbot.ask(prompt):
                    message = data["message"][len(prev_text):]
                    print(message, end="", flush=True)
                    prev_text = data["message"]

                    if self.event_enable_vits.is_set():
                        vits_task = VITSTask(message)
                        self.vits_task_queue.put(vits_task)

class BarragePollingProcess(multiprocessing.Process):
    def __init__(self, roomd_id, prompt_qeue, event_enable_polling, event_initialized, event_stop):
        super().__init__()
        self.room_id = roomd_id
        self.prompt_qeue = prompt_qeue
        self.event_enable_polling = event_enable_polling
        self.event_initialized = event_initialized
        self.event_stop = event_stop

        self.info_last = None
        # https://stackoverflow.com/questions/32822013/python-share-values
        self.enable_logging = multiprocessing.Value(ctypes.c_bool, False)
        url = "http://api.live.bilibili.com/ajax/msg?roomid="
        self.url = url + self.room_id

    def set_logging_enabled(self, value):
        self.enable_logging.value = value

    def is_logging_enabled(self):
        return self.enable_logging.value

    def get_barrage(self):
        res = requests.get(self.url).json()
        if self.enable_logging.value:
            print(f"Response: {res}")
        info_last = res['data']['room'][-1]
        if self.enable_logging.value:
            print(f"The last room info: {info_last}")
        if info_last == self.info_last:
            print(f"The room info polled is the same as the last one!")
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
            if self.event_enable_polling.is_set():
                print(f"{proc_name} is working...")
                try:
                    barrage_last = self.get_barrage()
                    if len(barrage_last) != 0:
                        self.prompt_qeue.put(barrage_last)
                    else:
                        print("Warning: empty barrage message!")

                    self.barrage_last = barrage_last
                    
                except Exception as e:
                    print(e)
            
            if self.event_stop.is_set():
                print(f"{proc_name}: Exiting")
                break

            time.sleep(0.5)


if __name__ == '__main__':
    vits_task_queue = multiprocessing.JoinableQueue()
    prompt_qeue = multiprocessing.Queue()
    event_enable_vits = multiprocessing.Event()
    event_chat_gpt_process_initialized = multiprocessing.Event()
    # event_enable_vits.set()

    chat_gpt_process = ChatGPTProcess(access_token, prompt_qeue, vits_task_queue, event_enable_vits, event_chat_gpt_process_initialized)
    chat_gpt_process.start()

    event_enable_audio_stream = multiprocessing.Event()
    event_enable_audio_stream_vitrual = multiprocessing.Event()
    event_enable_audio_stream.set()
    event_enable_audio_stream_vitrual.set()
    event_vits_process_initialized = multiprocessing.Event()
    event_is_speaking = multiprocessing.Event()

    # Or cpu
    device_str = 'cuda'

    vits_process = VITSProcess(
                            device_str,
                            vits_task_queue,  
                            event_enable_audio_stream,
                            event_enable_audio_stream_vitrual,
                            event_vits_process_initialized,
                            event_is_speaking)
    vits_process.start()

    room_id = "14655481"
    event_enable_barrage_polling = multiprocessing.Event()
    event_barrage_polling_process_initialized = multiprocessing.Event()
    event_barrage_polling_process_stop = multiprocessing.Event()

    barrage_polling_process = BarragePollingProcess(room_id, prompt_qeue, event_enable_barrage_polling, event_barrage_polling_process_initialized, event_barrage_polling_process_stop)
    barrage_polling_process.start()

    event_vits_process_initialized.wait()
    event_chat_gpt_process_initialized.wait()
    event_barrage_polling_process_initialized.wait()

    while True:
        user_input = input("Please enter commands:\n")
        if user_input == 'esc':
            break
        elif user_input == '0':
            if event_enable_vits.is_set():
                event_enable_vits.clear()
                print("Disable VITS")
            else:
                event_enable_vits.set()
                print("Enable VITS")
        elif user_input == '1':
            if event_enable_audio_stream.is_set():
                event_enable_audio_stream.clear()
                print("Disable Audio stream")
            else:
                event_enable_audio_stream.set()
                print("Enable Audio stream")
        elif user_input == '2':
            if event_enable_audio_stream_vitrual.is_set():
                event_enable_audio_stream_vitrual.clear()
                print("Disable virtual audio stream")
            else:
                event_enable_audio_stream_vitrual.set()
                print("Enable virtual audio stream")
        elif user_input == '3':
            if event_enable_barrage_polling.is_set():
                event_enable_barrage_polling.clear()
                print("Disable barrage polling")
            else:
                event_enable_barrage_polling.set()
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
                print("Disable chatgpt streamed")
            else:
                chat_gpt_process.set_streamed_enabled(True)
                print("Enable chatgpt streamed")
        else:
            prompt_qeue.put(user_input)

    event_barrage_polling_process_stop.set()
    prompt_qeue.put(None)
    vits_task_queue.put(None)

    vits_process.join()
    chat_gpt_process.join()
    barrage_polling_process.join()



