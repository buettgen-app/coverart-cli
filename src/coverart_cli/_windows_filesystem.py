# Copyright (c) 2026 WildDragonKing
# SPDX-License-Identifier: MIT

"""Windows-only implementation; imported lazily by filesystem.py.

Directory handles deny delete sharing, retaining ancestor locks for
as long as a descendant descriptor is live. CreateFileW opens reparse points
as objects so they can be rejected before any bytes are read or written.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import itertools

# This module must never be imported on a non-Windows host.
import msvcrt
import os
import struct
import sys
import threading
from contextlib import contextmanager, nullcontext, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coverart_cli.errors import UnsupportedPlatformError

_ctypes: Any = ctypes
_crt: Any = msvcrt
_system: Any = sys

_kernel = _ctypes.WinDLL("kernel32", use_last_error=True)
_CreateFile = _kernel.CreateFileW
_CreateFile.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
_CreateFile.restype = wintypes.HANDLE
_CloseHandle = _kernel.CloseHandle
_CloseHandle.argtypes = [wintypes.HANDLE]
_CloseHandle.restype = wintypes.BOOL
_GetInfo = _kernel.GetFileInformationByHandleEx
_GetInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
_GetInfo.restype = wintypes.BOOL
_SetInfo = _kernel.SetFileInformationByHandle
_SetInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
_SetInfo.restype = wintypes.BOOL
_advapi = _ctypes.WinDLL("advapi32", use_last_error=True)
_GetSecurity = _advapi.GetSecurityInfo
_GetSecurity.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD] + [ctypes.c_void_p] * 5
_GetSecurity.restype = wintypes.DWORD
_LocalFree = _kernel.LocalFree
_LocalFree.argtypes = [ctypes.c_void_p]
_LocalFree.restype = ctypes.c_void_p
_BackupRead = _kernel.BackupRead
_BackupWrite = _kernel.BackupWrite
for _backup_function in (_BackupRead, _BackupWrite):
    _backup_function.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.BOOL,
        ctypes.c_void_p,
    ]
    _backup_function.restype = wintypes.BOOL
_BackupSeek = _kernel.BackupSeek
_BackupSeek.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
_BackupSeek.restype = wintypes.BOOL


_ntdll = _ctypes.WinDLL("ntdll")
_NtCreateFile = _ntdll.NtCreateFile
_NtCreateFile.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
]
_NtCreateFile.restype = ctypes.c_long
_NtSetInfo = _ntdll.NtSetInformationFile
_NtSetInfo.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_int,
]
_NtSetInfo.restype = ctypes.c_long
_NtError = _ntdll.RtlNtStatusToDosError
_NtError.argtypes = [wintypes.DWORD]
_NtError.restype = wintypes.DWORD
_QueryDevice = _kernel.QueryDosDeviceW
_QueryDevice.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
_QueryDevice.restype = wintypes.DWORD
_FinalPath = _kernel.GetFinalPathNameByHandleW
_FinalPath.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
_FinalPath.restype = wintypes.DWORD
_GetProcess = _kernel.GetCurrentProcess
_GetProcess.restype = wintypes.HANDLE
_GetThread = _kernel.GetCurrentThread
_GetThread.restype = wintypes.HANDLE
_DuplicateHandle = _kernel.DuplicateHandle
_DuplicateHandle.argtypes = [
    wintypes.HANDLE,
    wintypes.HANDLE,
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
]
_DuplicateHandle.restype = wintypes.BOOL
_ReOpenFile = _kernel.ReOpenFile
_ReOpenFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
_ReOpenFile.restype = wintypes.HANDLE
_OpenThreadToken = _advapi.OpenThreadToken
_OpenThreadToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, ctypes.c_void_p]
_OpenThreadToken.restype = wintypes.BOOL
_OpenProcessToken = _advapi.OpenProcessToken
_OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p]
_OpenProcessToken.restype = wintypes.BOOL
_DuplicateToken = _advapi.DuplicateTokenEx
_DuplicateToken.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_void_p,
]
_DuplicateToken.restype = wintypes.BOOL
_SetThreadToken = _advapi.SetThreadToken
_SetThreadToken.argtypes = [ctypes.c_void_p, wintypes.HANDLE]
_SetThreadToken.restype = wintypes.BOOL
_LookupPrivilege = _advapi.LookupPrivilegeValueW
_LookupPrivilege.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]
_LookupPrivilege.restype = wintypes.BOOL
_AdjustPrivileges = _advapi.AdjustTokenPrivileges
_AdjustPrivileges.argtypes = [
    wintypes.HANDLE,
    wintypes.BOOL,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
_AdjustPrivileges.restype = wintypes.BOOL

_GetTokenInfo = _advapi.GetTokenInformation
_GetTokenInfo.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
]
_GetTokenInfo.restype = wintypes.BOOL
_GetAce = _advapi.GetAce
_GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
_GetAce.restype = wintypes.BOOL


class _UnicodeString(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.USHORT),
        ("maximum", wintypes.USHORT),
        ("buffer", ctypes.c_void_p),
    ]


class _ObjectAttributes(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.ULONG),
        ("root", wintypes.HANDLE),
        ("name", ctypes.c_void_p),
        ("attributes", wintypes.ULONG),
        ("security", ctypes.c_void_p),
        ("quality", ctypes.c_void_p),
    ]


class _IoStatus(ctypes.Structure):
    _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]


class _Luid(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.LONG)]


class _Privilege(ctypes.Structure):
    _fields_ = [("count", wintypes.DWORD), ("luid", _Luid), ("attributes", wintypes.DWORD)]


def _nt_error(status: int) -> OSError:
    return _ctypes.WinError(_NtError(status & 0xFFFFFFFF))


def _relative_create(
    name: str,
    parent: int,
    access: int,
    share: int,
    creation: int,
    directory: bool | None,
    descriptor,
    attributes: int,
) -> int:
    encoded = name.encode("utf-16-le", errors="surrogatepass")
    text = ctypes.create_string_buffer(encoded + b"\0\0")
    unicode = _UnicodeString(len(encoded), len(encoded) + 2, ctypes.addressof(text))
    matching = 0x40  # Ordinary Windows directories use case-insensitive lookup.
    if _system.getwindowsversion().build >= 17134:
        sensitivity = wintypes.DWORD()
        if not _GetInfo(parent, 23, ctypes.byref(sensitivity), ctypes.sizeof(sensitivity)):
            raise _ctypes.WinError(_ctypes.get_last_error())
        if sensitivity.value & 1:
            matching = 0
    objects = _ObjectAttributes(
        ctypes.sizeof(_ObjectAttributes),
        parent,
        ctypes.addressof(unicode),
        matching,
        descriptor,
        None,
    )
    result = wintypes.HANDLE()
    status = _IoStatus()
    options = 0x00200000 | 0x20 | (0 if directory is None else (1 if directory else 0x40))
    code = _NtCreateFile(
        ctypes.byref(result),
        access | 0x100000,
        ctypes.byref(objects),
        ctypes.byref(status),
        None,
        attributes,
        share,
        2 if creation == 1 else 1,
        options,
        None,
        0,
    )
    if code < 0:
        raise _nt_error(code)
    if result.value is None:
        raise OSError("native open returned no handle")
    return result.value


def _final_nt_path(handle: int) -> str:
    buffer = ctypes.create_unicode_buffer(32768)
    size = _FinalPath(handle, buffer, len(buffer), 2)  # VOLUME_NAME_NT, normalized.
    if not size or size >= len(buffer):
        raise _ctypes.WinError(_ctypes.get_last_error())
    return buffer.value


@contextmanager
def security_policy_access():
    """Temporarily enable an already-assigned privilege on a private thread token."""
    previous = wintypes.HANDLE()
    process = wintypes.HANDLE()
    private = wintypes.HANDLE()
    installed = False
    try:
        if not _OpenThreadToken(_GetThread(), 0xE, True, ctypes.byref(previous)):
            if _ctypes.get_last_error() != 1008:  # ERROR_NO_TOKEN
                raise _ctypes.WinError(_ctypes.get_last_error())
            if not _OpenProcessToken(_GetProcess(), 0xA, ctypes.byref(process)):
                raise _ctypes.WinError(_ctypes.get_last_error())
        base = previous if previous else process
        if not _DuplicateToken(base, 0x2C, None, 2, 2, ctypes.byref(private)):
            raise _ctypes.WinError(_ctypes.get_last_error())
        privilege = _Privilege()
        privilege.count = 1
        privilege.attributes = 2
        if not _LookupPrivilege(None, "SeSecurityPrivilege", ctypes.byref(privilege.luid)):
            raise _ctypes.WinError(_ctypes.get_last_error())
        _ctypes.set_last_error(0)
        if not _AdjustPrivileges(private, False, ctypes.byref(privilege), 0, None, None):
            raise _ctypes.WinError(_ctypes.get_last_error())
        if _ctypes.get_last_error():
            raise PermissionError("cannot retain SACL policy: SeSecurityPrivilege is unavailable")
        if not _SetThreadToken(None, private):
            raise _ctypes.WinError(_ctypes.get_last_error())
        installed = True
        yield
    finally:
        try:
            if installed:
                # Disable private-token privileges even if restoring the prior token fails.
                _AdjustPrivileges(private, True, None, 0, None, None)
                if not _SetThreadToken(None, previous):
                    raise _ctypes.WinError(_ctypes.get_last_error())
        finally:
            for token in (private, process, previous):
                if token:
                    _CloseHandle(token)


@contextmanager
def security_descriptor(fd: int):
    descriptor = ctypes.c_void_p()
    policy = _INVALID_HANDLE
    with security_policy_access():
        try:
            policy = _ReOpenFile(_crt.get_osfhandle(fd), 0x01020080, 7, 0)
            if policy == _INVALID_HANDLE:
                raise _ctypes.WinError(_ctypes.get_last_error())
            result = _GetSecurity(
                policy, 1, 0x1FF, None, None, None, None, ctypes.byref(descriptor)
            )  # Owner, group, DACL and all applicable SACL information.
            if result:
                raise _ctypes.WinError(result)
            yield descriptor
        finally:
            if descriptor:
                _LocalFree(descriptor)
            if policy != _INVALID_HANDLE:
                _CloseHandle(policy)


_GetOwner = _advapi.GetSecurityDescriptorOwner
_GetGroup = _advapi.GetSecurityDescriptorGroup
for _getter in (_GetOwner, _GetGroup):
    _getter.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    _getter.restype = wintypes.BOOL
_GetDacl = _advapi.GetSecurityDescriptorDacl
_GetSacl = _advapi.GetSecurityDescriptorSacl
for _getter in (_GetDacl, _GetSacl):
    _getter.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    _getter.restype = wintypes.BOOL
_EqualSid = _advapi.EqualSid
_EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_EqualSid.restype = wintypes.BOOL
_GetSecurityControl = _advapi.GetSecurityDescriptorControl
_GetSecurityControl.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
_GetSecurityControl.restype = wintypes.BOOL


def _same_security_policy(left, right) -> bool:
    for getter in (_GetOwner, _GetGroup):
        a, b = ctypes.c_void_p(), ctypes.c_void_p()
        defaulted = wintypes.BOOL()
        for descriptor, result in ((left, a), (right, b)):
            if not getter(descriptor, ctypes.byref(result), ctypes.byref(defaulted)):
                raise _ctypes.WinError(_ctypes.get_last_error())
        if bool(a) != bool(b) or (a and not _EqualSid(a, b)):
            return False
    controls = []
    for descriptor in (left, right):
        control, revision = wintypes.WORD(), wintypes.DWORD()
        if not _GetSecurityControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise _ctypes.WinError(_ctypes.get_last_error())
        controls.append(control.value & 0x3000)  # DACL/SACL inheritance protection.
    if controls[0] != controls[1]:
        return False
    for getter in (_GetDacl, _GetSacl):
        values = []
        for descriptor in (left, right):
            present, defaulted, acl = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p()
            if not getter(
                descriptor, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)
            ):
                raise _ctypes.WinError(_ctypes.get_last_error())
            raw = None
            if acl.value is not None:
                size = ctypes.c_ushort.from_address(acl.value + 2).value
                raw = ctypes.string_at(acl, size)
            values.append((bool(present.value), raw))
        if values[0] != values[1]:
            return False
    return True


def _verify_created_security(expected, handle: int) -> None:
    policy = _ReOpenFile(handle, 0x01020080, 7, 0)
    if policy == _INVALID_HANDLE:
        raise _ctypes.WinError(_ctypes.get_last_error())
    actual = ctypes.c_void_p()
    try:
        code = _GetSecurity(policy, 1, 0x1FF, None, None, None, None, ctypes.byref(actual))
        if code:
            raise _ctypes.WinError(code)
        if not _same_security_policy(expected, actual):
            raise PermissionError("complete source security policy could not be retained")
    finally:
        if actual:
            _LocalFree(actual)
        _CloseHandle(policy)


@contextmanager
def _effective_user_sid():
    token = wintypes.HANDLE()
    try:
        if not _OpenThreadToken(_GetThread(), 8, True, ctypes.byref(token)):
            if _ctypes.get_last_error() != 1008:
                raise _ctypes.WinError(_ctypes.get_last_error())
            if not _OpenProcessToken(_GetProcess(), 8, ctypes.byref(token)):
                raise _ctypes.WinError(_ctypes.get_last_error())
        needed = wintypes.DWORD()
        _GetTokenInfo(token, 1, None, 0, ctypes.byref(needed))
        if not 8 <= needed.value <= 4096:
            raise OSError("invalid token-user information size")
        data = ctypes.create_string_buffer(needed.value)
        if not _GetTokenInfo(token, 1, data, len(data), ctypes.byref(needed)):
            raise _ctypes.WinError(_ctypes.get_last_error())
        sid = ctypes.c_void_p.from_buffer(data).value
        if sid is None:
            raise OSError("token-user SID is missing")
        yield sid
    finally:
        if token:
            _CloseHandle(token)


def _assert_trusted_write_directory(parent: int) -> None:
    """Reject namespace writers outside the operator and host-admin boundary."""
    policy = _relative_create("", parent, 0x20080, 3, 3, True, None, 0)
    descriptor = ctypes.c_void_p()
    try:
        result = _GetSecurity(policy, 1, 5, None, None, None, None, ctypes.byref(descriptor))
        if result:
            raise _ctypes.WinError(result)
        # The kernel/system and host administrators are already privileged
        # actors. Other users must not control a write directory's namespace.
        system = ctypes.create_string_buffer(struct.pack("<BB6sI", 1, 1, b"\0" * 5 + b"\5", 18))
        admins = ctypes.create_string_buffer(
            struct.pack("<BB6sII", 1, 2, b"\0" * 5 + b"\5", 32, 544)
        )
        owner_rights = ctypes.create_string_buffer(
            struct.pack("<BB6sI", 1, 1, b"\0" * 5 + b"\3", 4)
        )
        with _effective_user_sid() as user:

            def trusted(sid):
                return bool(sid) and any(
                    _EqualSid(sid, principal) for principal in (user, system, admins)
                )

            owner = ctypes.c_void_p()
            defaulted = wintypes.BOOL()
            if not _GetOwner(descriptor, ctypes.byref(owner), ctypes.byref(defaulted)):
                raise _ctypes.WinError(_ctypes.get_last_error())
            if not trusted(owner):
                raise PermissionError("Windows write directory has an untrusted owner")
            present = wintypes.BOOL()
            acl = ctypes.c_void_p()
            if not _GetDacl(
                descriptor, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)
            ):
                raise _ctypes.WinError(_ctypes.get_last_error())
            if not present.value or acl.value is None:
                raise PermissionError("Windows write directory has an unrestricted DACL")
            count = ctypes.c_ushort.from_address(acl.value + 4).value
            unsafe = 0x2 | 0x4 | 0x10 | 0x40 | 0x100 | 0x10000 | 0x40000 | 0x80000 | 0x50000000
            for index in range(count):
                ace = ctypes.c_void_p()
                if not _GetAce(acl, index, ctypes.byref(ace)) or ace.value is None:
                    raise _ctypes.WinError(_ctypes.get_last_error())
                header = ctypes.string_at(ace, 8)
                kind, flags, _size, mask = struct.unpack("<BBHI", header)
                if flags & 8 or kind in {1, 6, 10, 12}:  # Inherit-only / deny ACEs.
                    continue
                # OWNER RIGHTS (S-1-3-4) resolves to the already-validated owner.
                # Python 3.13+ uses it for private (0o700) Windows directories.
                allowed = trusted(ace.value + 8) if kind == 0 else False
                if kind == 0 and _EqualSid(ace.value + 8, owner_rights):
                    allowed = True
                if mask & unsafe and not allowed:
                    raise PermissionError("Windows write directory permits untrusted writers")
    finally:
        if descriptor:
            _LocalFree(descriptor)
        _CloseHandle(policy)


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.DWORD),
        ("descriptor", ctypes.c_void_p),
        ("inherit", wintypes.BOOL),
    ]


class _RenameInfo(ctypes.Structure):
    _fields_ = [
        ("replace", wintypes.DWORD),
        ("root", wintypes.HANDLE),
        ("length", wintypes.DWORD),
        ("name", wintypes.WCHAR * 1),
    ]


_DeviceControl = _kernel.DeviceIoControl
_DeviceControl.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
_DeviceControl.restype = wintypes.BOOL


class _BasicInfo(ctypes.Structure):
    _fields_ = [
        ("creation", ctypes.c_longlong),
        ("access", ctypes.c_longlong),
        ("write", ctypes.c_longlong),
        ("change", ctypes.c_longlong),
        ("attributes", wintypes.DWORD),
    ]


_MUTABLE_ATTRIBUTES = 0x2 | 0x4 | 0x20 | 0x100 | 0x1000 | 0x2000
_SUPPORTED_ATTRIBUTES = _MUTABLE_ATTRIBUTES | 0x80 | 0x800


def _attributes(handle: int) -> int:
    info = _AttributeTag()
    if not _GetInfo(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
        raise _ctypes.WinError(_ctypes.get_last_error())
    return info.attributes


def preserve_attributes(source_fd: int, target_fd: int) -> None:
    expected = _attributes(_crt.get_osfhandle(source_fd))
    info = _BasicInfo()
    info.attributes = expected & _MUTABLE_ATTRIBUTES or 0x80
    target = _crt.get_osfhandle(target_fd)
    if not _SetInfo(target, 0, ctypes.byref(info), ctypes.sizeof(info)):
        raise _ctypes.WinError(_ctypes.get_last_error())
    # Compression is controlled by FSCTL, not by FILE_BASIC_INFO.
    if _attributes(target) & _SUPPORTED_ATTRIBUTES != expected & _SUPPORTED_ATTRIBUTES:
        raise OSError("source file attributes could not be retained")


_GetFileTime = _kernel.GetFileTime
_GetFileTime.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
_GetFileTime.restype = wintypes.BOOL
_SetFileTime = _kernel.SetFileTime
_SetFileTime.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
_SetFileTime.restype = wintypes.BOOL
_GetVolume = _kernel.GetVolumeInformationW
_GetVolume.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.LPWSTR,
    wintypes.DWORD,
]
_GetVolume.restype = wintypes.BOOL
_GetDriveType = _kernel.GetDriveTypeW
_GetDriveType.argtypes = [wintypes.LPCWSTR]
_GetDriveType.restype = wintypes.UINT
_INVALID_HANDLE = ctypes.c_void_p(-1).value


class _AttributeTag(ctypes.Structure):
    _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]


@dataclass
class _Directory:
    path: Path
    handle: int
    parent: _Directory | None
    refs: int = 1


_lock = threading.RLock()
_ids = itertools.count(1 << 30)
_directories: dict[int, _Directory] = {}


def _error(path: Path) -> OSError:
    error = _ctypes.WinError(_ctypes.get_last_error())
    error.filename = str(path)
    return error


def _native(
    path: Path,
    *,
    directory: bool,
    flags: int = 0,
    share_delete: bool = False,
    enumerate_directory: bool = True,
    security_source_fd: int | None = None,
    parent_handle: int | None = None,
) -> int:
    # Ancestors need traverse and metadata access, not enumeration permission.
    access = (0xA0 | (0x01 if enumerate_directory else 0)) if directory else 0x80000000
    if not directory and flags & (os.O_WRONLY | os.O_RDWR):
        access = 0x40000000 | (0x80000000 if flags & os.O_RDWR else 0)
    access |= 0x80  # NtCreateFile does not implicitly grant FILE_READ_ATTRIBUTES.
    if flags & os.O_CREAT:
        if parent_handle is None:
            raise OSError("Windows creation requires a pinned parent")
        _assert_trusted_write_directory(parent_handle)
        access |= 0x10000  # DELETE is required for a handle-bound rename.
    creation = 1 if flags & os.O_CREAT and flags & os.O_EXCL else 3
    if flags & os.O_CREAT and not flags & os.O_EXCL:
        raise OSError("only exclusive file creation is supported")
    source_attributes = 0
    if security_source_fd is not None:
        source_attributes = _attributes(_crt.get_osfhandle(security_source_fd))
        if source_attributes & 1:
            raise PermissionError("read-only audio files cannot be replaced", str(path))
        if source_attributes & ~_SUPPORTED_ATTRIBUTES:
            raise UnsupportedPlatformError("source file attributes cannot be retained", str(path))
    security = (
        security_descriptor(security_source_fd)
        if security_source_fd is not None
        else nullcontext(None)
    )
    handle = _INVALID_HANDLE
    try:
        with security as descriptor:
            share = 3 if directory else (5 if share_delete else 1)
            file_attributes = source_attributes & _MUTABLE_ATTRIBUTES
            if parent_handle is not None:
                handle = _relative_create(
                    path.name,
                    parent_handle,
                    access,
                    share,
                    creation,
                    directory,
                    descriptor,
                    file_attributes,
                )
            else:
                attributes = (
                    _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
                    if descriptor is not None
                    else None
                )
                handle = _CreateFile(
                    str(path),
                    access,
                    share,
                    ctypes.byref(attributes) if attributes is not None else None,
                    creation,
                    0x00200000 | (0x02000000 if directory else 0) | file_attributes,
                    None,
                )
                if handle == _INVALID_HANDLE:
                    raise _error(path)
            if descriptor is not None:
                _verify_created_security(descriptor, handle)
        if source_attributes & 0x800:
            compression = wintypes.WORD(1)  # COMPRESSION_FORMAT_DEFAULT
            returned = wintypes.DWORD()
            if not _DeviceControl(
                handle,
                0x9C040,
                ctypes.byref(compression),
                ctypes.sizeof(compression),
                None,
                0,
                ctypes.byref(returned),
                None,
            ):
                raise _error(path)
        info = _AttributeTag()
        if not _GetInfo(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise _error(path)
        if info.attributes & 0x400:
            error_type = UnsupportedPlatformError if directory else OSError
            raise error_type("reparse points are not supported", str(path))
        if not directory and info.attributes & 0x4000:
            raise UnsupportedPlatformError("EFS-encrypted files are unsupported", str(path))
        if bool(info.attributes & 0x10) != directory:
            raise OSError("unexpected filesystem object type", str(path))
        if not directory and flags & (os.O_WRONLY | os.O_RDWR):
            # Disable automatic last-access/write updates on this handle; restore
            # the source timestamps after the last write/flush, before closing.
            unchanged = ctypes.c_ulonglong(0xFFFFFFFFFFFFFFFF)
            if not _SetFileTime(handle, None, ctypes.byref(unchanged), ctypes.byref(unchanged)):
                raise _error(path)
        return handle
    except BaseException:
        if handle != _INVALID_HANDLE:
            _CloseHandle(handle)
        raise


def _release(directory: _Directory) -> None:
    directory.refs -= 1
    if not directory.refs:
        _CloseHandle(directory.handle)
        if directory.parent is not None:
            _release(directory.parent)


def _absolute(path) -> Path:
    result = Path(os.path.abspath(path))
    # Keep the supported boundary to ordinary local-drive paths. Device paths,
    # alternate streams and UNC volumes have different sharing/identity rules.
    if len(result.drive) != 2 or result.drive[1] != ":" or ":" in str(result)[2:]:
        raise UnsupportedPlatformError("Windows libraries require a local drive path", str(result))
    return result


def _child(path, dir_fd: int) -> Path:
    name = str(path)
    if not name or name in {".", ".."} or any(c in name for c in "\\/:"):
        raise OSError("invalid directory-relative name")
    return _directories[dir_fd].path / name


def validate_root(path) -> str:
    if _system.getwindowsversion().build < 16299:
        raise UnsupportedPlatformError(
            "native processing requires Windows 10 version 1709 or newer"
        )
    absolute = _absolute(path)
    root = Path(absolute.anchor)
    target = ctypes.create_unicode_buffer(4096)
    if not _QueryDevice(absolute.drive, target, len(target)):
        raise _error(root)
    device = target.value
    prefix = "\\Device\\HarddiskVolume"
    if not device.startswith(prefix) or not device[len(prefix) :].isdigit():
        raise UnsupportedPlatformError("substituted drive mappings are unsupported", str(root))
    if _GetDriveType(str(root)) not in {2, 3, 6}:
        raise UnsupportedPlatformError("Windows libraries require a local drive", str(root))
    filesystem = ctypes.create_unicode_buffer(32)
    if not _GetVolume(str(root), None, 0, None, None, None, filesystem, len(filesystem)):
        raise _error(root)
    if filesystem.value != "NTFS":
        raise UnsupportedPlatformError("Windows libraries require a local NTFS volume", str(root))
    return device


def _pin(path: Path, *, enumerate_directory: bool = True) -> _Directory:
    root_device = validate_root(path) if path == path.parent else None
    parent = None if root_device is not None else _pin(path.parent, enumerate_directory=False)
    handle = _INVALID_HANDLE
    try:
        actual = path if parent is None else parent.path / path.name
        handle = _native(
            actual,
            directory=True,
            enumerate_directory=enumerate_directory,
            parent_handle=parent.handle if parent is not None else None,
        )
        canonical = _final_nt_path(handle)
        if root_device is not None and canonical.rstrip("\\").casefold() != root_device.casefold():
            raise UnsupportedPlatformError("drive mapping changed while opening the library")
        return _Directory(Path("\\\\?\\GLOBALROOT" + canonical), handle, parent)
    except BaseException:
        if handle != _INVALID_HANDLE:
            _CloseHandle(handle)
        if parent is not None:
            _release(parent)
        raise


def open(
    path,
    flags: int,
    mode: int,
    *,
    dir_fd: int | None,
    directory: bool,
    share_delete: bool = False,
    security_source_fd: int | None = None,
) -> int:
    del mode  # Audio staging files receive the source DACL at creation.
    with _lock:
        absolute = _child(path, dir_fd) if dir_fd is not None else _absolute(path)
        if directory:
            if dir_fd is None:
                anchor = _pin(absolute)
            else:
                parent = _directories[dir_fd]
                handle = _native(absolute, directory=True, parent_handle=parent.handle)
                try:
                    canonical = Path("\\\\?\\GLOBALROOT" + _final_nt_path(handle))
                except BaseException:
                    _CloseHandle(handle)
                    raise
                parent.refs += 1
                anchor = _Directory(canonical, handle, parent)
            fd = next(_ids)
            _directories[fd] = anchor
            return fd
        parent = (
            _directories[dir_fd]
            if dir_fd is not None
            else _pin(absolute.parent, enumerate_directory=False)
        )
        try:
            absolute = parent.path / absolute.name
            handle = _native(
                absolute,
                directory=False,
                flags=flags,
                share_delete=share_delete,
                security_source_fd=security_source_fd,
                parent_handle=parent.handle,
            )
            try:
                return _crt.open_osfhandle(
                    handle, (flags & (os.O_WRONLY | os.O_RDWR)) | getattr(os, "O_BINARY", 0)
                )
            except BaseException:
                _CloseHandle(handle)
                raise
        finally:
            if dir_fd is None:
                _release(parent)


def dup(fd: int) -> int:
    with _lock:
        directory = _directories.get(fd)
        if directory is None:
            return os.dup(fd)
        new_fd = next(_ids)
        directory.refs += 1
        _directories[new_fd] = directory
        return new_fd


def close(fd: int) -> None:
    with _lock:
        directory = _directories.pop(fd, None)
        if directory is None:
            os.close(fd)
        else:
            _release(directory)


def _owned_stat(handle: int) -> os.stat_result:
    try:
        attributes = _attributes(handle)
        fd = _crt.open_osfhandle(handle, getattr(os, "O_BINARY", 0))
    except BaseException:
        _CloseHandle(handle)
        raise
    try:
        info = os.fstat(fd)
        extra = {
            "st_atime_ns": info.st_atime_ns,
            "st_mtime_ns": info.st_mtime_ns,
            "st_ctime_ns": info.st_ctime_ns,
            "st_file_attributes": attributes,
        }
        for name in ("st_birthtime", "st_birthtime_ns"):
            if hasattr(info, name):
                extra[name] = getattr(info, name)
        return os.stat_result(tuple(info), extra)
    finally:
        os.close(fd)


def _duplicate_stat(handle: int) -> os.stat_result:
    duplicate = wintypes.HANDLE()
    process = _GetProcess()
    if not _DuplicateHandle(process, handle, process, ctypes.byref(duplicate), 0, False, 2):
        raise _ctypes.WinError(_ctypes.get_last_error())
    if duplicate.value is None:
        raise OSError("native duplicate returned no handle")
    return _owned_stat(duplicate.value)


@dataclass
class _Entry:
    name: str
    parent: _Directory

    def stat(self, *, follow_symlinks: bool = False):
        del follow_symlinks  # This internal facade always inspects the entry itself.
        handle = _relative_create(self.name, self.parent.handle, 0x80, 7, 3, None, None, 0)
        return _owned_stat(handle)

    def is_dir(self, *, follow_symlinks: bool = False) -> bool:
        info = self.stat(follow_symlinks=follow_symlinks)
        return bool(getattr(info, "st_file_attributes", 0) & 0x10)

    def is_file(self, *, follow_symlinks: bool = False) -> bool:
        info = self.stat(follow_symlinks=follow_symlinks)
        return not bool(getattr(info, "st_file_attributes", 0) & 0x10)


class _Scandir:
    def __init__(self, parent: _Directory):
        self.parent = parent
        self.handle: int | None = _relative_create("", parent.handle, 0xA1, 3, 3, True, None, 0)
        if self.handle == _INVALID_HANDLE:
            raise _ctypes.WinError(_ctypes.get_last_error())
        self.restart = True
        self.entries: list[_Entry] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __iter__(self):
        return self

    def __next__(self):
        while not self.entries:
            if self.handle == _INVALID_HANDLE:
                raise StopIteration
            buffer = ctypes.create_string_buffer(65536)
            kind = 11 if self.restart else 10  # FileIdBothDirectoryRestartInfo / Info.
            self.restart = False
            if not _GetInfo(self.handle, kind, buffer, len(buffer)):
                error = _ctypes.get_last_error()
                self.close()
                if error == 18:  # ERROR_NO_MORE_FILES
                    raise StopIteration
                raise _ctypes.WinError(error)
            raw = buffer.raw
            offset = 0
            while True:
                next_offset = struct.unpack_from("<I", raw, offset)[0]
                name_size = struct.unpack_from("<I", raw, offset + 60)[0]
                if name_size % 2 or offset + 104 + name_size > len(raw):
                    self.close()
                    raise OSError("invalid directory information")
                name = raw[offset + 104 : offset + 104 + name_size].decode(
                    "utf-16-le", errors="surrogatepass"
                )
                if name not in {".", ".."}:
                    self.entries.append(_Entry(name, self.parent))
                if not next_offset:
                    break
                if next_offset < 104 + name_size or offset + next_offset + 104 > len(raw):
                    self.close()
                    raise OSError("invalid directory entry offset")
                offset += next_offset
            self.entries.reverse()
        return self.entries.pop()

    def close(self):
        if self.handle != _INVALID_HANDLE:
            _CloseHandle(self.handle)
            self.handle = _INVALID_HANDLE


def fstat(fd: int) -> os.stat_result:
    with _lock:
        directory = _directories.get(fd)
        return _duplicate_stat(directory.handle) if directory else os.fstat(fd)


def stat(path, *, dir_fd: int | None) -> os.stat_result:
    with _lock:
        if dir_fd is not None:
            absolute = _child(path, dir_fd)
            return _Entry(absolute.name, _directories[dir_fd]).stat()
        absolute = _absolute(path)
        parent = _pin(absolute.parent, enumerate_directory=False)
        try:
            if absolute == absolute.parent:
                return _duplicate_stat(parent.handle)
            return _Entry(absolute.name, parent).stat()
        finally:
            _release(parent)


def scandir(fd: int):
    with _lock:
        return _Scandir(_directories[fd])


def copy_streams(source_fd: int, target_fd: int) -> None:
    """Copy named streams and EAs through the verified source handle."""
    source = _crt.get_osfhandle(source_fd)
    target = _crt.get_osfhandle(target_fd)
    read_context = ctypes.c_void_p()
    write_context = ctypes.c_void_p()

    def transfer(function, handle, context, data, *, read=False):
        buffer = ctypes.create_string_buffer(data if not read else data)
        count = wintypes.DWORD()
        size = data if read else len(data)
        if not function(
            handle, buffer, size, ctypes.byref(count), False, False, ctypes.byref(context)
        ):
            raise _ctypes.WinError(_ctypes.get_last_error())
        if not read and count.value != size:
            raise OSError("incomplete backup stream write")
        return buffer.raw[: count.value]

    try:
        while True:
            header = transfer(_BackupRead, source, read_context, 20, read=True)
            if not header:
                break
            if len(header) != 20:
                raise OSError("incomplete backup stream header")
            stream_id, _attributes, size, name_size = struct.unpack("<IIqI", header)
            if size < 0 or name_size > 65536 or name_size % 2:
                raise OSError("invalid backup stream header")
            name = (
                transfer(_BackupRead, source, read_context, name_size, read=True)
                if name_size
                else b""
            )
            if len(name) != name_size:
                raise OSError("incomplete backup stream name")
            if stream_id not in {1, 2, 3, 4}:
                raise UnsupportedPlatformError("source backup stream metadata cannot be retained")
            if stream_id not in {2, 4}:
                low, high = wintypes.DWORD(), wintypes.DWORD()
                if size and not _BackupSeek(
                    source,
                    size & 0xFFFFFFFF,
                    size >> 32,
                    ctypes.byref(low),
                    ctypes.byref(high),
                    ctypes.byref(read_context),
                ):
                    raise _ctypes.WinError(_ctypes.get_last_error())
                if size and low.value + (high.value << 32) != size:
                    raise OSError("incomplete backup stream seek")
                continue
            transfer(_BackupWrite, target, write_context, header + name)
            while size:
                chunk = transfer(_BackupRead, source, read_context, min(size, 65536), read=True)
                if not chunk:
                    raise OSError("incomplete named stream")
                transfer(_BackupWrite, target, write_context, chunk)
                size -= len(chunk)
    finally:
        for function, handle, context in (
            (_BackupRead, source, read_context),
            (_BackupWrite, target, write_context),
        ):
            count = wintypes.DWORD()
            function(handle, None, 0, ctypes.byref(count), True, False, ctypes.byref(context))
        os.lseek(source_fd, 0, os.SEEK_SET)
        os.lseek(target_fd, 0, os.SEEK_SET)


def reject_encrypted_destination(path, *, dir_fd: int) -> None:
    with _lock:
        try:
            info = stat(path, dir_fd=dir_fd)
        except FileNotFoundError:
            return
        if getattr(info, "st_file_attributes", 0) & 0x4000:
            raise UnsupportedPlatformError("EFS-encrypted destinations are unsupported")


def replace(src, dst, *, src_dir_fd: int, dst_dir_fd: int, source_fd: int | None) -> None:
    with _lock:
        _child(src, src_dir_fd)
        _child(dst, dst_dir_fd)
        if source_fd is None:
            raise OSError("verified staging handle is required")
        _assert_trusted_write_directory(_directories[dst_dir_fd].handle)
        destination: int | None = None
        try:
            with suppress(FileNotFoundError):
                # Deny in-place writers, including EFS conversion, through commit.
                # Namespace writers are excluded by the directory policy above;
                # delete sharing allows our own atomic entry replacement.
                # FILE_READ_DATA is required: attribute-only opens do not
                # participate in Windows data-access sharing checks.
                destination = _relative_create(
                    str(dst), _directories[dst_dir_fd].handle, 0x81, 5, 3, None, None, 0
                )
            if destination is not None and _attributes(destination) & 0x4000:
                raise UnsupportedPlatformError("EFS-encrypted destinations are unsupported")
            handle = _crt.get_osfhandle(source_fd)
            name = str(dst).encode("utf-16-le", errors="surrogatepass")
            size = ctypes.sizeof(_RenameInfo) + len(name)
            buffer = ctypes.create_string_buffer(max(size, ctypes.sizeof(_RenameInfo)))
            info = _RenameInfo.from_buffer(buffer)
            info.replace = 3  # REPLACE_IF_EXISTS | POSIX_SEMANTICS, retaining old readers.
            info.root = _directories[dst_dir_fd].handle
            info.length = len(name)
            ctypes.memmove(ctypes.addressof(buffer) + _RenameInfo.name.offset, name, len(name))
            # The original staging handle denies delete sharing and survives until commit.
            status = _IoStatus()
            code = _NtSetInfo(handle, ctypes.byref(status), buffer, size, 65)
            if code < 0:
                raise _nt_error(code)
        finally:
            if destination is not None:
                _CloseHandle(destination)


def unlink(path, *, dir_fd: int) -> None:
    with _lock:
        name = _child(path, dir_fd).name
        handle = _relative_create(name, _directories[dir_fd].handle, 0x10080, 7, 3, None, None, 0)
        try:
            disposition = wintypes.DWORD(3)  # DELETE | POSIX_SEMANTICS
            status = _IoStatus()
            code = _NtSetInfo(
                handle,
                ctypes.byref(status),
                ctypes.byref(disposition),
                ctypes.sizeof(disposition),
                64,
            )
            if code < 0:
                raise _nt_error(code)
        finally:
            _CloseHandle(handle)


def _preserve_handle_times(
    handle: int, *, ns: tuple[int, int], creation: int | None = None
) -> None:
    # FILETIME is measured in 100 ns ticks since 1601-01-01 UTC.
    access, modified = (ctypes.c_ulonglong(value // 100 + 116444736000000000) for value in ns)
    created = ctypes.c_ulonglong(creation) if creation is not None else None
    if not _SetFileTime(
        handle,
        ctypes.byref(created) if created is not None else None,
        ctypes.byref(access),
        ctypes.byref(modified),
    ):
        raise _ctypes.WinError(_ctypes.get_last_error())


def creation_time(fd: int) -> int:
    created = ctypes.c_ulonglong()
    if not _GetFileTime(_crt.get_osfhandle(fd), ctypes.byref(created), None, None):
        raise _ctypes.WinError(_ctypes.get_last_error())
    return created.value


def preserve_times(fd: int, *, ns: tuple[int, int], creation: int | None = None) -> None:
    _preserve_handle_times(_crt.get_osfhandle(fd), ns=ns, creation=creation)
