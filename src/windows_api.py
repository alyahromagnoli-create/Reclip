"""Windows native hotkey and carefully targeted paste. No keyboard hook."""
import ctypes,re
from ctypes import wintypes as w

u=ctypes.WinDLL('user32',use_last_error=True);k=ctypes.WinDLL('kernel32',use_last_error=True)
u.RegisterHotKey.argtypes=[w.HWND,ctypes.c_int,w.UINT,w.UINT];u.RegisterHotKey.restype=w.BOOL
u.UnregisterHotKey.argtypes=[w.HWND,ctypes.c_int];u.UnregisterHotKey.restype=w.BOOL
u.GetForegroundWindow.restype=w.HWND;u.IsWindow.argtypes=[w.HWND];u.IsWindow.restype=w.BOOL
u.SetForegroundWindow.argtypes=[w.HWND];u.SetForegroundWindow.restype=w.BOOL
u.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)];u.GetWindowThreadProcessId.restype=w.DWORD
u.ShowWindow.argtypes=[w.HWND,ctypes.c_int];u.IsIconic.argtypes=[w.HWND];u.GetAncestor.argtypes=[w.HWND,w.UINT];u.GetAncestor.restype=w.HWND
u.RegisterClipboardFormatW.argtypes=[w.LPCWSTR];u.RegisterClipboardFormatW.restype=w.UINT
u.IsClipboardFormatAvailable.argtypes=[w.UINT];u.IsClipboardFormatAvailable.restype=w.BOOL
u.AttachThreadInput.argtypes=[w.DWORD,w.DWORD,w.BOOL];u.AttachThreadInput.restype=w.BOOL
u.BringWindowToTop.argtypes=[w.HWND]
k.GetCurrentThreadId.restype=w.DWORD;k.CreateMutexW.argtypes=[ctypes.c_void_p,w.BOOL,w.LPCWSTR];k.CreateMutexW.restype=w.HANDLE
k.CloseHandle.argtypes=[w.HANDLE]

def parse_hotkey(text):
    parts=text.replace(' ','').split('+');aliases={'ctrl':2,'control':2,'alt':1,'shift':4,'win':8,'meta':8}
    if len(parts)<2:raise ValueError('需要修饰键加字母、数字或 F1–F11，例如 Alt+V。')
    mods=0
    for part in parts[:-1]:
        flag=aliases.get(part.lower())
        if flag is None or mods&flag:raise ValueError('快捷键修饰键无效或重复。')
        mods|=flag
    last=parts[-1].upper()
    if re.fullmatch('[A-Z0-9]',last):key=ord(last)
    elif re.fullmatch(r'F(?:[1-9]|10|11)',last):key=111+int(last[1:])
    else:raise ValueError('主键请使用字母、数字或 F1–F11。')
    if mods==2 and key==ord('Q'):raise ValueError('Ctrl+Q 已保留给 QQ 录屏，请选择其他组合。')
    return mods,key

def foreground():return int(u.GetForegroundWindow() or 0)
def clipboard_sequence():return int(u.GetClipboardSequenceNumber())
def is_window(hwnd):return bool(hwnd and u.IsWindow(hwnd))
def same_root(a,b):return bool(a and b and u.GetAncestor(a,2)==u.GetAncestor(b,2))
def modifiers_down():return any(u.GetAsyncKeyState(v)&0x8000 for v in (0x10,0x11,0x12,0x5b,0x5c))

class Hotkey:
    ID=0x61a2
    def __init__(self,hwnd):self.hwnd=hwnd;self.current=None;self.active_id=self.ID
    def register(self,combo):
        mods,key=parse_hotkey(combo)
        if self.current==combo:return True
        new_id=self.ID+1 if self.active_id==self.ID else self.ID
        if not u.RegisterHotKey(self.hwnd,new_id,mods|0x4000,key):return False
        if self.current:u.UnregisterHotKey(self.hwnd,self.active_id)
        self.active_id=new_id;self.current=combo;return True
    def close(self):
        if self.current:u.UnregisterHotKey(self.hwnd,self.active_id);self.current=None

class KEYBDINPUT(ctypes.Structure):
    _fields_=[('wVk',w.WORD),('wScan',w.WORD),('dwFlags',w.DWORD),('time',w.DWORD),('dwExtraInfo',w.WPARAM)]
class MOUSEINPUT(ctypes.Structure):
    _fields_=[('dx',w.LONG),('dy',w.LONG),('mouseData',w.DWORD),('dwFlags',w.DWORD),('time',w.DWORD),('dwExtraInfo',w.WPARAM)]
class INPUTUNION(ctypes.Union):_fields_=[('ki',KEYBDINPUT),('mi',MOUSEINPUT)]
class INPUT(ctypes.Structure):_anonymous_=('data',);_fields_=[('type',w.DWORD),('data',INPUTUNION)]
u.SendInput.argtypes=[w.UINT,ctypes.POINTER(INPUT),ctypes.c_int];u.SendInput.restype=w.UINT

def send_ctrl_v(target):
    if not is_window(target) or not same_root(foreground(),target) or modifiers_down():return False
    events=(INPUT*4)()
    for event,(vk,up) in zip(events,[(0x11,False),(0x56,False),(0x56,True),(0x11,True)]):
        event.type=1;event.ki=KEYBDINPUT(vk,0,2 if up else 0,0,0)
    return u.SendInput(4,events,ctypes.sizeof(INPUT))==4

def restore_foreground(target):
    if not is_window(target):return False
    if u.IsIconic(target):u.ShowWindow(target,9)
    current=u.GetWindowThreadProcessId(foreground(),None);thread=k.GetCurrentThreadId();attached=False
    try:
        if current and thread!=current:attached=bool(u.AttachThreadInput(thread,current,True))
        u.BringWindowToTop(target);u.SetForegroundWindow(target)
    finally:
        if attached:u.AttachThreadInput(thread,current,False)
    return same_root(foreground(),target)

def excluded_from_history():
    # Respect the standard marker used by applications to suppress monitoring.
    fmt=u.RegisterClipboardFormatW('ExcludeClipboardContentFromMonitorProcessing')
    return bool(fmt and u.IsClipboardFormatAvailable(fmt))

class SingleInstance:
    def __init__(self):
        self.handle=k.CreateMutexW(None,False,'Local\\ReclipClipboardTimeMachine_v1')
        self.already_running=ctypes.get_last_error()==183
    def close(self):
        if self.handle:k.CloseHandle(self.handle);self.handle=None
