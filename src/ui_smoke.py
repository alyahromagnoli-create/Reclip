"""Isolated packaged UI regression checks, called only by --smoke-test."""
import ctypes
from PyQt6.QtCore import Qt,QPoint,QPointF,QEvent
from PyQt6.QtGui import QMouseEvent,QImage,QColor
from PyQt6.QtWidgets import QDialog,QApplication

def check_interaction(window,report_path):
    app=QApplication.instance();checks={}
    def inspect(name):
        app.processEvents();d=app.activeModalWidget()
        ok=bool(d and d.isVisible() and ctypes.windll.user32.GetWindowLongW(int(d.winId()),-20)&8)
        checks[name]=ok
        if d:
            d.grab().save(str(report_path.with_name(report_path.stem+'-'+name+'.png')))
            d.reject();app.processEvents()
    window.refresh()
    for mode in ('clean','urls','emails','view'):
        window.preview(mode);inspect(mode)
    from PyQt6.QtCore import QByteArray,QBuffer,QIODevice
    image=QImage(64,48,QImage.Format.Format_ARGB32);image.fill(QColor('#235970'))
    data=QByteArray();buf=QBuffer(data);buf.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buf,'PNG')
    n=window.history.add_image(bytes(data),64,48);window.refresh();window.select_id(n)
    window.preview('view');inspect('image')
    window.clear_history();inspect('confirmation')
    window.settings_dialog();inspect('settings')
    start=window.pos();bar=window.title_bar;local=QPointF(15,15)
    glob=QPointF(bar.mapToGlobal(QPoint(15,15)))
    def send(kind,point,button,buttons):
        app.sendEvent(bar,QMouseEvent(kind,local,point,button,buttons,Qt.KeyboardModifier.NoModifier))
    send(QEvent.Type.MouseButtonPress,glob,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
    for name,dx,dy in [('right_down',60,25),('left_up',-50,-20)]:
        send(QEvent.Type.MouseMove,glob+QPointF(dx,dy),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton)
        checks['drag_'+name]=window.pos()==start+QPoint(dx,dy)
    send(QEvent.Type.MouseButtonRelease,glob,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)
    window.move(start);checks['main_enabled_after_dialogs']=window.isEnabled()
    return checks
