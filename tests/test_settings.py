"""Settings regression checks; isolated paused DB, no system clipboard writes/hotkeys."""
import ctypes
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QApplication,QDialog,QKeySequenceEdit,QPushButton
from app import ReclipWindow
from history import History

@pytest.fixture(scope='module')
def qt():
    app=QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app

@pytest.fixture
def win(qt,tmp_path):
    path=tmp_path/'paused.db'
    h=History(path);h.setting('paused','1');h.add_text('synthetic preserved history');h.close()
    w=ReclipWindow(path,register_hotkey=False)
    yield w
    for d in w.findChildren(QDialog):d.reject()
    w.shutdown();qt.processEvents()

def settings(w):
    return next((d for d in w.findChildren(QDialog) if d.windowTitle()=='Reclip 设置' and d.isVisible()),None)

@pytest.mark.parametrize('parent_visible',[True,False])
def test_settings_returns_immediately_and_is_above_topmost_parent(win,qt,parent_visible):
    if parent_visible:win.show()
    qt.processEvents()
    delayed=[]
    def rescue_blocking_old_dialog():
        d=settings(win)
        if d:delayed.append(True);d.reject()
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(rescue_blocking_old_dialog);timer.start(250)
    try:win.settings_button.click()
    finally:timer.stop()
    assert not delayed,'Settings used a nested blocking modal loop'
    d=settings(win)
    assert d is not None
    assert d.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert ctypes.windll.user32.GetWindowLongW(int(d.winId()),-20)&8,'Settings HWND must be topmost'
    assert QApplication.activeModalWidget() is d
    d.reject();qt.processEvents()

def test_repeated_open_cancel_then_save_preserves_records(win,qt,monkeypatch):
    win.settings_dialog();first=settings(win)
    win.settings_dialog()
    assert settings(win) is first
    first.findChild(QKeySequenceEdit).setKeySequence(QKeySequence('Ctrl+Alt+V'))
    first.reject();qt.processEvents()
    assert win.hotkey_text=='Alt+V'
    assert win.history.setting('hotkey') is None
    calls=[]
    monkeypatch.setattr(win.hk,'register',lambda combo:calls.append(combo) or True)
    win.settings_dialog();d=settings(win)
    d.findChild(QKeySequenceEdit).setKeySequence(QKeySequence('Ctrl+Alt+V'))
    next(b for b in d.findChildren(QPushButton) if b.text()=='保存').click()
    qt.processEvents()
    assert calls==['Ctrl+Alt+V']
    assert win.history.setting('hotkey')=='Ctrl+Alt+V'
    assert win.hotkey_badge.text()=='Ctrl+Alt+V'
    assert win.history.items()[0]['text']=='synthetic preserved history'
    win.settings_dialog();assert settings(win) is not None

