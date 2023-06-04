"""
client 端支持 HTTP/2 协议
https://httpwg.org/specs/rfc9113.html
"""
import io
import socket

SETTINGS_HEADER_TABLE_SIZE = 0x1
SETTINGS_ENABLE_PUSH = 0x2
SETTINGS_MAX_CONCURRENT_STREAMS = 0x3
SETTINGS_INITIAL_WINDOW_SIZE = 0x4
SETTINGS_MAX_FRAME_SIZE = 0x5
SETTINGS_MAX_HEADER_LIST_SIZE = 0x6


class Frame:
    type = -1
    def __init__(self, type_number: int):
        self._data = io.BytesIO()
        b = type_number.to_bytes(1, 'big')
        self._data.write(b)

    def add_raw_bytes(self, b: bytes):
        self._data.write(b)

    def set_stream_identifier(self, identifier: int):
        b = identifier.to_bytes(4, 'big')
        self._data.write(b)

    def get_stream_identifier(self) -> int:
        b = self._data.read(4)
        return int.from_bytes(b, 'big')

    def as_bytes(self):
        b = self._data.getvalue()
        length = len(b)
        # 3 字节长度 + 数据
        return length.to_bytes(3, "big") + b


class SettingsFrame(Frame):
    type = 4
    def __init__(self):
        super().__init__(self.type)

    def set_ack(self, ack: bool):
        if ack:
            self._data.write(b'\x01')
        else:
            self._data.write(b'\x00')

    def get_ack(self):
        b = self._data.read(1)
        return b == b'\x01'

    def add_setting(self, identifier: int, value: int):
        b = identifier.to_bytes(2, 'big')
        self._data.write(b)
        b = value.to_bytes(4, 'big')
        self._data.write(b)


class FrameIO:
    def __init__(self, sock: socket.socket):
        self._sock = sock

    def write_frame(self, frame: "Frame"):
        self._sock.sendall(frame.as_bytes())

    def read_frame(self) -> "Frame":
        while True:
            b = self._sock.recv(3)
            length = int.from_bytes(b, 'big')
            data = self._sock.recv(length)
            if data[0] == 4:
                frame = SettingsFrame()
                frame.add_raw_bytes(data)
                if frame.get_ack():
                    continue
                return frame

    def ack_settings(self):
        frame = SettingsFrame()
        frame.set_ack(True)
        self.write_frame(frame)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 8080))
    # 假设服务端支持 HTTP/2 ，那么直接开始 HTTP/2 就行
    # connection preface
    sock.sendall(b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n")
    # 发送 SETTINGS frame 消息
    # https://httpwg.org/specs/rfc9113.html#rfc.section.6.5
    settings_frame = SettingsFrame()
    settings_frame.set_ack(False)
    settings_frame.set_stream_identifier(0)
    # 设置直接用 wireshark 抓到的包
    settings_frame.add_setting(SETTINGS_HEADER_TABLE_SIZE, 4096)
    settings_frame.add_setting(SETTINGS_ENABLE_PUSH, 0)
    settings_frame.add_setting(SETTINGS_INITIAL_WINDOW_SIZE, 65535)
    settings_frame.add_setting(SETTINGS_MAX_FRAME_SIZE, 16384)
    settings_frame.add_setting(SETTINGS_MAX_CONCURRENT_STREAMS, 100)
    settings_frame.add_setting(SETTINGS_MAX_HEADER_LIST_SIZE, 65536)
    sock.sendall(settings_frame.as_bytes())

    # 读取 server 发送 settings frame
    frame_io = FrameIO(sock)
    frame = frame_io.read_frame()
    print(frame.as_bytes())
    if frame.type == 4:
        frame_io.ack_settings()

    # 相互 ack settings 之后，一个 HTTP2 连接就建立了

    sock.close()


if __name__ == '__main__':
    main()
