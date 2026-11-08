"""Own-widget tests with synthetic paused history; no physical keyboard/clipboard."""
import ctypes
import pytest
from test_settings import qt,win
from PyQt6.QtCore import QTimer, Qt, QPoint, QPointF, QEvent
from PyQt6.QtGui import QMouseEvent,QImage,QColor
from PyQt6.QtWidgets import QDialog,QPlainTextEdit,QMessageBox

@pytest.mark.parametrize('mode',['clean','urls','emails','view','image'])
def test_previews_are_nonblocking_topmost_and_close_cleanly(win,qt,mode):
    if mode=='image':
        from PyQt6.QtCore import QByteArray,QBuffer,QIODevice
        img=QImage(24,20,QImage.Format.Format_ARGB32);img.fill(QColor('#235970'))
        a=QByteArray();b=QBuffer(a);b.open(QIODevice.OpenModeFlag.WriteOnly);img.save(b,'PNG')
        n=win.history.add_image(bytes(a),24,20)
    else:n=win.history.add_text('Hello\u200b\r\nhttps://example.com a@example.com')
    win.refresh();win.select_id(n);win.show();qt.processEvents()
    blocked=[]
    def rescue():
        blocked.append(True)
        for d in win.findChildren(QDialog):d.reject()
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(rescue);timer.start(250)
    try:win.preview('view' if mode=='image' else mode)
    finally:timer.stop()
    assert not blocked,'Preview traps input in a nested modal loop'
    d=qt.activeModalWidget();assert d is not None
    assert ctypes.windll.user32.GetWindowLongW(int(d.winId()),-20)&8
    if mode=='clean':assert '\u200b' not in d.findChild(QPlainTextEdit).toPlainText()
    d.reject();qt.processEvents();assert win.isEnabled()

def test_titlebar_drag_moves_left_right_and_up_down(win,qt):
    win.show();qt.processEvents();start=win.pos()
    bar=win.title_bar
    local=QPointF(15,15);global_pos=QPointF(bar.mapToGlobal(QPoint(15,15)))
    def send(kind,point,button,buttons):
        QApplication=__import__('PyQt6.QtWidgets',fromlist=['QApplication']).QApplication
        QApplication.sendEvent(bar,QMouseEvent(kind,local,point,button,buttons,Qt.KeyboardModifier.NoModifier))
    send(QEvent.Type.MouseButtonPress,global_pos,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
    send(QEvent.Type.MouseMove,global_pos+QPointF(70,30),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton)
    assert win.pos()==start+QPoint(70,30)
    send(QEvent.Type.MouseMove,global_pos+QPointF(-45,-20),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton)
    assert win.pos()==start+QPoint(-45,-20)
    send(QEvent.Type.MouseButtonRelease,global_pos,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)

def test_confirmation_topmost_cancel_does_not_clear(win,qt):
    timer=QTimer();timer.setSingleShot(True)
    timer.timeout.connect(lambda: [d.reject() for d in win.findChildren(QMessageBox)])
    timer.start(250)
    try:win.clear_history()
    finally:timer.stop()
    d=qt.activeModalWidget();assert isinstance(d,QMessageBox)
    assert ctypes.windll.user32.GetWindowLongW(int(d.winId()),-20)&8
    d.reject();qt.processEvents();assert win.history.items()

def test_preview_actions_use_edited_result_and_close_before_paste(win,qt,monkeypatch):
    from PyQt6.QtWidgets import QPushButton
    copied=[];pasted=[]
    monkeypatch.setattr(win,'copy_text',copied.append)
    monkeypatch.setattr(win,'perform_paste',lambda:pasted.append(qt.activeModalWidget()))
    for action in ('复制结果','粘贴回原窗口'):
        win.refresh();win.preview('clean');d=qt.activeModalWidget()
        d.findChild(QPlainTextEdit).setPlainText('edited synthetic result')
        next(b for b in d.findChildren(QPushButton) if b.text()==action).click();qt.processEvents()
        assert not d.isVisible() if not __import__('PyQt6.sip',fromlist=['isdeleted']).isdeleted(d) else True
    assert copied==['edited synthetic result']*2
    assert pasted==[None]

def test_nested_invalid_hotkey_warning_and_translation_cancel(win,qt,monkeypatch):
    from PyQt6.QtWidgets import QKeySequenceEdit,QPushButton
    from PyQt6.QtGui import QKeySequence,QDesktopServices
    win.settings_dialog();d=qt.activeModalWidget()
    d.findChild(QKeySequenceEdit).setKeySequence(QKeySequence('V'))
    next(b for b in d.findChildren(QPushButton) if b.text()=='保存').click();qt.processEvents()
    warning=qt.activeModalWidget();assert isinstance(warning,QMessageBox)
    assert ctypes.windll.user32.GetWindowLongW(int(warning.winId()),-20)&8
    warning.reject();qt.processEvents();assert qt.activeModalWidget() is d
    d.reject();qt.processEvents()
    calls=[];monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:calls.append(url))
    win.refresh();win.translate();box=qt.activeModalWidget()
    assert box.defaultButton()==box.button(QMessageBox.StandardButton.No)
    box.reject();qt.processEvents();assert not calls
