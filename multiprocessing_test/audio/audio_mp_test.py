import sys
import os
import multiprocessing
import time

import numpy as np

import wave
import pyaudio

from torch import no_grad, LongTensor
from torch import device as torch_device

dir_path = os.path.dirname(os.path.realpath(__file__))

# Get the parent directory
parent_dir = os.path.dirname(dir_path)
project_path = os.path.dirname(parent_dir)
print(project_path)
vits_dir = os.path.join(project_path, 'vits')
print(vits_dir)

# sys.path.append(vits_dir)
sys.path.insert(0, vits_dir)
print(sys.path)

import utils
import commons as commons
from models import SynthesizerTrn
from text import text_to_sequence

from global_state import GlobalState

class SingingProcess(multiprocessing.Process):

    def run(self):
        CHUNK = 1024

        wf = wave.open("vox.wav", 'rb')

        py_audio = pyaudio.PyAudio()

        stream = py_audio.open(format=py_audio.get_format_from_width(wf.getsampwidth()),
                        channels=wf.getnchannels(),
                        rate=wf.getframerate(),
                        output=True)
        
        GlobalState.speech_event = self.speech_event
        print(f"""Process name: {multiprocessing.current_process().name}. 
                Global event object: {GlobalState.speech_event}. Global event id: {id(GlobalState.speech_event)}""")

        while True:
            if self.event_exit.is_set():
                break

            data = wf.readframes(CHUNK)
            size = len(data)
            if size != 0:
                if GlobalState.speech_event.is_set():
                    # https://www.programiz.com/python-programming/methods/built-in/bytes
                    junk = bytes(size)
                    stream.write(junk)
                else:
                    stream.write(data)
            else:
                break

            time.sleep(0)    

        print("Singing ends.")

        stream.close()
        wf.close()

        py_audio.terminate()

class SingingProcess_1(multiprocessing.Process):

    def run(self):
        CHUNK = 1024
        enable_write_junk = True

        wf_vox = wave.open("vox.wav", 'rb')
        wf_bgm = wave.open("bgm.wav", 'rb')

        py_audio = pyaudio.PyAudio()

        device_index = None
        if self.use_virtual_audio_device:
            device_index = self.virtual_audio_output_device_index

        stream_vox = py_audio.open(format=py_audio.get_format_from_width(wf_vox.getsampwidth()),
                        channels=wf_vox.getnchannels(),
                        rate=wf_vox.getframerate(),
                        output=True,
                        output_device_index=device_index)
        
        stream_bgm = py_audio.open(format=py_audio.get_format_from_width(wf_vox.getsampwidth()),
                channels=wf_vox.getnchannels(),
                rate=wf_vox.getframerate(),
                output=True)
        
        GlobalState.speech_event = self.speech_event
        print(f"""Process name: {multiprocessing.current_process().name}. 
                Global event object: {GlobalState.speech_event}. Global event id: {id(GlobalState.speech_event)}""")

        junk = None
        init_junk = True
        while True:
            if self.event_exit.is_set():
                break

            data_vox = wf_vox.readframes(CHUNK)
            data_bgm = wf_bgm.readframes(CHUNK)
            size_vox = len(data_vox)
            size_bgm = len(data_bgm)

            if init_junk:
                junk = bytes(size_vox)
                init_junk = False

            if size_bgm != 0:
                stream_bgm.write(data_bgm)
            if size_vox != 0:
                if not GlobalState.speech_event.is_set():
                    stream_vox.write(data_vox)
                else:
                    if enable_write_junk:
                        stream_vox.write(junk)

            if size_bgm == 0 and size_vox == 0:
                break

            time.sleep(0)    

        print("Singing ends.")

        stream_vox.close()
        stream_bgm.close()
        wf_vox.close()
        wf_bgm.close()

        py_audio.terminate()

class SingingProcess_2(multiprocessing.Process):

    def run(self):
        CHUNK = 1024
        enable_write_junk = False

        wf_vox = wave.open("vox.wav", 'rb')
        wf_bgm = wave.open("bgm.wav", 'rb')

        py_audio = pyaudio.PyAudio()

        # Write vox data into virtual audio device to drive lip sync animation
        if self.use_virtual_audio_device:
            device_index = self.virtual_audio_output_device_index
            stream_virtual = py_audio.open(format=py_audio.get_format_from_width(wf_vox.getsampwidth()),
                            channels=wf_vox.getnchannels(),
                            rate=wf_vox.getframerate(),
                            output=True,
                            output_device_index=device_index)
        
        stream_bgm = py_audio.open(format=py_audio.get_format_from_width(wf_vox.getsampwidth()),
                channels=wf_vox.getnchannels(),
                rate=wf_vox.getframerate(),
                output=True)
        
        stream_vox = py_audio.open(format=py_audio.get_format_from_width(wf_vox.getsampwidth()),
                channels=wf_vox.getnchannels(),
                rate=wf_vox.getframerate(),
                output=True)

        GlobalState.speech_event = self.speech_event
        print(f"""Process name: {multiprocessing.current_process().name}. 
                Global event object: {GlobalState.speech_event}. Global event id: {id(GlobalState.speech_event)}""")

        junk = None
        init_junk = True
        while True:
            if self.event_exit.is_set():
                break

            data_vox = wf_vox.readframes(CHUNK)
            data_bgm = wf_bgm.readframes(CHUNK)
            size_vox = len(data_vox)
            size_bgm = len(data_bgm)

            if init_junk:
                junk = bytes(size_vox)
                init_junk = False

            if size_bgm != 0:
                stream_bgm.write(data_bgm)
            if size_vox != 0:  
                if not GlobalState.speech_event.is_set():
                    stream_vox.write(data_vox)
                    if self.use_virtual_audio_device:
                        stream_virtual.write(data_vox)
                else:
                    if enable_write_junk:
                        stream_vox.write(junk)

            if size_bgm == 0 and size_vox == 0:
                break

            time.sleep(0)    

        print("Singing ends.")

        stream_vox.close()
        stream_bgm.close()
        wf_vox.close()
        wf_bgm.close()

        py_audio.terminate()


class SpeechProcess(multiprocessing.Process):

    def run(self):
        CHUNK = 1024
        enable_write_chunk = False

        wf = wave.open("speech.wav", 'rb')

        py_audio = pyaudio.PyAudio()

        device_index = None

        if self.use_virtual_audio_device:
            device_index = self.virtual_audio_output_device_index

        stream = py_audio.open(format=py_audio.get_format_from_width(wf.getsampwidth()),
                        channels=wf.getnchannels(),
                        rate=wf.getframerate(),
                        output=True,
                        output_device_index=device_index)
        
        GlobalState.speech_event = self.speech_event
        print(f"""Process name: {multiprocessing.current_process().name}. 
                Global event object: {GlobalState.speech_event}. Global event id: {id(GlobalState.speech_event)}""")

        while True:
            if self.event_exit.is_set():
                break
            
            if GlobalState.speech_event.is_set():
                if enable_write_chunk:
                    while True:
                        data = wf.readframes(CHUNK)
                        if len(data) != 0:
                            stream.write(data)
                        else:
                            break
                else:
                    # https://stackoverflow.com/questions/28128905/python-wave-readframes-doesnt-return-all-frames-on-windows
                    data = wf.readframes(wf.getnframes())
                    stream.write(data)

                wf.rewind()
                time.sleep(0.5)
                GlobalState.speech_event.clear()

            time.sleep(0)

        print("Speech ends.")

        stream.close()
        wf.close()

        py_audio.terminate()


class VITSWrapper:
    def __init__(self):
        # device = torch_device('cpu')
        self.device = torch_device('cuda')

        hparams_path = os.path.join(project_path, 'vits/model/config.json')
        self.hps_ms = utils.get_hparams_from_file(hparams_path)
        speakers = self.hps_ms.speakers

        with no_grad():
            self.net_g_ms = SynthesizerTrn(
                len(self.hps_ms.symbols),
                self.hps_ms.data.filter_length // 2 + 1,
                self.hps_ms.train.segment_size // self.hps_ms.data.hop_length,
                n_speakers=self.hps_ms.data.n_speakers,
                **self.hps_ms.model).to(self.device)
            _ = self.net_g_ms.eval()
            checkpoint_path = os.path.join(project_path, 'vits/model/G_953000.pth')
            model, optimizer, learning_rate, epochs = utils.load_checkpoint(checkpoint_path, 
                                                                            self.net_g_ms, None)
                  
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


# By ChatGPT
def normalize_audio(audio_data):
    # Calculate the maximum absolute value in the audio data
    max_value = np.max(np.abs(audio_data))
    
    # Normalize the audio data by dividing it by the maximum value
    normalized_data = audio_data / max_value
    
    return normalized_data


# https://stackoverflow.com/questions/434287/how-to-iterate-over-a-list-in-chunks
def chunker(seq, size):
    return [seq[pos:pos + size] for pos in range(0, len(seq), size)]


class SpeechProcess_1(multiprocessing.Process):

    def run(self):
        text = "一马当先，万马牡蛎！"

        use_norm = True

        vits_wrapper = VITSWrapper()
        audio = vits_wrapper.vits(text, 0, 2, 0.5, 0.5, 1.0)
        print(audio.shape)
        print(audio.dtype)
        if use_norm:
            # https://stackoverflow.com/questions/70722435/does-ndarray-tobytes-create-a-copy-of-raw-data
            data = normalize_audio(audio).view(np.uint8) # No copy
            # data = normalize_audio(audio).tobytes() # This will copy
        else:
            data = audio.tobytes()

        py_audio = pyaudio.PyAudio()
        stream = py_audio.open(format=pyaudio.paFloat32,
                            channels=1,
                            rate=22050,
                            output=True)
        
        if self.use_virtual_audio_device:
            device_index = self.virtual_audio_output_device_index
            stream_virtual = py_audio.open(format=pyaudio.paFloat32,
                        channels=1,
                        rate=22050,
                        output=True,
                        output_device_index=device_index)
            
        
        NUM_FRAMES = 1024
        BIT_DEPTH = 32
        NUM_BYTES_PER_SAMPLE = BIT_DEPTH // 8
        NUM_CHANNELS = 1
        CHUNK_SIZE = NUM_FRAMES * NUM_BYTES_PER_SAMPLE * NUM_CHANNELS # Data chunk size in bytes

        chunks = chunker(data, CHUNK_SIZE)
        print(f"Number of chunks: {len(chunks)}")
        
        GlobalState.speech_event = self.speech_event
        print(f"""Process name: {multiprocessing.current_process().name}. 
            Global event object: {GlobalState.speech_event}. Global event id: {id(GlobalState.speech_event)}""")

        while True:
            if self.event_exit.is_set():
                break
            
            if GlobalState.speech_event.is_set():
                for chunk in chunks:
                    stream.write(chunk)
                    if self.use_virtual_audio_device:
                        # Write speech data into virtual audio device to drive lip sync animation
                        stream_virtual.write(chunk)
                GlobalState.speech_event.clear()
            
            time.sleep(0)

        print("Speech ends.")

        stream.close()
        py_audio.terminate()

if __name__ == '__main__':
    print("Start")

    # get the current start method
    method = multiprocessing.get_start_method()
    print(f"{method}")

    event_exit = multiprocessing.Event()
    use_vits = True

    # singing_process = SingingProcess()
    singing_process = SingingProcess_2()

    if use_vits:
        speech_process = SpeechProcess_1()
    else:
        speech_process = SpeechProcess()

    singing_process.event_exit = event_exit
    speech_process.event_exit = event_exit

    GlobalState.speech_event = multiprocessing.Event()
    print(f"""Process name: {multiprocessing.current_process().name}. 
            Global event object: {GlobalState.speech_event}. Global event id: {id(GlobalState.speech_event)}""")
    speech_process.speech_event = GlobalState.speech_event
    singing_process.speech_event = GlobalState.speech_event

    py_audio = pyaudio.PyAudio()
    virtual_audio_output_device_index = None

    # Search for valid virtual audio input and output devices
    for i in range(py_audio.get_device_count()):
        device_info = py_audio.get_device_info_by_index(i)
        
        if ("CABLE Input" in device_info['name'] and
            device_info['hostApi'] == 0):
            assert device_info['index'] == i
            virtual_audio_output_device_index = i

    if virtual_audio_output_device_index is None:
        print("Error: no valid virtual audio devices found")
    
    py_audio.terminate()

    singing_process.virtual_audio_output_device_index = virtual_audio_output_device_index
    singing_process.use_virtual_audio_device = True
    speech_process.virtual_audio_output_device_index = virtual_audio_output_device_index
    speech_process.use_virtual_audio_device = True

    _ = input("Press Enter to sing\n")
    singing_process.start()
    speech_process.start()

    while True:
        user_input = input("Press Enter to speak\n")
        if user_input == "esc":
            event_exit.set()
            break
        else:
            GlobalState.speech_event.set()

    singing_process.join()
    speech_process.join()