import wave

import pyaudio

p = pyaudio.PyAudio()

# https://vb-audio.com/Cable/

PRINT_DEVICES = True

if PRINT_DEVICES:

    def write_dict(f, dictionary):
        for key, value in dictionary.items():
            f.write(f"{key}:{value}\n")

    output = "Devices Info.txt"
    with open(output, 'w', encoding='utf-8') as f:
        print("Default Devices:")
        f.write("Default Devices:")
        print(p.get_default_host_api_info())
        write_dict(f, p.get_default_host_api_info())

        print(p.get_default_input_device_info())
        write_dict(f, p.get_default_input_device_info())

        print(p.get_default_output_device_info())
        write_dict(f, p.get_default_output_device_info())

        print("All Devices:")
        for i in range(p.get_device_count()):
            print(p.get_device_info_by_index(i))
            write_dict(f, p.get_device_info_by_index(i))

virtual_audio_input_device_index = None
virtual_audio_output_device_index = None

# Search for valid virtual audio input and output devices
for i in range(p.get_device_count()):
    device_info = p.get_device_info_by_index(i)
    if ("CABLE Output" in device_info['name'] and
        device_info['hostApi'] == 0):
        assert device_info['index'] == i 
        virtual_audio_input_device_index = i
    
    if ("CABLE Input" in device_info['name'] and
        device_info['hostApi'] == 0):
        assert device_info['index'] == i
        virtual_audio_output_device_index = i

if (virtual_audio_input_device_index is None or
    virtual_audio_output_device_index is None):
    print("Error: no valid virtual audio devices found")
    exit()

CHUNK = 1024

with wave.open("test.wav", 'rb') as wf:
    # Open stream (2)
    stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True,
                    input_device_index=virtual_audio_input_device_index,
                    output_device_index=virtual_audio_output_device_index)

    # Play samples from the wave file (3)
    while len(data := wf.readframes(CHUNK)):  # Requires Python 3.8+ for :=
        stream.write(data)

    # Close stream (4)
    stream.close()

with wave.open("test.wav", 'rb') as wf:
    stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True)

    while len(data := wf.readframes(CHUNK)): 
        stream.write(data)

    stream.close()

# Release PortAudio system resources (5)
p.terminate()
