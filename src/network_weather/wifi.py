"""Read-only Native Wi-Fi signal checks that avoid location-gated BSSID APIs."""

from __future__ import annotations

import ctypes
import struct
import sys
import time
from ctypes import wintypes

from network_weather.models import WifiSnapshot

_CURRENT_QUALITY = 0x13  # wlan_intf_opcode_realtime_connection_quality
_RSSI = 0x10000102  # wlan_intf_opcode_rssi
_CHANNEL = 0x08  # wlan_intf_opcode_channel_number
_CONNECTED = 1  # wlan_interface_state_connected


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", wintypes.DWORD), ("data2", wintypes.WORD),
        ("data3", wintypes.WORD), ("data4", ctypes.c_ubyte * 8),
    ]


class _Interface(ctypes.Structure):
    _fields_ = [
        ("guid", _Guid), ("description", wintypes.WCHAR * 256),
        ("state", wintypes.DWORD),
    ]


class _InterfaceListHeader(ctypes.Structure):
    _fields_ = [("count", wintypes.DWORD), ("index", wintypes.DWORD)]


class _QualityHeader(ctypes.Structure):
    _fields_ = [
        ("phy_type", wintypes.DWORD), ("quality", wintypes.DWORD),
        ("rx_rate", wintypes.DWORD), ("tx_rate", wintypes.DWORD),
        ("is_mlo", wintypes.BOOL), ("link_count", wintypes.DWORD),
    ]


def _quality_percent(raw: bytes | None) -> int | None:
    if raw is None or len(raw) < ctypes.sizeof(_QualityHeader):
        return None
    quality = _QualityHeader.from_buffer_copy(raw).quality
    return quality if 0 <= quality <= 100 else None


def _rssi_dbm(raw: bytes | None) -> int | None:
    if raw is None or len(raw) < 4:
        return None
    value = struct.unpack_from("<i", raw)[0]
    return value if -120 <= value <= 0 else None


def _channel_number(raw: bytes | None) -> int | None:
    if raw is None or len(raw) < 4:
        return None
    value = struct.unpack_from("<I", raw)[0]
    return value if 1 <= value <= 233 else None


def _query(api: object, handle: wintypes.HANDLE, guid: _Guid, opcode: int) -> bytes | None:
    size = wintypes.DWORD()
    pointer = ctypes.c_void_p()
    status = api.WlanQueryInterface(
        handle, ctypes.byref(guid), opcode, None,
        ctypes.byref(size), ctypes.byref(pointer), None,
    )
    try:
        if status != 0 or not pointer.value or not 0 < size.value <= 65536:
            return None
        return ctypes.string_at(pointer, size.value)
    finally:
        if pointer.value:
            api.WlanFreeMemory(pointer)


def _configure_api(api: object) -> None:
    api.WlanOpenHandle.argtypes = [wintypes.DWORD, ctypes.c_void_p,
                                   ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.HANDLE)]
    api.WlanOpenHandle.restype = wintypes.DWORD
    api.WlanEnumInterfaces.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                       ctypes.POINTER(ctypes.c_void_p)]
    api.WlanEnumInterfaces.restype = wintypes.DWORD
    api.WlanQueryInterface.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Guid), wintypes.DWORD,
                                       ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                                       ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    api.WlanQueryInterface.restype = wintypes.DWORD
    api.WlanFreeMemory.argtypes = [ctypes.c_void_p]
    api.WlanFreeMemory.restype = None
    api.WlanCloseHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    api.WlanCloseHandle.restype = wintypes.DWORD


def connected_wifi() -> tuple[WifiSnapshot, ...]:
    """Return only connected radios; unsupported or unavailable fields stay None.

    The queried opcodes do not request SSID/BSSID, scan nearby networks, or ask
    for location access. A Native Wi-Fi failure is optional missing context.
    """
    if sys.platform != "win32":
        return ()
    try:
        api = ctypes.WinDLL("wlanapi.dll")
        _configure_api(api)
    except (OSError, AttributeError):
        return ()
    version = wintypes.DWORD()
    handle = wintypes.HANDLE()
    if api.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle)) != 0:
        return ()
    interfaces = ctypes.c_void_p()
    try:
        if api.WlanEnumInterfaces(handle, None, ctypes.byref(interfaces)) != 0:
            return ()
        if not interfaces.value:
            return ()
        header = _InterfaceListHeader.from_address(interfaces.value)
        if header.count > 32:
            return ()
        result = []
        for index in range(header.count):
            address = (interfaces.value + ctypes.sizeof(_InterfaceListHeader)
                       + index * ctypes.sizeof(_Interface))
            interface = _Interface.from_address(address)
            if interface.state != _CONNECTED:
                continue
            quality = _quality_percent(_query(api, handle, interface.guid, _CURRENT_QUALITY))
            rssi = _rssi_dbm(_query(api, handle, interface.guid, _RSSI))
            channel = _channel_number(_query(api, handle, interface.guid, _CHANNEL))
            result.append(WifiSnapshot(interface.description, quality, rssi, channel))
        return tuple(result)
    finally:
        if interfaces.value:
            api.WlanFreeMemory(interfaces)
        api.WlanCloseHandle(handle, None)


class WifiCache:
    def __init__(self, ttl_seconds: float = 60) -> None:
        self.ttl_seconds = ttl_seconds
        self.last_refresh = float("-inf")
        self.snapshots: tuple[WifiSnapshot, ...] = ()

    def current(self) -> tuple[WifiSnapshot, ...]:
        now = time.monotonic()
        if now - self.last_refresh >= self.ttl_seconds:
            try:
                self.snapshots = connected_wifi()
            except (OSError, ValueError, ctypes.ArgumentError):
                # Optional local context must not abort a real probe round.
                self.snapshots = ()
            self.last_refresh = now
        return self.snapshots

    def invalidate(self) -> None:
        self.last_refresh = float("-inf")
