import sys
import os
import time

import numpy as np

from torch import no_grad, LongTensor
from torch import device as torch_device

import wave
import pyaudio

dir_path = os.path.dirname(os.path.realpath(__file__))

# Get the parent directory
parent_dir = os.path.dirname(dir_path)
print(parent_dir)
vits_dir = os.path.join(parent_dir, 'vits')
print(vits_dir)

# sys.path.append(vits_dir)
sys.path.insert(0, vits_dir)
print(sys.path)

import utils
import commons as commons
from models import SynthesizerTrn
from text import text_to_sequence

class VITSWrapper:
    def __init__(self):
        # device = torch_device('cpu')
        self.device = torch_device('cuda')

        self.hps_ms = utils.get_hparams_from_file('../vits/model/config.json')
        speakers = self.hps_ms.speakers

        with no_grad():
            self.net_g_ms = SynthesizerTrn(
                len(self.hps_ms.symbols),
                self.hps_ms.data.filter_length // 2 + 1,
                self.hps_ms.train.segment_size // self.hps_ms.data.hop_length,
                n_speakers=self.hps_ms.data.n_speakers,
                **self.hps_ms.model).to(self.device)
            _ = self.net_g_ms.eval()
            model, optimizer, learning_rate, epochs = utils.load_checkpoint('../vits/model/G_953000.pth', 
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

# def normalize_audio(audio_data):
#     # Calculate the mean and standard deviation of the audio data
#     mean = np.mean(audio_data)
#     std = np.std(audio_data)
    
#     # Normalize the audio data using z-score normalization
#     normalized_data = (audio_data - mean) / std
    
#     return normalized_data


if __name__ == '__main__':
    text = "一马当先，万马牡蛎！"

    py_audio = pyaudio.PyAudio()

    wf = wave.open("test.wav", 'rb')

    sample_width = wf.getsampwidth()
    print(f"sample_width: {sample_width}")

    format = py_audio.get_format_from_width(sample_width)
    print(f"format: {format}")

    num_channels = wf.getnchannels()
    print(f"num_channels: {num_channels}")

    frame_rate = wf.getframerate()
    print(f"frame_rate: {frame_rate}")

    data_from_file = wf.readframes(wf.getnframes())

    wf.close()

    vits_wrapper = VITSWrapper()

    # https://stackoverflow.com/questions/59463040/how-can-i-convert-a-numpy-array-wav-data-to-int16-with-python
    # pyaudio.paFloat32
    # np.float32

    stream = py_audio.open(format=format,
                        channels=num_channels,
                        rate=frame_rate,
                        output=True)

    stream_float32 = py_audio.open(format=pyaudio.paFloat32,
                        channels=1,
                        rate=22050,
                        output=True)

    audio = vits_wrapper.vits(text, 0, 2, 0.5, 0.5, 1.0)
    print(audio.dtype)
    audio_x2 = audio * 2
    data = audio_x2.tobytes()

    # https://stackoverflow.com/questions/59463040/how-can-i-convert-a-numpy-array-wav-data-to-int16-with-python
    data_int16 = (audio * 32767).astype(np.int16).tobytes()
    
    blah = np.array([32767.9])
    blah = blah.astype(np.int16)
    print(blah)
    
    data_norm = normalize_audio(audio).tobytes()

    while True:
        user_input = input("Press Enter to continue\n")
        if user_input == "esc":
            break

        stream.write(data_from_file)
        stream_float32.write(data) # Explosion noise
        stream.write(data_int16)

        stream_float32.write(data_norm)

    stream.close()
    stream_float32.close()
    py_audio.terminate()