import multiprocessing
import time

import wave
import pyaudio

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

        stream_vox = py_audio.open(format=py_audio.get_format_from_width(wf_vox.getsampwidth()),
                        channels=wf_vox.getnchannels(),
                        rate=wf_vox.getframerate(),
                        output=True)
        
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
            else:
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

        # self.event_speech = multiprocessing.Event()
        # self.event_exit = multiprocessing.Event()

        wf = wave.open("speech.wav", 'rb')

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
            
            if GlobalState.speech_event.is_set():
                while True:
                    data = wf.readframes(CHUNK)
                    if len(data) != 0:
                        stream.write(data)
                    else:
                        break

                wf.rewind()
                time.sleep(0.5)
                GlobalState.speech_event.clear()

            time.sleep(0)

        print("Speech ends.")

        stream.close()
        wf.close()

        py_audio.terminate()

if __name__ == '__main__':
    print("Start")

    # get the current start method
    method = multiprocessing.get_start_method()
    print(f"{method}")

    event_exit = multiprocessing.Event()
    event_speech = multiprocessing.Event()

    # singing_process = SingingProcess()
    singing_process = SingingProcess_1()
    speech_process = SpeechProcess()

    singing_process.event_exit = event_exit
    speech_process.event_exit = event_exit
    singing_process.event_speech = event_speech
    speech_process.event_speech = event_speech

    GlobalState.speech_event = multiprocessing.Event()
    print(f"""Process name: {multiprocessing.current_process().name}. 
            Global event object: {GlobalState.speech_event}. Global event id: {id(GlobalState.speech_event)}""")
    speech_process.speech_event = GlobalState.speech_event
    singing_process.speech_event = GlobalState.speech_event

    _ = input("Press Enter to sing\n")
    singing_process.start()
    speech_process.start()

    while True:
        user_input = input("Press Enter to speak\n")
        if user_input == "esc":
            speech_process.event_exit.set()
            break
        else:
            GlobalState.speech_event.set()

    singing_process.join()
    speech_process.join()