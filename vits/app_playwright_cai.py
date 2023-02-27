import multiprocessing

import time
import numpy as np
import utils
import commons
from models import SynthesizerTrn
from text import text_to_sequence
from torch import no_grad, LongTensor

import pyaudio
from playwright.sync_api import sync_playwright, Page, expect

import asyncio


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

        self.hps_ms = utils.get_hparams_from_file(r'./model/config.json')
        speakers = self.hps_ms.speakers

        with no_grad():
            self.net_g_ms = SynthesizerTrn(
                len(self.hps_ms.symbols),
                self.hps_ms.data.filter_length // 2 + 1,
                self.hps_ms.train.segment_size // self.hps_ms.data.hop_length,
                n_speakers=self.hps_ms.data.n_speakers,
                **self.hps_ms.model)
            _ = self.net_g_ms.eval()
            model, optimizer, learning_rate, epochs = utils.load_checkpoint(r'./model/G_953000.pth', self.net_g_ms, None)

        py_audio = pyaudio.PyAudio()
        stream = py_audio.open(format=pyaudio.paFloat32,
                channels=1,
                rate=22050,
                output=True)

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

class CAIPlaywright:
    def init(self, charaid: str, persistent_mode=True):
        try:
            self.persistent_mode = persistent_mode
            self.playwright = sync_playwright().start()

            # https://playwright.dev/python/docs/browsers#google-chrome--microsoft-edge
            # chrome/msedge
            # self.browser = self.playwright.chromium.launch(channel="chrome", headless=False)
            if persistent_mode:
                print("In persistent mode:")
                userDataDir = "C:/Users/DELL/AppData/Local/Google/Chrome/User Data/"
                # https://github.com/microsoft/playwright/issues/15011
                # https://playwright.dev/docs/api/class-browsertype
                self.context = self.playwright.chromium.launch_persistent_context(userDataDir, channel="chrome", headless=False)
                print("Context is created", flush=True)
                self.page = self.context.new_page()
            else:
                self.browser = self.playwright.firefox.launch(headless=False)
                self.page = self.browser.new_page()

            # create a new incognito browser context.
            # self.context = self.browser.new_context()
            # create a new page in a pristine context.
            # self.page = self.context.new_page()

            # https://stackoverflow.com/questions/71362982/is-there-a-way-to-connect-to-my-existing-browser-session-using-playwright
            # self.browser = self.playwright.chromium.connect_over_cdp("http://localhost:9222")
            # self.page = self.browser.new_page()

            # https://beta.character.ai/chat?char=IQeHSc2ino-Wedq1lk9HMA0Lz6sXAg-QI2Gq0aMFyIA
            url = "https://beta.character.ai/chat?char=" + charaid
            self.page.goto(url)
            self.page.screenshot(path="CAIPlayerwright Test.png")
            if not persistent_mode:
                self.page.get_by_role("button", name="Accept").click()

            self.chara_name = ""
            while self.chara_name == "":
                handle = self.page.query_selector('div.chattitle.p-0.pe-1.m-0')
                while not handle:
                    handle = self.page.query_selector('div.chattitle.p-0.pe-1.m-0')
                    time.sleep(0.5)
                self.chara_name = handle.inner_text()
                time.sleep(0.5)

            self.ipt = self.page.get_by_placeholder("Type a message")
        except Exception as e:
            print(e)
            self.stop()
            exit()
    
    def send_msg(self, msg):
        try:
            self.ipt.fill(msg)
            self.ipt.press("Enter")
        except Exception as e:
            print(e)
            self.stop()
            exit()

    def get_msg(self) -> str:
        try:
            # print("Getting msg...")

            # locate the button with class "btn py-0"
            lct = self.page.locator("button.btn.py-0").nth(0)

            expect(lct).to_be_enabled(timeout=0)

            div = self.page.query_selector('div.msg.char-msg')
            output_text = div.inner_text()
            # print(f"{self.chara_name}: {output_text}")
            return output_text
        except Exception as e:
            print(e)
            self.stop()
            exit()

    def stop(self):
        self.page.close()
        if self.persistent_mode:
            self.context.close()
        else:
            self.browser.close()
        self.playwright.stop()


class CAIProcess(multiprocessing.Process):
    def __init__(self, message_queue, response_queue, event_initialized):
        multiprocessing.Process.__init__(self)
        self.message_queue = message_queue
        self.response_queue = response_queue
        self.event_initalized = event_initialized

    def run(self):
        charaid = "IQeHSc2ino-Wedq1lk9HMA0Lz6sXAg-QI2Gq0aMFyIA"
        cai_playwright = CAIPlaywright()
        cai_playwright.init(charaid)

        proc_name = self.name
        
        self.event_initalized.set()

        while True:
            message = self.message_queue.get()
            if message is None:
                # Poison pill means shutdown
                print(f"{proc_name}: Exiting", flush=True)
                break
            
            print(f"{proc_name} is working...", flush=True)
            cai_playwright.send_msg(message)
            response = cai_playwright.get_msg()

            self.response_queue.put(response)

        cai_playwright.stop()


if __name__ == '__main__':
    # asyncio.new_event_loop()
    # asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # asyncio.get_event_loop().run_until_complete(...)

    # https://pymotw.com/2/multiprocessing/communication.html

    # Establish communication queues
    vits_task_queue = multiprocessing.JoinableQueue()
    results = multiprocessing.Queue()

    message_queue = multiprocessing.Queue()
    response_queue = multiprocessing.Queue()

    event_cai_process_initialized = multiprocessing.Event()
    event_vits_process_initialized = multiprocessing.Event()

    event_all_tasks_finished = multiprocessing.Event()

    cai_process = CAIProcess(message_queue, response_queue, event_cai_process_initialized)
    cai_process.start()
    vits_process = VITSProcess(vits_task_queue, results, event_vits_process_initialized, event_all_tasks_finished)
    vits_process.start()

    event_cai_process_initialized.wait()
    event_vits_process_initialized.wait()

    # charaid = "IQeHSc2ino-Wedq1lk9HMA0Lz6sXAg-QI2Gq0aMFyIA"
    # cai_playwright = CAIPlaywright()
    # cai_playwright.init(charaid)

    # https://www.geeksforgeeks.org/how-to-detect-if-a-specific-key-pressed-using-python/
    while True:
        user_input = input("Please enter commands: ")
        event_all_tasks_finished.clear()
        if user_input == 'esc':
            # Add a poison pill for the consumer
            message_queue.put(None)
            vits_task_queue.put(None)
            break
        elif user_input == '0':
            task = VITSTask("你好，我是东海帝皇！")
            vits_task_queue.put(task)
        else:
            message_queue.put(user_input)

            res = response_queue.get()
            print(res, flush=True)

            task = VITSTask(res)
            vits_task_queue.put(task)
        
        event_all_tasks_finished.wait()

    # cai_playwright.stop()

    # Wait for all of the tasks to finish
    # tasks.join()

    # tasks.close()

    cai_process.join()
    vits_process.join()


    



