"""Optional verified HTTPS HEAD through the current Windows system route."""

from __future__ import annotations

import ctypes
import sys
import time
from contextlib import ExitStack


def https_head_system_route(host: str, path: str, timeout: float) -> tuple[float, int] | None:
    """Return elapsed milliseconds and HTTP status, or None if WinHTTP fails.

    WinHTTP chooses the current user's proxy route. Certificate checks remain on.
    Only a 2xx/3xx response corroborates connectivity through this route;
    proxy-generated errors must not be presented as origin responses.
    """
    if sys.platform != "win32":
        return None
    api = ctypes.WinDLL("winhttp", use_last_error=True)
    handle = ctypes.c_void_p
    dword = ctypes.c_uint32
    api.WinHttpOpen.argtypes = [ctypes.c_wchar_p, dword, ctypes.c_wchar_p,
                                ctypes.c_wchar_p, dword]
    api.WinHttpOpen.restype = handle
    api.WinHttpSetTimeouts.argtypes = [handle, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int]
    api.WinHttpSetTimeouts.restype = ctypes.c_int
    api.WinHttpConnect.argtypes = [handle, ctypes.c_wchar_p, ctypes.c_uint16, dword]
    api.WinHttpConnect.restype = handle
    api.WinHttpOpenRequest.argtypes = [handle, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                       ctypes.c_wchar_p, ctypes.c_wchar_p, handle, dword]
    api.WinHttpOpenRequest.restype = handle
    api.WinHttpSendRequest.argtypes = [handle, ctypes.c_wchar_p, dword, handle,
                                       dword, dword, ctypes.c_size_t]
    api.WinHttpSendRequest.restype = ctypes.c_int
    api.WinHttpReceiveResponse.argtypes = [handle, handle]
    api.WinHttpReceiveResponse.restype = ctypes.c_int
    api.WinHttpQueryHeaders.argtypes = [handle, dword, ctypes.c_wchar_p, handle,
                                        ctypes.POINTER(dword), ctypes.POINTER(dword)]
    api.WinHttpQueryHeaders.restype = ctypes.c_int
    api.WinHttpCloseHandle.argtypes = [handle]
    api.WinHttpCloseHandle.restype = ctypes.c_int

    started = time.perf_counter()
    timeout_ms = max(200, round(timeout * 1000))
    try:
        with ExitStack() as stack:
            session = api.WinHttpOpen("NetworkWeather/0.1", 4, None, None, 0)
            if not session:
                return None
            stack.callback(api.WinHttpCloseHandle, session)
            if not api.WinHttpSetTimeouts(session, timeout_ms, timeout_ms,
                                          timeout_ms, timeout_ms):
                return None
            connection = api.WinHttpConnect(session, host, 443, 0)
            if not connection:
                return None
            stack.callback(api.WinHttpCloseHandle, connection)
            request = api.WinHttpOpenRequest(connection, "HEAD", path, None, None,
                                              None, 0x00800000)
            if not request:
                return None
            stack.callback(api.WinHttpCloseHandle, request)
            if not api.WinHttpSendRequest(request, None, 0, None, 0, 0, 0):
                return None
            if not api.WinHttpReceiveResponse(request, None):
                return None
            status = dword()
            size = dword(ctypes.sizeof(status))
            index = dword()
            if not api.WinHttpQueryHeaders(request, 19 | 0x20000000, None,
                                            ctypes.byref(status), ctypes.byref(size),
                                            ctypes.byref(index)):
                return None
            if not 200 <= status.value < 400:
                return None
            return round((time.perf_counter() - started) * 1000, 3), status.value
    except OSError:
        return None
