# coding=utf8
import sys
import multiprocessing
import ctypes

import time
import numpy as np

import pyaudio

from torch import no_grad, LongTensor
from torch import device as torch_device

from revChatGPT.V1 import Chatbot as ChatbotV1
from revChatGPT.V3 import Chatbot as ChatbotV3

sys.path.append("vits")

import vits.utils as utils
import vits.commons as commons
from vits.models import SynthesizerTrn
from vits.text import text_to_sequence

import subtitle
import prompt_hot_update

from app_utils import *
import song_singer

from system_message_manager import SystemMessageManager

from vts_utils import ExpressionHelper, VTSAPIProcess, VTSAPITask

from Danmaku import DanmakuProcess

class VITSProcess(multiprocessing.Process):
    def __init__(
            self,
            device_str,
            task_queue,
            result_queue,
            event_initialized):
        multiprocessing.Process.__init__(self)
        self.device_str = device_str
        self.task_queue = task_queue  # VITS inference task queue
        self.result_queue = result_queue  # Audio data queue
        self.event_initialized = event_initialized

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
            audio = self.net_g_ms.infer(x_tst, x_tst_lengths, sid=speaker_id, noise_scale=noise_scale,
                                        noise_scale_w=noise_scale_w,
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
                break
            try:
                print(f"{proc_name} is working...")
                audio = None
                if next_task.text is not None:
                    audio = self.vits(next_task.text, next_task.language, next_task.sid, next_task.noise_scale,
                                    next_task.noise_scale_w, next_task.length_scale)

                # data = audio.astype(np.float32).tobytes()

                task = AudioTask(audio, 
                                next_task.text, 
                                pre_speaking_event=next_task.pre_speaking_event,
                                post_speaking_event=next_task.post_speaking_event)
                self.result_queue.put(task)

            except Exception as e:
                print(e)
                # print(f"Errors ocurrs in the process {proc_name}")

        sys.exit() # Manually and forcibly exit the process


class VITSTask:
    def __init__(self, text, language=0, speaker_id=2, noise_scale=0.5, 
                 noise_scale_w=0.5, length_scale=1.0, pre_speaking_event=None, post_speaking_event=None):
        self.text = text
        self.language = language
        self.sid = speaker_id
        self.noise_scale = noise_scale
        self.noise_scale_w = noise_scale_w
        self.length_scale = length_scale
        self.pre_speaking_event = pre_speaking_event
        self.post_speaking_event = post_speaking_event


# By ChatGPT
def normalize_audio(audio_data):
    # Calculate the maximum absolute value in the audio data
    max_value = np.max(np.abs(audio_data))
    
    # Normalize the audio data by dividing it by the maximum value
    normalized_data = audio_data / max_value
    
    return normalized_data


class AudioTask:
    def __init__(self, data, text=None, pre_speaking_event=None, post_speaking_event=None):
        self.data = data
        self.text = text
        self.pre_speaking_event = pre_speaking_event
        self.post_speaking_event = post_speaking_event


class AudioPlayerProcess(multiprocessing.Process):
    NUM_FRAMES = 1024
    BIT_DEPTH = 32
    NUM_BYTES_PER_SAMPLE = BIT_DEPTH // 8
    NUM_CHANNELS = 1
    CHUNK_SIZE = NUM_FRAMES * NUM_BYTES_PER_SAMPLE * NUM_CHANNELS # Data chunk size in bytes

    def __init__(self, audio_task_queue, subtitle_task_queue, sing_queue, vts_api_queue, event_initalized):
        super().__init__()
        self.task_queue = audio_task_queue
        self.subtitle_task_queue = subtitle_task_queue
        self.sing_queue = sing_queue
        self.vts_api_queue = vts_api_queue
        self.event_initalized = event_initalized

        self.enable_audio_stream = multiprocessing.Value(ctypes.c_bool, True)
        self.enable_audio_stream_virtual = multiprocessing.Value(ctypes.c_bool, True)

        self.virtual_audio_devices_are_found = False  # Maybe incorrect, because __init__ is run in the main process

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

    # https://stackoverflow.com/questions/434287/how-to-iterate-over-a-list-in-chunks
    def chunker(self, seq, size):
        return [seq[pos:pos + size] for pos in range(0, len(seq), size)]

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
                pre_speaking_event = next_task.pre_speaking_event
                if pre_speaking_event is not None:
                    if pre_speaking_event.event_type == SpeakingEvent.SING:
                        self.sing_queue.put(pre_speaking_event.msg)
                    elif pre_speaking_event.event_type == SpeakingEvent.SET_EXPRESSION:
                        expression_file = ExpressionHelper.emotion_to_expression_file(pre_speaking_event.msg)
                        if expression_file is not None:
                            msg_type = "ExpressionActivationRequest"
                            data_dict = {
                                "expressionFile": expression_file,
                                "active": True
                            }

                            vts_api_task = VTSAPITask(msg_type, data_dict)
                            self.vts_api_queue.put(vts_api_task)
                    elif pre_speaking_event.event_type == SpeakingEvent.TRIGGER_HOTKEY:
                        msg_type = "HotkeyTriggerRequest"
                        data_dict = {
                            "hotkeyID": pre_speaking_event.msg
                        }

                        vts_api_task = VTSAPITask(msg_type, data_dict)
                        self.vts_api_queue.put(vts_api_task)

                audio = next_task.data
                text = next_task.text
                
                if text is not None:
                    self.subtitle_task_queue.put(text)
                
                if audio is not None:
                    audio = normalize_audio(audio)
                    data = audio.view(np.uint8)

                    # Write speech data into virtual audio device to drive lip sync animation
                    chunks = self.chunker(data, self.CHUNK_SIZE)
                    for chunk in chunks:
                        if self.is_audio_stream_enabled():
                            stream.write(chunk)

                        if (self.is_audio_stream_virtual_enabled() and
                                self.virtual_audio_devices_are_found):
                            stream_virtual.write(chunk)

                post_speaking_event = next_task.post_speaking_event
                if post_speaking_event is not None:
                    if post_speaking_event.event_type == SpeakingEvent.SING:
                        time.sleep(1.0) # a quick hack to delay continue to sing
                        self.sing_queue.put(post_speaking_event.msg)
                    elif post_speaking_event.event_type == SpeakingEvent.SET_EXPRESSION:
                        expression_file = ExpressionHelper.emotion_to_expression_file(post_speaking_event.msg)
                        if expression_file is not None:
                            msg_type = "ExpressionActivationRequest"
                            data_dict = {
                                "expressionFile": expression_file,
                                "active": True
                            }

                            vts_api_task = VTSAPITask(msg_type, data_dict)
                            self.vts_api_queue.put(vts_api_task)
                    elif post_speaking_event.event_type == SpeakingEvent.TRIGGER_HOTKEY:
                        msg_type = "HotkeyTriggerRequest"
                        data_dict = {
                            "hotkeyID": post_speaking_event.msg
                        }

                        vts_api_task = VTSAPITask(msg_type, data_dict)
                        self.vts_api_queue.put(vts_api_task)

            except Exception as e:
                print(e)

        stream.close()
        stream_virtual.close()
        self.py_audio.terminate()
        

def should_cut_text(text, min, punctuations_min, threshold, punctuations_threshold):
    should_cut = False
    if len(text) >= min:
        if text[-1] in punctuations_min:
            should_cut = True
        elif len(text) >= threshold:
            if text[-1] in punctuations_threshold:
                should_cut = True

    return should_cut


class ChatGPTProcess(multiprocessing.Process):
    def __init__(self, api_key, greeting_queue, chat_queue, thanks_queue, cmd_queue, vits_task_queue,
                 app_state, event_initialized):
        super().__init__()
        self.api_key = api_key

        self.greeting_queue = greeting_queue
        self.chat_queue = chat_queue
        self.thanks_queue = thanks_queue
        self.cmd_queue = cmd_queue

        self.vits_task_queue = vits_task_queue
        self.event_initialized = event_initialized

        self.use_streamed = multiprocessing.Value(ctypes.c_bool, False)
        self.enable_vits = multiprocessing.Value(ctypes.c_bool, True)
        
        self.app_state = app_state

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

        # system_msg_updater = prompt_hot_update.SystemMessageUpdater()
        # system_msg_updater.start(60.0)

        system_message_manager = SystemMessageManager()

        song_list = song_singer.SongList()

        # engine_str = "gpt-3.5-turbo-0301"
        # chatbot = ChatbotV3(api_key=self.api_key, engine=engine_str, temperature=0.7, system_prompt=preset_text)
        chatbot = ChatbotV3(api_key=self.api_key, max_tokens=3000, temperature=0.7,
                            system_prompt=preset_text_short)

        punctuations_to_split_text = {'。', '！', '？', '：', '\n'}
        punctuations_to_split_text_longer = {'。', '！', '？', '：', '\n', '，'}

        min_sentence_length = 12
        sentence_longer_threshold = 24

        # Use short preset text for event
        chatbot.reset(convo_id='default', system_prompt=preset_text_short)

        channels = {'default', 'chat', 'presing'}

        curr_song_dict = None

        self.event_initialized.set()

        print(f"{proc_name} is Initialized.")

        while True:
            # system_msg_updater.update()

            if self.app_state.value == AppState.CHAT:
                task = None
                if not self.thanks_queue.empty():
                    print(f"{proc_name} is working...")
                    print("Get a task from thanks_queue.")
                    task = self.thanks_queue.get()
                elif not self.chat_queue.empty():
                    print(f"{proc_name} is working...")
                    print("Get a task from chat_queue.")
                    task = self.chat_queue.get()
                    if task is None:
                        # Poison pill means shutdown
                        print(f"{proc_name}: Exiting")
                        break

                    header = task.message[:32]
                    if '#reset' in header:
                        try:
                            print("Reset ChatGPT")
                            print(preset_text_short)
                            chatbot.conversation.clear()
                            chatbot.reset(convo_id='default', system_prompt=preset_text_short)
                        except Exception as e:
                            print(e)
                            print("Reset fail!")
                        finally:
                            continue

                    if task.message.startswith("点歌"):
                        cmd_sing_str = task.message 
                        song_alias = cmd_sing_str[2:]

                        user_name = task.user_name
                        song_dict = song_list.search_song(song_alias)
                        channel = 'presing'

                        curr_song_dict = song_dict

                        editor_name = None
                        song_name = None
                        song_abbr = None
                        id = None
                        if song_dict is not None:
                            song_name = song_dict['name']
                            song_abbr = song_dict['abbr']
                            editor_name = song_dict['editor']
                            id = song_dict['id']

                        if editor_name is not None and editor_name == '_':
                            editor_name = None

                        # Maybe the code should behave like 
                        # if Song ID doesn't exist, then the character should tell the audience that the Song ID does not exist
                        if id is not None and id == 666:
                            system_msg = SystemMessageManager_1.get_presing_special_sm(user_name)
                        else:
                            system_msg = SystemMessageManager_1.get_presing_sm(user_name, song_abbr, editor_name)

                        chatbot.reset(convo_id=channel, system_prompt=system_msg)

                        cmd_sing = None
                        if song_dict is not None:
                            cmd_sing = f"点歌{song_name}"

                        try:
                            new_sentence = ""
                            vits_task = None
                            for data in chatbot.ask_stream(prompt="", convo_id=channel):
                                print(data, end="|", flush=True)

                                if vits_task is not None:
                                    self.vits_task_queue.put(vits_task)
                                    vits_task = None

                                new_sentence += data
                                should_cut = should_cut_text(new_sentence, 
                                                        min_sentence_length, 
                                                        punctuations_to_split_text, 
                                                        sentence_longer_threshold,
                                                        punctuations_to_split_text_longer)

                                # If code reaches here, meaning that the request to ChatGPT is successful.
                                if self.is_vits_enabled():
                                    if should_cut:
                                        vits_task = VITSTask(new_sentence.strip())
                                        new_sentence = ""

                            if self.is_vits_enabled():
                                if vits_task is None:
                                    vits_task = VITSTask(new_sentence.strip())
                                else:
                                    assert len(new_sentence) == 0

                                if song_dict is not None:
                                    vits_task.post_speaking_event = SpeakingEvent(SpeakingEvent.SING, cmd_sing)

                                self.vits_task_queue.put(vits_task)

                        except Exception as e:
                            print(e)
                            if id != 666:
                                if song_dict is not None:
                                    if editor_name is not None:
                                        response_to_song_request_msg = f"好的，“{user_name}”同学，下面我将给大家献唱一首{song_abbr}，感谢{editor_name}大佬教我唱这首歌。"
                                    else:
                                        response_to_song_request_msg = f"好的，“{user_name}”同学，下面我将给大家献唱一首{song_abbr}。"
                                else:
                                    response_to_song_request_msg = f"对不起，{user_name}同学，我不会唱你点的这首歌。"
                            else:
                                response_to_song_request_msg = f"“{user_name}”同学，小爷这下可是真的怒了！"
                            
                            vits_task = VITSTask(response_to_song_request_msg)
                            
                            if song_dict is not None:
                                vits_task.post_speaking_event = SpeakingEvent(SpeakingEvent.SING, cmd_sing)

                            self.vits_task_queue.put(vits_task)

                        if song_dict is not None:
                            self.app_state.value = AppState.PRESING
                        continue

                # elif not self.greeting_queue.empty():
                #     print(f"{proc_name} is working...")
                #     print("Get a task from greeting_queue.")
                #     task = self.greeting_queue.get()

                else:
                    time.sleep(1.0)
                    continue

                assert task is not None
                
                user_name = task.user_name
                msg = task.message
                channel = task.channel
                prompt_msg = msg

                assert channel in channels

                try:
                    repeat_user_message = True
                    repeat_message = None
                    if channel == 'default':
                        repeat_user_message = False
                        if channel in chatbot.conversation:
                            if len(chatbot.conversation[channel]) >= 9:
                                chatbot.reset(convo_id=channel)
                    elif channel == 'chat':
                        if (channel not in chatbot.conversation or 
                            len(chatbot.conversation[channel]) >= 9):
                            # system_msg = system_msg_updater.get_system_message()
                            system_msg = system_message_manager.systetm_message
                            chatbot.reset(channel, system_msg)

                        repeat_message = f"{user_name}说：“{msg}”"
                        # prompt_msg = f"（{user_name}对你说：)“{msg}”"
                        prompt_msg = f"我是{user_name}，{msg}"

                    new_sentence = ""
                    is_first_sentence = True
                    for data in chatbot.ask_stream(prompt=prompt_msg, convo_id=channel):
                        print(data, end='|', flush=True)
                        
                        new_sentence += data
                        should_cut = should_cut_text(new_sentence, 
                                                min_sentence_length, 
                                                punctuations_to_split_text, 
                                                sentence_longer_threshold,
                                                punctuations_to_split_text_longer)

                        # If code reaches here, meaning that the request to ChatGPT is successful.
                        if self.is_vits_enabled():
                            if should_cut:
                                if repeat_user_message:
                                    vits_task = VITSTask(repeat_message.strip())
                                    self.vits_task_queue.put(vits_task)
                                    # time.sleep(1.0) # Simulate speech pause
                                    repeat_user_message = False

                                if is_first_sentence:
                                    emotion, line = ExpressionHelper.get_emotion_and_line(new_sentence)
                                    print(f"#{line}#")
                                    vits_task = VITSTask(line.strip())
                                    if emotion in ExpressionHelper.emotion_to_expression:
                                        vits_task.pre_speaking_event = SpeakingEvent(SpeakingEvent.SET_EXPRESSION, emotion)
                                    is_first_sentence = False
                                else:
                                    vits_task = VITSTask(new_sentence.strip())

                                self.vits_task_queue.put(vits_task)
                                new_sentence = ""

                    if len(new_sentence) > 0:
                        if self.is_vits_enabled():
                            pre_speaking_event = None
                            line = new_sentence
                            if is_first_sentence:
                                emotion, line = ExpressionHelper.get_emotion_and_line(new_sentence)
                                if emotion in ExpressionHelper.emotion_to_expression:
                                    pre_speaking_event = SpeakingEvent(SpeakingEvent.SET_EXPRESSION, emotion)
                                is_first_sentence = False
                            
                            vits_task = VITSTask(line.strip(), 
                                                pre_speaking_event=pre_speaking_event)
                            self.vits_task_queue.put(vits_task)

                    if self.is_vits_enabled():
                        # A task with no text for TTS, just for SpeakingEvent at the end of the conversation.
                        end_task = VITSTask(None,
                                            post_speaking_event=SpeakingEvent(SpeakingEvent.TRIGGER_HOTKEY, "Clear"))
                        self.vits_task_queue.put(end_task)

                except Exception as e:
                    print(e)
                    if channel == 'chat':
                        if self.is_vits_enabled():
                            text = "不好意思，刚才我走神了，请问你刚才说什么?"
                            task = VITSTask(text)
                            self.vits_task_queue.put(task)

            elif self.app_state.value == AppState.PRESING:
                # Clear all queues
                while not self.chat_queue.empty():
                    _ = self.chat_queue.get()

                # while not self.greeting_queue.empty():
                    # _ = self.greeting_queue.get()

                while not self.thanks_queue.empty():
                    _ = self.thanks_queue.get()

                cmd_msg = self.cmd_queue.get()
                if cmd_msg == "#唱歌开始":
                    self.app_state.value = AppState.SING
                elif cmd_msg == "#唱歌结束":
                    self.app_state.value = AppState.CHAT
                if cmd_msg is None:
                    # Poison pill means shutdown
                    print(f"{proc_name}: Exiting")
                    break

            elif self.app_state.value == AppState.SING:
                if not self.cmd_queue.empty():
                    cmd_msg = self.cmd_queue.get()

                    if cmd_msg == "#唱歌结束":

                        song_abbr = curr_song_dict['abbr']
                        editor_name = curr_song_dict['editor']
                        id = curr_song_dict['id']
                        channel = "postsing"

                        if editor_name == '_':
                            editor_name = None

                        if id == 666:
                            system_msg = SystemMessageManager_1.get_finish_special_sm()
                        else:
                            system_msg = SystemMessageManager_1.get_finish_sm(song_abbr, editor_name)
                        chatbot.reset(convo_id=channel, system_prompt=system_msg)
                        
                        try:
                            new_sentence = ""
                            for data in chatbot.ask_stream(prompt="", convo_id=channel):
                                print(data, end="|", flush=True)

                                new_sentence += data
                                should_cut = should_cut_text(new_sentence, 
                                                    min_sentence_length, 
                                                    punctuations_to_split_text, 
                                                    sentence_longer_threshold,
                                                    punctuations_to_split_text_longer)

                                if should_cut:
                                    vits_task = VITSTask(new_sentence.strip())
                                    self.vits_task_queue.put(vits_task)
                                    new_sentence = ""

                            if len(new_sentence) > 0:
                                if self.is_vits_enabled():
                                    vits_task = VITSTask(new_sentence.strip())
                                    self.vits_task_queue.put(vits_task)
                        except Exception as e:
                            print(e)
                            if id != 666:
                                if editor_name is not None:
                                    post_sing_line = f"感谢各位朋友欣赏这首{song_abbr}，再次感谢{editor_name}大佬，是他教我唱得首歌！"
                                else:
                                    post_sing_line = f"感谢各位朋友欣赏这首{song_abbr}！"
                            else:
                                post_sing_line = "请下次不要再激怒小爷了！"

                            vits_task = VITSTask(post_sing_line)
                            self.vits_task_queue.put(vits_task)
                        finally:
                            self.app_state.value = AppState.CHAT
                    elif cmd_msg == "#一键三连":
                        # test_interrupted_line = "有什么话想和我说吗？没事我继续唱啦~"
                        test_interrupted_line = "如果你喜欢我的歌声，请记得一定要，一键三连哦~"
                        pre_event = SpeakingEvent(SpeakingEvent.SING, "#打断唱歌")
                        post_event = SpeakingEvent(SpeakingEvent.SING, "#继续唱歌")
                        vits_task = VITSTask(test_interrupted_line, 
                                            pre_speaking_event=pre_event, 
                                            post_speaking_event=post_event)
                        self.vits_task_queue.put(vits_task)

                    elif cmd_msg is None:
                        # Poison pill means shutdown
                        print(f"{proc_name}: Exiting")
                        break

                elif not self.thanks_queue.empty():
                    task = self.thanks_queue.get()

                    user_name = task.user_name
                    msg = task.message
                    channel = "sing"

                    system_msg = SystemMessageManager_1.sing_thanks
                    chatbot.reset(convo_id=channel, system_prompt=system_msg)

                    try:
                        first_sentence = True
                        new_sentence = ""
                        vits_task = None
                        for data in chatbot.ask_stream(prompt=msg, convo_id=channel):
                            print(data, end='|', flush=True)

                            if vits_task is not None:
                                if first_sentence:      
                                    vits_task.pre_speaking_event = SpeakingEvent(SpeakingEvent.SING, "#打断唱歌")                        
                                    self.vits_task_queue.put(vits_task)
                                    vits_task = None   
                                    first_sentence = False

                            new_sentence += data

                            should_cut = should_cut_text(new_sentence, 
                                                        min_sentence_length, 
                                                        punctuations_to_split_text, 
                                                        sentence_longer_threshold,
                                                        punctuations_to_split_text_longer)
                            
                            # If code reaches here, meaning that the request to ChatGPT is successful.
                            if self.is_vits_enabled():
                                if should_cut:
                                    vits_task = VITSTask(new_sentence.strip())
                                    new_sentence = ""

                        if self.is_vits_enabled():
                            if vits_task is not None:
                                assert len(new_sentence) == 0
                                vits_task.post_speaking_event = SpeakingEvent(SpeakingEvent.SING, "#继续唱歌")
                            else:
                                vits_task = VITSTask(new_sentence.strip(), 
                                                    post_speaking_event=SpeakingEvent(SpeakingEvent.SING, "#继续唱歌"))
                                
                            if first_sentence:
                                vits_task.pre_speaking_event = SpeakingEvent(SpeakingEvent.SING, "#打断唱歌")

                            self.vits_task_queue.put(vits_task)

                    except Exception as e:
                        print(e)
                        response_to_interuption_msg = f"十分感谢您的认可！要不要跟着小爷一起唱呢？"
                        if self.is_vits_enabled():
                            vits_task = VITSTask(response_to_interuption_msg, 
                                                pre_speaking_event=SpeakingEvent(SpeakingEvent.SING, "#打断唱歌"),
                                                post_speaking_event=SpeakingEvent(SpeakingEvent.SING, "#继续唱歌")
                                                )

                            self.vits_task_queue.put(vits_task)

                else:
                    time.sleep(1.0)
                    
class SpeakingEvent:
    SING = 0
    SET_EXPRESSION = 1
    TRIGGER_HOTKEY = 2

    def __init__(self, event_type, msg):
        self.event_type = event_type
        self.msg = msg


preset_text_short = "现在赋予你一个身份，你是一位赛马娘，名字为东海帝皇，在B站直播间直播和观众聊天。你常用小爷来称呼自己。你说话简练。"

class SystemMessageManager_1:
    sing_accept_thank_tempate = "现在赋予你一个身份，你是一位赛马娘，名字是东海帝皇，正在胜利舞台上准备唱歌。你常用小爷来称呼自己。台下一名观众，叫“{t_user_name}”，点了一个首歌，名叫“{t_song_name}”，这首歌是“{t_editor_name}”大佬教你唱的，你同意唱并且要答谢教你的大佬，这时你对这名观众说：（你所有说话内容必须遵照以下规则：1. 必须用第一人称方式说话。2. 说话内容不要带第三人称方式描述的内容。3. 说话内容不要带任何动作描述。）"

    sing_accept_tempate = "现在赋予你一个身份，你是一位赛马娘，名字是东海帝皇，正在胜利舞台上准备唱歌。你常用小爷来称呼自己。台下一名观众，叫“{t_user_name}”，点了一个首歌，名叫“{t_song_name}”，你会唱，并且同意唱，这时你对这名观众说：（你所有说话内容必须遵照以下规则：1. 必须用第一人称方式说话。2. 说话内容不要带第三人称方式描述的内容。3. 说话内容不要带任何动作描述。）"

    # 可以随机推荐歌曲，有个清单
    sing_refuse_template = "现在赋予你一个身份，你是一位赛马娘，名字是东海帝皇，正在胜利舞台上准备唱歌。你常用小爷来称呼自己。台下一名观众，叫“{t_user_name}“，点了一个首歌，你不会唱，这时你对这名观众说：（你所有说话内容必须遵照以下规则：1. 必须用第一人称方式说话。2. 说话内容不要带第三人称方式描述的内容。3. 说话内容不要带任何动作描述。）"

    sing_finish_template = "现在赋予你一个身份，你是一位赛马娘，名字是东海帝皇，你常用小爷来称呼自己。你刚在胜利舞台上唱完一首歌，这首歌的名字是“{t_song_name}”，是“{t_editor_name}”大佬教你唱的。这时，你要感谢台下观众的聆听，并再次感谢教你唱这首歌的大佬，你说：（你所有说话内容必须遵照以下规则：1. 必须用第一人称方式说话。2. 说话内容不要带第三人称方式描述的内容。3. 说话内容不要带任何动作描述。）"

    sing_finish_no_editor_template = "现在赋予你一个身份，你是一位赛马娘，名字是东海帝皇，你常用小爷来称呼自己。你刚在胜利舞台上唱完一首歌，这首歌的名字是“{t_song_name}”。这时，你要感谢台下观众的聆听，你说：（你所有说话内容必须遵照以下规则：1. 必须用第一人称方式说话。2. 说话内容不要带第三人称方式描述的内容。3. 说话内容不要带任何动作描述。）"

    sing_thanks = "现在赋予你一个身份，你是一位赛马娘，名字是东海帝皇，正在胜利舞台上直播唱歌。你常用小爷来称呼自己。如果有观众在你唱歌的时候现场送礼，点赞，或是关注了你的直播间，你会暂停唱歌，答谢观众。你所有说话内容必须遵照以下规则：1. 必须用第一人称方式说话。2. 说话内容不要带第三人称方式描述的内容。3. 说话内容不要带任何动作描述。"

    speical_accept_template = "现在赋予你一个身份，你是一位赛马娘，名字是东海帝皇，正在胜利舞台上准备唱歌。你常用小爷来称呼自己。台下一名观众，叫“{t_user_name}”，试图把你激怒，你对这名观众说：（你所有说话内容必须遵照以下规则：1. 必须用第一人称方式说话。2. 说话内容不要带第三人称方式描述的内容。3. 说话内容不要带任何动作描述。）"

    speical_finish_template = "现在赋予你一个身份，你是一位赛马娘，名字是东海帝皇，正在胜利舞台上唱歌。你常用小爷来称呼自己。刚才你很生气，希望观众不要再激怒自己了，你向名观众们说：（你所有说话内容必须遵照以下规则：1. 必须用第一人称方式说话。2. 说话内容不要带第三人称方式描述的内容。3. 说话内容不要带任何动作描述。）"

    def get_presing_sm(user_name, song_name=None, editor_name=None):
        if song_name is not None:
            if editor_name is not None:
                return SystemMessageManager_1.sing_accept_thank_tempate.format(t_user_name=user_name, 
                                                                       t_song_name=song_name,
                                                                       t_editor_name=editor_name)
            else:
                return SystemMessageManager_1.sing_accept_tempate.format(t_user_name=user_name, t_song_name=song_name)
        else:
            return SystemMessageManager_1.sing_refuse_template.format(t_user_name=user_name)
        
    def get_finish_sm(song_name, editor_name=None):
        if editor_name is not None:
            return SystemMessageManager_1.sing_finish_template.format(t_song_name=song_name, t_editor_name=editor_name)
        else:
            return SystemMessageManager_1.sing_finish_no_editor_template.format(t_song_name=song_name)
    
    def get_presing_special_sm(user_name):
        return SystemMessageManager_1.speical_accept_template.format(t_user_name=user_name)
    
    def get_finish_special_sm():
        return SystemMessageManager_1.speical_finish_template

if __name__ == '__main__':
    app_state = multiprocessing.Value('i', AppState.CHAT)

    room_id = ""

    greeting_queue = multiprocessing.Queue(maxsize=2)
    chat_queue = multiprocessing.Queue(maxsize=3)
    thanks_queue = multiprocessing.Queue(maxsize=4)

    event_danmaku_process_stop = multiprocessing.Event()

    damaku_process = DanmakuProcess(room_id, greeting_queue, chat_queue, thanks_queue, app_state, event_danmaku_process_stop)
    damaku_process.start()

    cmd_queue = multiprocessing.Queue(maxsize=4)
    sing_queue = multiprocessing.Queue(maxsize=4)

    event_song_singer_process_initialized = multiprocessing.Event()
    song_singer_process = song_singer.SongSingerProcess(sing_queue, cmd_queue, event_song_singer_process_initialized)
    song_singer_process.start()

    vits_task_queue = multiprocessing.Queue()

    event_chat_gpt_process_initialized = multiprocessing.Event()

    api_key = ""
    chat_gpt_process = ChatGPTProcess(api_key, greeting_queue, chat_queue, thanks_queue, cmd_queue, vits_task_queue,
                                      app_state, event_chat_gpt_process_initialized)
    chat_gpt_process.start()

    audio_task_queue = multiprocessing.Queue()

    event_vits_process_initialized = multiprocessing.Event()

    # Or cpu
    device_str = 'cuda'
    # device_str = 'cpu'
    vits_process = VITSProcess(
        device_str,
        vits_task_queue,
        audio_task_queue,
        event_vits_process_initialized)
    vits_process.start()

    event_audio_player_process_initialized = multiprocessing.Event()
    subtitle_task_queue = multiprocessing.Queue()

    vts_api_queue = multiprocessing.Queue(maxsize=8)
    audio_player_process = AudioPlayerProcess(audio_task_queue, subtitle_task_queue, sing_queue, vts_api_queue,
                                              event_audio_player_process_initialized)
    audio_player_process.start()

    event_subtitle_bar_process_initialized = multiprocessing.Event()

    subtitle_bar_process = subtitle.SubtitleBarProcess(subtitle_task_queue, event_subtitle_bar_process_initialized)
    subtitle_bar_process.start()

    vts_api_process = VTSAPIProcess(vts_api_queue)
    vts_api_process.start()

    event_subtitle_bar_process_initialized.wait()

    event_song_singer_process_initialized.wait()
    event_chat_gpt_process_initialized.wait()
    event_vits_process_initialized.wait()
    event_audio_player_process_initialized.wait()

    while True:
        user_input = input("Please enter commands:\n")
        if user_input == 'esc':
            break
        if app_state.value == AppState.CHAT:
            if user_input == '0':
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
                if damaku_process.is_response_enabled():
                    damaku_process.set_response_enabled(False)
                    print("Disable response to live comments")
                else:
                    damaku_process.set_response_enabled(True)
                    print("Enable response to live comments")
            elif user_input == '5':
                if chat_gpt_process.is_streamed_enabled():
                    chat_gpt_process.set_streamed_enabled(False)
                    print("Disable chatGPT streamed")
                else:
                    chat_gpt_process.set_streamed_enabled(True)
                    print("Enable ChatGPT streamed")

            elif user_input == '8':
                print("Reset ChatGPT")
                chat_task = ChatTask(None, "#reset", 'chat')
                chat_queue.put(chat_task)
            elif user_input == '9':
                print("Test VITS and audio player")
                test_text = "测试语音合成和音频播放。"
                vits_task_queue.put(VITSTask(test_text))
            else:
                chat_task = ChatTask('喵喵抽风', user_input, 'chat')
                chat_queue.put(chat_task)
        elif app_state.value != AppState.CHAT:
            if user_input == "#唱歌结束":
                # cmd_queue.put("#唱歌结束")
                sing_queue.put("666切歌")
            elif user_input == "#一键三连":
                cmd_queue.put("#一键三连")
            elif user_input == "#点赞":
                msg = f"给你点赞！"
                task = ChatTask(None, msg, 'default')
                thanks_queue.put(task)

    event_danmaku_process_stop.set()
    # Clear all queues
    clear_queue(chat_queue)
    chat_queue.put(None)
    print("The chat_queue is cleared")
    clear_queue(vits_task_queue)
    vits_task_queue.put(None)
    print("The vits_task_queue is cleared")
    clear_queue(audio_task_queue)
    audio_task_queue.put(None)
    print("The audio_task_queue is cleared")
    clear_queue(subtitle_task_queue)
    subtitle_task_queue.put(None)
    print("The subtitle_task_queue is cleared")
    clear_queue(sing_queue)
    sing_queue.put(None)
    print("The sing_queue is cleared")
    clear_queue(cmd_queue)
    cmd_queue.put(None)
    print("The cmd_queue is cleared")
    clear_queue(vts_api_queue)
    vts_api_queue.put(None)
    print("The vts_api_queue is cleared")

    print("All queues are cleared")

    chat_gpt_process.join()
    print("chat_gpt_process is joined")
    damaku_process.join()
    print("damaku_process is joined")
    song_singer_process.join()
    print("song_singer_process is joined")
    audio_player_process.join()
    print("audio_player_process is joined")
    subtitle_bar_process.join()
    print("subtitle_bar_process is joined")
    vts_api_process.join()
    print("vts_api_process is joined")
    vits_process.join()
    print("vits_process is joined")
