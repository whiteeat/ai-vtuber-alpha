import sys
import multiprocessing

import time
import numpy as np

from torch import no_grad, LongTensor

import pyaudio

import asyncio

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib
import json

import requests

sys.path.append("vits")

import vits.utils as utils
import vits.commons as commons
from vits.models import SynthesizerTrn
from vits.text import text_to_sequence


class VITSProcess(multiprocessing.Process):
    def __init__(self, task_queue, result_queue, event_initialized, event_all_tasks_fininished=None):
        multiprocessing.Process.__init__(self)
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.event_initialized = event_initialized
        self.event_all_tasks_fininished = event_all_tasks_fininished

        # self.hps_ms = utils.get_hparams_from_file(r'./model/config.json')
        # speakers = self.hps_ms.speakers

        # with no_grad():
        #     self.net_g_ms = SynthesizerTrn(
        #         len(self.hps_ms.symbols),
        #         self.hps_ms.data.filter_length // 2 + 1,
        #         self.hps_ms.train.segment_size // self.hps_ms.data.hop_length,
        #         n_speakers=self.hps_ms.data.n_speakers,
        #         **self.hps_ms.model)
        #     _ = self.net_g_ms.eval()
        #     model, optimizer, learning_rate, epochs = utils.load_checkpoint(r'./model/G_953000.pth', self.net_g_ms, None)

    def get_text(self, text, hps):
        text_norm, clean_text = text_to_sequence(text, hps.symbols, hps.data.text_cleaners)
        if hps.data.add_blank:
            text_norm = commons.intersperse(text_norm, 0)
        text_norm = LongTensor(text_norm)
        return text_norm, clean_text
    
    def vits(self, text, language, speaker_id, noise_scale, noise_scale_w, length_scale):
        proc_name = multiprocessing.current_process().name
        print(f'Doing something fancy in {proc_name}!')

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
            x_tst = stn_tst.unsqueeze(0)
            x_tst_lengths = LongTensor([stn_tst.size(0)])
            speaker_id = LongTensor([speaker_id])
            audio = self.net_g_ms.infer(x_tst, x_tst_lengths, sid=speaker_id, noise_scale=noise_scale, noise_scale_w=noise_scale_w,
                                        length_scale=length_scale)[0][0, 0].data.float().numpy()
            print(f"The inference takes {time.perf_counter() - start} seconds")
            
        return audio

    def run(self):
        proc_name = self.name

        self.hps_ms = utils.get_hparams_from_file(r'vits/model/config.json')
        speakers = self.hps_ms.speakers

        with no_grad():
            self.net_g_ms = SynthesizerTrn(
                len(self.hps_ms.symbols),
                self.hps_ms.data.filter_length // 2 + 1,
                self.hps_ms.train.segment_size // self.hps_ms.data.hop_length,
                n_speakers=self.hps_ms.data.n_speakers,
                **self.hps_ms.model)
            _ = self.net_g_ms.eval()
            model, optimizer, learning_rate, epochs = utils.load_checkpoint(r'vits/model/G_953000.pth', self.net_g_ms, None)

        print("Loading Weights finished.", flush=True)

        py_audio = pyaudio.PyAudio()
        stream = py_audio.open(format=pyaudio.paFloat32,
                channels=1,
                rate=22050,
                output=True)

        print("PYAudio is initialized.", flush=True)

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

                # https://people.csail.mit.edu/hubert/pyaudio/docs/

                # https://stackoverflow.com/questions/30675731/howto-stream-numpy-array-into-pyaudio-stream  

                # stream = py_audio.open(format=pyaudio.paFloat32,
                #                 channels=1,
                #                 rate=22050,
                #                 output=True)
                
                data = audio.astype(np.float32).tostring()
                stream.write(data)
                
            except Exception as e:
                print(e)
                # print(f"Errors ocurrs in the process {proc_name}")
            finally:
                self.task_queue.task_done()
                if self.event_all_tasks_fininished is not None:
                    self.event_all_tasks_fininished.set()

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


# https://pymotw.com/2/multiprocessing/communication.html
# Establish communication queues
vits_task_queue = multiprocessing.JoinableQueue()
results = multiprocessing.Queue()

last_message = None

def get_message():
    global last_message
    url = "http://api.live.bilibili.com/ajax/msg?roomid="
    room = "14655481"
    res = requests.get(url+room).json()
    try:
        res = res['data']['room'][-1]
        if res == last_message:
            return None
        else:
            last_message = res
            return res
    except Exception as e:
        print(e)
        None


'''========【http端口服务】========'''

class HttpHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path, args = urllib.parse.splitquery(self.path)
        # self._response(path, args)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        if message := get_message():
            data = {'result': message['text'], 'status': 0}
            self.wfile.write(json.dumps(data).encode())
        else :
            data = {'result': '', 'status': -1}
            self.wfile.write(json.dumps(data).encode())

    def do_POST(self):
        args = self.rfile.read(int(self.headers['content-length'])).decode("utf-8")
        print("==================================================")
        print(args)
        print("==================================================")

        vits_task = VITSTask(args)
        vits_task_queue.put(vits_task)

        self._response(self.path, args)

    def _response(self, path, args):
        # 组装参数为字典
        if args:
            args = urllib.parse.parse_qs(args).items()
            args = dict([(k, v[0]) for k, v in args])
        else:
            args = {}
        # 设置响应结果
        result = {"status": 0, "msg": "操作成功", "data": [{"page_id": 1}, {"page_id": 2}]}
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

if __name__ == '__main__':


    # asyncio.new_event_loop()
    # asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # asyncio.get_event_loop().run_until_complete(...)

    event_vits_process_initialized = multiprocessing.Event()

    event_all_tasks_finished = multiprocessing.Event()

    vits_process = VITSProcess(vits_task_queue, results, event_vits_process_initialized, event_all_tasks_finished)
    vits_process.start()

    event_vits_process_initialized.wait()

    print("Running HTTPServer...")
    # 开启http服务，设置监听ip和端口
    httpd = HTTPServer(('', 8787), HttpHandler)
    httpd.serve_forever()
    # 运行后 http://localhost:8787 即可访问该接口

    # charaid = "IQeHSc2ino-Wedq1lk9HMA0Lz6sXAg-QI2Gq0aMFyIA"
    # cai_playwright = CAIPlaywright()
    # cai_playwright.init(charaid)

    # https://www.geeksforgeeks.org/how-to-detect-if-a-specific-key-pressed-using-python/
    # while True:
    #     user_input = input("Please enter commands: ")
    #     event_all_tasks_finished.clear()
    #     if user_input == 'esc':
    #         # Add a poison pill for the consumer
    #         vits_task_queue.put(None)
    #         break
    #     elif user_input == '0':
    #         task = VITSTask("你好，我是东海帝皇！")
    #         vits_task_queue.put(task)
    #     else:
    #         event_all_tasks_finished.set()
        
    #     event_all_tasks_finished.wait()

    # cai_playwright.stop()

    # Wait for all of the tasks to finish
    # tasks.join()

    # tasks.close()

    vits_process.join()