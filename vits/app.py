# coding=utf-8
import time
import gradio as gr
import utils
import commons
from models import SynthesizerTrn
from text import text_to_sequence
from torch import no_grad, LongTensor

hps_ms = utils.get_hparams_from_file(r'./model/config.json')
net_g_ms = SynthesizerTrn(
    len(hps_ms.symbols),
    hps_ms.data.filter_length // 2 + 1,
    hps_ms.train.segment_size // hps_ms.data.hop_length,
    n_speakers=hps_ms.data.n_speakers,
    **hps_ms.model)
_ = net_g_ms.eval()
speakers = hps_ms.speakers
model, optimizer, learning_rate, epochs = utils.load_checkpoint(r'./model/G_953000.pth', net_g_ms, None)

def get_text(text, hps):
    text_norm, clean_text = text_to_sequence(text, hps.symbols, hps.data.text_cleaners)
    if hps.data.add_blank:
        text_norm = commons.intersperse(text_norm, 0)
    text_norm = LongTensor(text_norm)
    return text_norm, clean_text

def vits(text, language, speaker_id, noise_scale, noise_scale_w, length_scale):
    start = time.perf_counter()
    if not len(text):
        return "输入文本不能为空！", None, None
    text = text.replace('\n', ' ').replace('\r', '').replace(" ", "")
    if len(text) > 100:
        return f"输入文字过长！{len(text)}>100", None, None
    if language == 0:
        text = f"[ZH]{text}[ZH]"
    elif language == 1:
        text = f"[JA]{text}[JA]"
    else:
        text = f"{text}"
    stn_tst, clean_text = get_text(text, hps_ms)
    with no_grad():
        x_tst = stn_tst.unsqueeze(0)
        x_tst_lengths = LongTensor([stn_tst.size(0)])
        speaker_id = LongTensor([speaker_id])
        audio = net_g_ms.infer(x_tst, x_tst_lengths, sid=speaker_id, noise_scale=noise_scale, noise_scale_w=noise_scale_w,
                               length_scale=length_scale)[0][0, 0].data.float().numpy()

    return "生成成功!", (22050, audio), f"生成耗时 {round(time.perf_counter()-start, 2)} s"

def search_speaker(search_value):
    for s in speakers:
        if search_value == s:
            return s
    for s in speakers:
        if search_value in s:
            return s

def change_lang(language):
    if language == 0:
        return 0.6, 0.668, 1.2
    else:
        return 0.6, 0.668, 1.1

download_audio_js = """
() =>{{
    let root = document.querySelector("body > gradio-app");
    if (root.shadowRoot != null)
        root = root.shadowRoot;
    let audio = root.querySelector("#tts-audio").querySelector("audio");
    let text = root.querySelector("#input-text").querySelector("textarea");
    if (audio == undefined)
        return;
    text = text.value;
    if (text == undefined)
        text = Math.floor(Math.random()*100000000);
    audio = audio.src;
    let oA = document.createElement("a");
    oA.download = text.substr(0, 20)+'.wav';
    oA.href = audio;
    document.body.appendChild(oA);
    oA.click();
    oA.remove();
}}
"""

if __name__ == '__main__':
    with gr.Blocks() as app:
        gr.Markdown(
            "# <center> VITS语音在线合成demo\n"
            "<div align='center'>主要有赛马娘，原神中文，原神日语，崩坏3的音色</div>"
            '<div align="center"><a><font color="#dd0000">结果有随机性，语调可能很奇怪，可多次生成取最佳效果</font></a></div>'
            '<div align="center"><a><font color="#dd0000">标点符号会影响生成的结果</font></a></div>'
        )

        with gr.Tabs():
            with gr.TabItem("vits"):
                with gr.Row():
                    with gr.Column():
                        input_text = gr.Textbox(label="Text (100 words limitation)", lines=5, value="今天晚上吃啥好呢。", elem_id=f"input-text")
                        lang = gr.Dropdown(label="Language", choices=["中文", "日语", "中日混合（中文用[ZH][ZH]包裹起来，日文用[JA][JA]包裹起来）"],
                                    type="index", value="中文")
                        btn = gr.Button(value="Submit")
                        with gr.Row():
                            search = gr.Textbox(label="Search Speaker", lines=1)
                            btn2 = gr.Button(value="Search")
                        sid = gr.Dropdown(label="Speaker", choices=speakers, type="index", value=speakers[228])
                        with gr.Row():
                            ns = gr.Slider(label="noise_scale(控制感情变化程度)", minimum=0.1, maximum=1.0, step=0.1, value=0.6, interactive=True)
                            nsw = gr.Slider(label="noise_scale_w(控制音素发音长度)", minimum=0.1, maximum=1.0, step=0.1, value=0.668, interactive=True)
                            ls = gr.Slider(label="length_scale(控制整体语速)", minimum=0.1, maximum=2.0, step=0.1, value=1.2, interactive=True)
                    with gr.Column():
                        o1 = gr.Textbox(label="Output Message")
                        o2 = gr.Audio(label="Output Audio", elem_id=f"tts-audio")
                        o3 = gr.Textbox(label="Extra Info")
                        download = gr.Button("Download Audio")
                    btn.click(vits, inputs=[input_text, lang, sid, ns, nsw, ls], outputs=[o1, o2, o3])
                    download.click(None, [], [], _js=download_audio_js.format())
                    btn2.click(search_speaker, inputs=[search], outputs=[sid])
                    lang.change(change_lang, inputs=[lang], outputs=[ns, nsw, ls])
            with gr.TabItem("可用人物一览"):
                gr.Radio(label="Speaker", choices=speakers, interactive=False, type="index")
    app.queue(concurrency_count=1).launch()
