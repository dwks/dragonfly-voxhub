import pyaudio
import audioop
import threading

class SilviusMicrophoneManager:
    # Note: this will get created once per process.
    pyaudio_instance = None

    @staticmethod
    def get_pa():
        if not SilviusMicrophoneManager.pyaudio_instance:
            # prints a lot of junk, but no avoiding it
            SilviusMicrophoneManager.pyaudio_instance = pyaudio.PyAudio()
        return SilviusMicrophoneManager.pyaudio_instance

    @staticmethod
    def dump_list():
        pa = SilviusMicrophoneManager.get_pa()

        print("")
        print("LISTING OF ALL INPUT DEVICES SUPPORTED BY PORTAUDIO.")
        print("Device can be configured by adding <DEVICE_NUMBER> under device in silvius_config.py")
        print("(any device numbers not shown are for output only)")
        print("")

        for i in range(0, pa.get_device_count()):
            info = pa.get_device_info_by_index(i)

            if info['maxInputChannels'] > 0:  # microphone? or just speakers
                print("DEVICE_NUMBER = %d" % info['index'])
                print("    %s" % info['name'])
                print("    input channels = %d, output channels = %d, defaultSampleRate = %d" \
                    % (info['maxInputChannels'], info['maxOutputChannels'], info['defaultSampleRate']))
                #print(info)

    @staticmethod
    def lookup_microphone_helper(name):
        pa = SilviusMicrophoneManager.get_pa()

        for i in range(0, pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if(name in info['name']):
                return info['index']
        return -1  # use default microphone

    @staticmethod
    def lookup_microphone(name):
        try:
            # if the user gave us a number, no conversion necessary
            return int(name)
        except ValueError:
            pass
        except TypeError:
            pass

        if(isinstance(name, list)):
            for value in name:
                print("Trying microphone '" + value + "'...")
                m = SilviusMicrophoneManager.lookup_microphone_helper(value)
                if(m != -1):
                    print("    found!")
                    return m
            print("WARNING: no specified microphones found, trying default")
        else:
            m = SilviusMicrophoneManager.lookup_microphone_helper(name)
            if(m != -1): return m
            print("WARNING: specified microphone '" + name + "' not found, trying default")

        return -1  # use default microphone

    @staticmethod
    def open(mic_index, byte_rate, chunk):
        pa = SilviusMicrophoneManager.get_pa()
        stream = None
        original_byte_rate = byte_rate

        while stream is None:
            try:
                if mic_index == -1:
                    mic_index = pa.get_default_input_device_info()['index']
                    print("Selecting default mic")
                print("Using mic #", mic_index)
                stream = pa.open(
                    rate        = byte_rate,
                    format      = pyaudio.paInt16,
                    channels    = 1,
                    input       = True,
                    input_device_index = mic_index,
                    frames_per_buffer  = chunk)
                print("Creating microphone with", byte_rate, stream)
                return SilviusMicrophone(original_byte_rate, byte_rate, stream, chunk)
            except IOError as e:
                if e.errno == -9997 or e.errno == 'Invalid sample rate':
                    new_sample_rate = int(pa.get_device_info_by_index(mic_index)['defaultSampleRate'])
                    if byte_rate != new_sample_rate:
                        byte_rate = new_sample_rate
                        continue
                print(str(e))
                print("\nCould not open microphone. Please try a different device.")
                return None

class SilviusMicrophone:
    def __init__(self, original_byte_rate, byte_rate, stream, chunk):
        self.original_byte_rate = original_byte_rate
        self.byte_rate = byte_rate
        self.stream = stream
        self.chunk = chunk
        self.audio_gate = 0

    def set_audio_gate(self, gate):
        self.audio_gate = gate

    def start_thread(self, data_callback, finished_callback=None):
        print("Starting microphone thread...")
        def listen_to_mic():  # uses self.stream
            print("\nLISTENING TO MICROPHONE")
            last_state = None
            running = True
            while running:
                bytes_to_read = int(self.chunk * self.byte_rate / self.original_byte_rate)
                data = self.stream.read(bytes_to_read)
                if self.audio_gate > 0:
                    rms = audioop.rms(data, 2)
                    if rms < self.audio_gate:
                        data = '\00' * len(data)
                if self.byte_rate != self.original_byte_rate:
                    (data, last_state) = audioop.ratecv(data, 2, 1, self.original_byte_rate, self.byte_rate, last_state)

                running = data_callback(data)

            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass

            if finished_callback:
                finished_callback()

        threading.Thread(target=listen_to_mic).start()