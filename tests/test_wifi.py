import ctypes
import struct

import pytest

from network_weather.models import WifiSnapshot
from network_weather.wifi import WifiCache, _channel_number, _quality_percent, _rssi_dbm


def test_optional_native_wifi_fields_accept_only_plausible_values():
    assert _quality_percent(struct.pack("<6I", 0, 73, 0, 0, 0, 1)) == 73
    assert _quality_percent(struct.pack("<6I", 0, 101, 0, 0, 0, 1)) is None
    assert _quality_percent(b"short") is None
    assert _rssi_dbm(struct.pack("<i", -61)) == -61
    assert _rssi_dbm(struct.pack("<i", 999)) is None
    assert _channel_number(struct.pack("<I", 44)) == 44
    assert _channel_number(struct.pack("<I", 0)) is None


def test_wifi_cache_refreshes_and_keeps_optional_failures_out_of_probe_rounds(monkeypatch):
    from network_weather import wifi

    calls = []
    snapshot = WifiSnapshot("Test radio", 75, -60, 44)
    monkeypatch.setattr(wifi.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(wifi, "connected_wifi", lambda: calls.append(1) or (snapshot,))
    cache = WifiCache()
    assert cache.current() == (snapshot,)
    assert cache.current() == (snapshot,)
    assert len(calls) == 1
    cache.invalidate()
    assert cache.current() == (snapshot,)
    assert len(calls) == 2
    monkeypatch.setattr(wifi, "connected_wifi", lambda: (_ for _ in ()).throw(OSError("WLAN")))
    cache.invalidate()
    assert cache.current() == ()


def test_wifi_snapshot_rejects_fabricated_ranges():
    with pytest.raises(ValueError):
        WifiSnapshot("radio", signal_quality_percent=140)
    with pytest.raises(ValueError):
        WifiSnapshot("radio", rssi_dbm=20)


def test_native_wifi_query_reads_connected_radio_and_frees_buffers(monkeypatch):
    from network_weather import wifi

    class FakeFunction:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    class FakeApi:
        def __init__(self):
            self.buffers = []
            self.freed = []
            self.opcodes = []
            self.closed = False
            self.WlanOpenHandle = FakeFunction(self.open)
            self.WlanEnumInterfaces = FakeFunction(self.enumerate)
            self.WlanQueryInterface = FakeFunction(self.query)
            self.WlanFreeMemory = FakeFunction(self.free)
            self.WlanCloseHandle = FakeFunction(self.close)

        def open(self, _version, _reserved, negotiated, handle):
            ctypes.cast(negotiated, ctypes.POINTER(wifi.wintypes.DWORD))[0] = 2
            ctypes.cast(handle, ctypes.POINTER(wifi.wintypes.HANDLE))[0] = 123
            return 0

        def enumerate(self, _handle, _reserved, output):
            header = wifi._InterfaceListHeader(1, 0)
            interface = wifi._Interface()
            interface.description = "Test Wireless Adapter"
            interface.state = wifi._CONNECTED
            buffer = ctypes.create_string_buffer(ctypes.sizeof(header) + ctypes.sizeof(interface))
            ctypes.memmove(ctypes.addressof(buffer), ctypes.byref(header), ctypes.sizeof(header))
            ctypes.memmove(ctypes.addressof(buffer) + ctypes.sizeof(header),
                           ctypes.byref(interface), ctypes.sizeof(interface))
            self.buffers.append(buffer)
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(buffer)
            return 0

        def query(self, _handle, _guid, opcode, _reserved, size, output, _type):
            self.opcodes.append(opcode)
            payload = {
                wifi._CURRENT_QUALITY: struct.pack("<6I", 0, 73, 0, 0, 0, 1),
                wifi._RSSI: struct.pack("<i", -61),
                wifi._CHANNEL: struct.pack("<I", 44),
            }[opcode]
            buffer = ctypes.create_string_buffer(payload)
            self.buffers.append(buffer)
            ctypes.cast(size, ctypes.POINTER(wifi.wintypes.DWORD))[0] = len(payload)
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(buffer)
            return 0

        def free(self, pointer):
            self.freed.append(pointer.value)

        def close(self, _handle, _reserved):
            self.closed = True
            return 0

    fake = FakeApi()
    monkeypatch.setattr(wifi.sys, "platform", "win32")
    monkeypatch.setattr(wifi.ctypes, "WinDLL", lambda _name: fake, raising=False)
    assert wifi.connected_wifi() == (WifiSnapshot("Test Wireless Adapter", 73, -61, 44),)
    assert fake.opcodes == [wifi._CURRENT_QUALITY, wifi._RSSI, wifi._CHANNEL]
    assert len(fake.freed) == 4
    assert fake.closed
