import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PyQt6.QtWidgets import QApplication,QTextEdit
from PyQt6.QtCore import QMimeData,Qt
from PyQt6.QtGui import QImage,QColor
from PyQt6.QtTest import QTest
from app import ReclipWindow
from windows_api import restore_foreground,foreground

@pytest.fixture(scope='module')
def qt():return QApplication.instance() or QApplication([])

@pytest.fixture
def win(qt,tmp_path):
    original=QMimeData();mime=qt.clipboard().mimeData()
    if mime:
        for f in mime.formats():original.setData(f,mime.data(f))
    w=ReclipWindow(tmp_path/'history.db',register_hotkey=False);w.show();qt.processEvents()
    yield w
    w.shutdown();qt.clipboard().setMimeData(original);qt.processEvents()

def test_capture_pause_and_internal_copy(win,qt):
    qt.clipboard().setText('Reclip synthetic test text');qt.processEvents()
    assert len(win.history.items())==1

def test_duplicate_native_notice_does_not_count_as_new_copy(win,qt):
    qt.clipboard().setText('native notice synthetic');qt.processEvents()
    row=win.history.items()[0]
    win.capture();win.capture()
    assert win.history.get(row['id'])['copies']==1
    qt.clipboard().setText('native notice synthetic');qt.processEvents()
    assert win.history.get(row['id'])['copies']==2
    row=win.history.items()[0]
    win.copy_clip(row['id']);qt.processEvents()
    assert win.history.get(row['id'])['copies']==2
    win.toggle_pause();qt.clipboard().setText('paused synthetic');qt.processEvents()
    assert len(win.history.items())==1

def test_capture_image_and_filter(win,qt):
    image=QImage(25,20,QImage.Format.Format_ARGB32);image.fill(QColor('#2a6c7a'))
    qt.clipboard().setImage(image);qt.processEvents()
    rows=win.history.items(kind='image');assert len(rows)==1
    assert rows[0]['width']==25
    win.copy_clip(rows[0]['id']);qt.processEvents()
    assert win.history.get(rows[0]['id'])['copies']==1
    win.search.setText('missing synthetic');qt.processEvents();assert win.list.count()==0
    win.search.clear();assert win.list.count()==1

def test_processing_result_and_preview(win,qt):
    n=win.history.add_text('hello\u200b  \r\nhttps://example.com a@example.com')
    win.refresh();win.select_id(n)
    assert win.process_text('urls')=='https://example.com'
    assert win.process_text('emails')=='a@example.com'
    assert '\u200b' not in win.process_text('clean')

def test_real_text_paste_returns_to_target(win,qt):
    target=QTextEdit();target.setWindowTitle('Reclip synthetic paste target');target.show();target.setFocus();restore_foreground(int(target.winId()));qt.processEvents()
    n=win.history.add_text('Synthetic paste target 123')
    win.summon(int(target.winId()));qt.processEvents();assert win.target==int(target.winId())
    win.paste_clip(n)
    QTest.qWait(500);qt.processEvents()
    assert target.toPlainText()=='Synthetic paste target 123'
    target.close()

def test_real_image_paste(win,qt):
    # A target must support image paste. Plain QTextEdit has no image insertion
    # handler, so model a rich-text editor that explicitly accepts image MIME.
    class ImageEditor(QTextEdit):
        def canInsertFromMimeData(self,source):return source.hasImage() or super().canInsertFromMimeData(source)
        def insertFromMimeData(self,source):
            if source.hasImage():self.textCursor().insertImage(QImage(source.imageData()))
            else:super().insertFromMimeData(source)
    target=ImageEditor();target.show();target.setFocus();restore_foreground(int(target.winId()));qt.processEvents()
    image=QImage(20,15,QImage.Format.Format_ARGB32);image.fill(QColor('#c64a37'))
    qt.clipboard().setImage(image);qt.processEvents();row=win.history.items(kind='image')[0]
    win.summon(int(target.winId()));win.paste_clip(row['id']);QTest.qWait(500)
    assert '<img ' in target.toHtml()
    target.close()

def test_no_target_copies_without_sending(win,qt):
    n=win.history.add_text('copy only');win.target=0;win.paste_clip(n);qt.processEvents()
    assert qt.clipboard().text()=='copy only'
    assert '已复制' in win.status.text()

def test_escape_hides(win):
    QTest.keyClick(win,Qt.Key.Key_Escape);assert not win.isVisible()

def test_exit_button_and_ctrl_q_is_not_bound(win):
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    from PyQt6.QtTest import QSignalSpy
    spy=QSignalSpy(win.quit_requested)
    win.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Q,Qt.KeyboardModifier.ControlModifier))
    assert len(spy)==0
    assert not any(s.key().toString()=='Ctrl+Q' for s in win.findChildren(__import__('PyQt6.QtGui',fromlist=['QShortcut']).QShortcut))
    win.exit_button.click();assert len(spy)==1

def test_global_hotkey_native_message_and_conflict_rollback(win,qt):
    from PyQt6.QtWidgets import QWidget
    from windows_api import Hotkey,INPUT,KEYBDINPUT,u
    import ctypes
    target=QTextEdit();target.show();target.setFocus();restore_foreground(int(target.winId()))
    assert win.hk.register('Ctrl+Alt+F10')
    blocker=QWidget();other=Hotkey(int(blocker.winId()))
    assert other.register('Ctrl+Alt+F11')
    assert not win.hk.register('Ctrl+Alt+F11')
    assert win.hk.current=='Ctrl+Alt+F10'
    win.hide();events=(INPUT*6)()
    for event,(vk,up) in zip(events,[(0x11,False),(0x12,False),(0x79,False),(0x79,True),(0x12,True),(0x11,True)]):
        event.type=1;event.ki=KEYBDINPUT(vk,0,2 if up else 0,0,0)
    assert u.SendInput(6,events,ctypes.sizeof(INPUT))==6
    QTest.qWait(350)
    assert win.isVisible()
    assert win.target==int(target.winId())
    other.close();target.close();blocker.close()

def test_resummon_cancels_pending_paste(win,qt):
    target=QTextEdit();target.show();target.setFocus();restore_foreground(int(target.winId()))
    n=win.history.add_text('must not paste after recall')
    win.summon(int(target.winId()));win.paste_clip(n)
    win.summon(int(target.winId()));QTest.qWait(250)
    assert target.toPlainText()==''
    target.close()
