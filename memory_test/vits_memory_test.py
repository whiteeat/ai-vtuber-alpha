import sys
import os
import time

from torch import no_grad, LongTensor
from torch import device as torch_device

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

# device = torch_device('cpu')
device = torch_device('cuda')

hps_ms = utils.get_hparams_from_file(r'../vits/model/config.json')
speakers = hps_ms.speakers

with no_grad():
    net_g_ms = SynthesizerTrn(
        len(hps_ms.symbols),
        hps_ms.data.filter_length // 2 + 1,
        hps_ms.train.segment_size // hps_ms.data.hop_length,
        n_speakers=hps_ms.data.n_speakers,
        **hps_ms.model).to(device)
    _ = net_g_ms.eval()
    model, optimizer, learning_rate, epochs = utils.load_checkpoint(r'../vits/model/G_953000.pth', 
                                                                    net_g_ms, None)
                  

def get_text(text, hps):
    text_norm, clean_text = text_to_sequence(text, hps.symbols, hps.data.text_cleaners)
    if hps.data.add_blank:
        text_norm = commons.intersperse(text_norm, 0)
    text_norm = LongTensor(text_norm)
    return text_norm, clean_text

def vits(text, language, speaker_id, noise_scale, noise_scale_w, length_scale):
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
    stn_tst, clean_text = get_text(text, hps_ms)

    start = time.perf_counter()
    with no_grad():
        x_tst = stn_tst.unsqueeze(0).to(device)
        x_tst_lengths = LongTensor([stn_tst.size(0)]).to(device)
        speaker_id = LongTensor([speaker_id]).to(device)

        input("Press any key to continue")

        audio = net_g_ms.infer(x_tst, x_tst_lengths, sid=speaker_id, noise_scale=noise_scale,
                                    noise_scale_w=noise_scale_w,
                                    length_scale=length_scale)[0][0, 0].data.cpu().float().numpy()
    
    print(f"The inference takes {time.perf_counter() - start} seconds")

    import gc
    import torch
    gc.collect()
    torch.cuda.empty_cache()

    return audio

text = "这是一个测试"
while True:
    audio = vits(text, 0, 2, 0.5, 0.5, 1.0)

    user_input = input("Press any key to continue")
    if user_input == "esc":
        break
