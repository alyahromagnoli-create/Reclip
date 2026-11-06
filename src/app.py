"""Reclip floating clipboard time machine, built with newly installed PyQt6."""
from pathlib import Path
from datetime import datetime
import ctypes,time,sqlite3
from ctypes import wintypes
from PyQt6.QtCore import Qt,QTimer,QBuffer,QByteArray,QIODevice,QMimeData,QSize,QPoint,QUrl,pyqtSignal
from PyQt6.QtGui import QIcon,QPixmap,QImage,QAction,QKeySequence,QDesktopServices,QShortcut
from PyQt6.QtWidgets import (QApplication,QWidget,QFrame,QLabel,QPushButton,QLineEdit,QComboBox,QListWidget,QListWidgetItem,QVBoxLayout,QHBoxLayout,QSystemTrayIcon,QMenu,QDialog,QPlainTextEdit,QDialogButtonBox,QFormLayout,QKeySequenceEdit,QMessageBox,QCheckBox)
from history import History,digest
from text_tools import clean_text,extract_urls,extract_emails,translation_url
from windows_api import Hotkey,foreground,is_window,same_root,restore_foreground,send_ctrl_v,modifiers_down,excluded_from_history,parse_hotkey,clipboard_sequence

STYLE='''
QWidget {font-family:"Microsoft YaHei UI","Segoe UI";font-size:13px;color:#24344a;}
QWidget#window {background:#f8fafb;border:1px solid #ccd7df;}
QLabel#brand {font-size:27px;font-weight:700;color:#162e43;}
QLabel#muted {color:#6b7c8c;font-size:12px;}
QLabel#status {color:#38646c;background:#e9f2f2;padding:9px;border-radius:5px;font-size:12px;}
QPushButton {background:white;border:1px solid #d0dbe3;border-radius:5px;padding:7px 11px;}
QPushButton:hover {background:#eaf2f5;border-color:#7aa8b4;}
QPushButton:pressed {background:#d4e6ec;}
QPushButton:disabled {color:#a1aeb8;background:#f3f5f6;}
QPushButton#primary {background:#235970;border:1px solid #235970;color:white;font-weight:600;}
QLineEdit,QComboBox,QPlainTextEdit,QKeySequenceEdit {background:white;border:1px solid #cbd7e1;border-radius:5px;padding:8px;selection-background-color:#32657a;}
QListWidget {background:transparent;border:0;outline:none;}
QListWidget::item {background:white;border:1px solid #e0e7ec;border-radius:7px;padding:12px;margin-bottom:7px;}
QListWidget::item:hover {background:#edf5f7;border-color:#9ebac6;}
QListWidget::item:selected {background:#e4f0f4;border-color:#7ca2b4;color:#173f53;}
QScrollBar:vertical {width:8px;background:#f1f5f7;}
QScrollBar::handle:vertical {background:#b9cbd5;border-radius:3px;min-height:24px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QMenu {background:white;border:1px solid #ccd7df;padding:5px;}
QMenu::item {padding:8px 20px;}
QMenu::item:selected {background:#e4f0f4;}
QDialog {background:#f8fafb;}
'''

def text_label(text,muted=False):
    label=QLabel(text);label.setWordWrap(True);label.setTextFormat(Qt.TextFormat.PlainText)
    if muted:label.setObjectName('muted')
    return label

def btn(text,callback,primary=False):
    b=QPushButton(text);b.clicked.connect(callback)
    if primary:b.setObjectName('primary')
    return b

def time_label(ns):
    dt=datetime.fromtimestamp(ns/1e9);delta=time.time()-ns/1e9
    if delta<60:return '刚刚'
    if delta<3600:return f'{max(1,int(delta//60))} 分钟前'
    return dt.strftime('%H:%M') if dt.date()==datetime.now().date() else dt.strftime('%m-%d %H:%M')

class ReclipWindow(QWidget):
    quit_requested=pyqtSignal()
    def __init__(self,data_path,register_hotkey=True):
        super().__init__();self.history=History(data_path);self.target=0;self.quitting=False;self.own_digest=None;self.closed=False;self.pending_paste=None;self.last_sequence=clipboard_sequence();self.own_sequence=None
        self.paused=self.history.setting('paused')=='1';self.hotkey_text=self.history.setting('hotkey') or 'Alt+V'
        self.setWindowTitle('Reclip · 回拾 · 剪贴板时间机器')
        self.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName('window');self.setStyleSheet(STYLE);self.resize(510,740);self.setMinimumSize(420,540)
        self.icon=QIcon(str(Path(__file__).resolve().parent/'resources'/'Reclip.ico'));self.setWindowIcon(self.icon)
        v=QVBoxLayout(self);v.setContentsMargins(20,18,20,16);v.setSpacing(12)
        h=QHBoxLayout();brand=text_label('Reclip');brand.setObjectName('brand');h.addWidget(brand,1);self.hotkey_badge=text_label(self.hotkey_text,True);h.addWidget(self.hotkey_badge)
        self.settings_button=btn('设置',self.settings_dialog);h.addWidget(self.settings_button);h.addWidget(btn('收起',self.hide));v.addLayout(h)
        v.addWidget(text_label('回拾 · 最近 50 次复制的时光',True))
        h=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('搜索以前复制的文字…');self.search.textChanged.connect(self.refresh);h.addWidget(self.search,1)
        self.kind=QComboBox();self.kind.addItems(['全部','文本','图片']);self.kind.currentIndexChanged.connect(self.refresh);h.addWidget(self.kind);v.addLayout(h)
        self.list=QListWidget();self.list.setIconSize(QSize(62,46));self.list.setSpacing(1);self.list.itemClicked.connect(self.clicked_item);self.list.currentItemChanged.connect(self.selection_changed);self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.list.customContextMenuRequested.connect(self.context_menu);v.addWidget(self.list,1)
        self.empty=text_label('还没有历史记录。\n启动后复制文字或图片，它们会出现在这里。',True);self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter);v.addWidget(self.empty)
        tools=QHBoxLayout();self.clean_button=btn('纯文本',lambda:self.preview('clean'));tools.addWidget(self.clean_button);self.urls_button=btn('提取网址',lambda:self.preview('urls'));tools.addWidget(self.urls_button);self.emails_button=btn('提取邮箱',lambda:self.preview('emails'));tools.addWidget(self.emails_button);self.translate_button=btn('在线翻译',self.translate);tools.addWidget(self.translate_button);v.addLayout(tools)
        self.status=text_label('');self.status.setObjectName('status');v.addWidget(self.status)
        h=QHBoxLayout();self.count=text_label('0 / 50',True);h.addWidget(self.count);h.addStretch();self.pause_button=btn('',self.toggle_pause);h.addWidget(self.pause_button);h.addWidget(btn('清空',self.clear_history));self.exit_button=btn('退出',self.request_quit);h.addWidget(self.exit_button);v.addLayout(h)
        v.addWidget(text_label('点条目粘贴 · 右键处理／删除 · Enter 粘贴 · Esc 收起',True))
        self.tray=QSystemTrayIcon(self.icon,self);self.tray.setToolTip('Reclip｜回拾 · '+self.hotkey_text)
        menu=QMenu();menu.addAction('呼出回拾',self.summon);self.pause_action=menu.addAction('暂停记录',self.toggle_pause);self.pause_action.setCheckable(True);menu.addAction('设置',self.settings_dialog);menu.addSeparator();menu.addAction('退出',self.request_quit);self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason:self.summon() if reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        if QSystemTrayIcon.isSystemTrayAvailable():self.tray.show()
        self.clipboard=QApplication.clipboard();self.clipboard.dataChanged.connect(self.capture)
        self.hk=Hotkey(int(self.winId()));self.hotkey_registered=False
        if register_hotkey:
            try:self.hotkey_registered=self.hk.register(self.hotkey_text)
            except ValueError:self.hotkey_registered=False
        self.hotkey_badge.setText(self.hotkey_text if self.hotkey_registered or not register_hotkey else '热键未注册')
        self.tray.setToolTip('Reclip｜回拾 · '+self.hotkey_text)
        self.esc=QShortcut(QKeySequence('Escape'),self);self.esc.activated.connect(self.hide)
        self.enter=QShortcut(QKeySequence('Return'),self);self.enter.activated.connect(self.paste_selected)
        self.enter2=QShortcut(QKeySequence('Enter'),self);self.enter2.activated.connect(self.paste_selected)
        self.refresh();self.update_pause()
        if register_hotkey and not self.hotkey_registered:self.status.setText('热键被占用，未注册其他组合。请在设置中自行选择。')
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and event.position().y()<75 and self.windowHandle():self.windowHandle().startSystemMove()
        else:super().mousePressEvent(event)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.hide();event.accept()
        elif event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.paste_selected();event.accept()
        else:super().keyPressEvent(event)
    def nativeEvent(self,eventType,message):
        msg=ctypes.cast(int(message),ctypes.POINTER(wintypes.MSG)).contents
        if msg.message==0x0312 and msg.wParam==self.hk.active_id:
            QTimer.singleShot(0,self.summon);return True,0
        return False,0
    def selected_id(self):
        item=self.list.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None
    def select_id(self,id):
        for n in range(self.list.count()):
            if self.list.item(n).data(Qt.ItemDataRole.UserRole)==id:self.list.setCurrentRow(n);return
    def refresh(self,*args):
        old=self.selected_id();rows=self.history.items(self.search.text(),['all','text','image'][self.kind.currentIndex()]);self.list.clear()
        for row in rows:
            when=time_label(row['copied_ns']);kind='文本' if row['kind']=='text' else f"图片 · {row['width']}×{row['height']}"
            preview=row['text'].replace('\r','').replace('\n','  ')[:88] if row['kind']=='text' else '图片剪贴板'
            item=QListWidgetItem(f'{preview}\n{kind}   ·   {when}   ·   复制 {row["copies"]} 次');item.setData(Qt.ItemDataRole.UserRole,row['id']);item.setSizeHint(QSize(0,83));item.setToolTip('点击回贴；右键查看处理选项。')
            if row['kind']=='image':
                full=self.history.get(row['id']);pix=QPixmap();pix.loadFromData(full['image'],'PNG');item.setIcon(QIcon(pix.scaled(100,72,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)))
            self.list.addItem(item)
        if old is not None:self.select_id(old)
        if self.list.currentRow()<0 and rows:self.list.setCurrentRow(0)
        self.empty.setVisible(not rows);self.empty.setText('没有找到匹配的记录。' if self.search.text() else '还没有历史记录。\n启动后复制文字或图片，它们会出现在这里。')
        self.count.setText(f'{len(self.history.items())} / 50 条');self.selection_changed()
    def selection_changed(self,*args):
        id=self.selected_id();row=self.history.get(id) if id is not None else None
        for b in (self.clean_button,self.urls_button,self.emails_button,self.translate_button):b.setEnabled(bool(row and row['kind']=='text'))
    def capture(self):
        if self.closed:return
        try:
            seq=clipboard_sequence()
            if seq and (seq==self.last_sequence or seq==self.own_sequence):return
            self.last_sequence=seq
            if self.paused or excluded_from_history():self.own_digest=None;return
            mime=self.clipboard.mimeData()
            if mime is None:return
            if mime.hasImage():
                image=self.clipboard.image()
                if image.isNull():return
                if image.width()*image.height()>40000000:raise ValueError('图片像素过大，已跳过记录。')
                arr=QByteArray();buffer=QBuffer(arr);buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                if not image.save(buffer,'PNG'):return
                data=bytes(arr);key=digest('image',data);kind='image'
            elif mime.hasText():
                data=mime.text();key=digest('text',data);kind='text'
                if not data:return
            else:return
            if self.own_digest==key:self.own_digest=None;return
            self.own_digest=None
            if kind=='image':self.history.add_image(data,image.width(),image.height())
            else:self.history.add_text(data)
            self.refresh();self.status.setText('已记录。'+('当前有筛选条件。' if self.search.text() or self.kind.currentIndex() else f' {self.hotkey_text} 呼出后点选回贴。'))
        except (ValueError,RuntimeError,sqlite3.Error,OSError) as exc:self.status.setText(str(exc))
    def copy_clip(self,id):
        row=self.history.get(id)
        if not row:return False
        if row['kind']=='image':
            image=QImage.fromData(row['image'],'PNG')
            if image.isNull():self.status.setText('这条图片无法解码。');return False
            self.own_digest=row['digest'];self.clipboard.setImage(image)
        else:
            self.own_digest=row['digest'];mime=QMimeData();mime.setText(row['text']);self.clipboard.setMimeData(mime)
        self.own_sequence=clipboard_sequence();self.last_sequence=self.own_sequence;self.own_digest=None
        return True
    def copy_text(self,text):
        self.own_digest=digest('text',text);mime=QMimeData();mime.setText(text);self.clipboard.setMimeData(mime)
        self.own_sequence=clipboard_sequence();self.last_sequence=self.own_sequence;self.own_digest=None
    def clicked_item(self,item):self.paste_clip(item.data(Qt.ItemDataRole.UserRole))
    def paste_selected(self):
        if self.selected_id() is not None:self.paste_clip(self.selected_id())
    def paste_clip(self,id):
        if self.copy_clip(id):self.perform_paste()
    def perform_paste(self):
        if not is_window(self.target) or same_root(self.target,int(self.winId())):
            self.status.setText('已复制。先在目标输入框中按热键呼出，可直接回贴。');return
        self.pending_paste=(self.target,time.monotonic());self.hide();QTimer.singleShot(80,self.finish_paste)
    def finish_paste(self):
        if self.closed or self.pending_paste is None:return
        target,started=self.pending_paste
        if modifiers_down() and time.monotonic()-started<1.5:QTimer.singleShot(30,self.finish_paste);return
        self.pending_paste=None
        if restore_foreground(target) and send_ctrl_v(target):self.status.setText('已向原窗口发送粘贴。')
        else:
            self.status.setText('已复制；目标未能接收自动粘贴，请手动按 Ctrl+V。')
            self.tray.showMessage('Reclip','已复制，请在目标窗口手动按 Ctrl+V。',QSystemTrayIcon.MessageIcon.Information,2500)
    def summon(self,target=None):
        if QApplication.activeModalWidget() is not None:return
        self.pending_paste=None
        origin=int(target) if target is not None else foreground()
        if target is None and self.isVisible() and same_root(origin,int(self.winId())):self.hide();return
        if is_window(origin) and not same_root(origin,int(self.winId())):self.target=origin
        else:self.target=0
        self.refresh();screen=QApplication.screenAt(self.cursor().pos()) or QApplication.primaryScreen();area=screen.availableGeometry()
        self.resize(min(510,area.width()-24),min(740,area.height()-24))
        point=self.cursor().pos();x=max(area.left()+10,min(point.x()-self.width()//2,area.right()-self.width()-10));y=max(area.top()+10,min(point.y()-40,area.bottom()-self.height()-10));self.move(x,y)
        self.show();self.raise_();self.activateWindow();restore_foreground(int(self.winId()));self.search.setFocus()
    def toggle_pause(self):self.paused=not self.paused;self.history.setting('paused','1' if self.paused else '0');self.update_pause()
    def update_pause(self):
        self.pause_button.setText('继续记录' if self.paused else '暂停记录');self.pause_action.setChecked(self.paused)
        self.status.setText('已暂停。现有历史仍可回贴。' if self.paused else f'正在本地记录 · {self.hotkey_text} 呼出 · 最近 50 条')
    def context_menu(self,point):
        item=self.list.itemAt(point)
        if not item:return
        self.list.setCurrentItem(item);id=self.selected_id();row=self.history.get(id);menu=QMenu(self)
        menu.addAction('粘贴回原窗口',lambda:self.paste_clip(id));menu.addAction('只复制',lambda:self.copy_clip(id));menu.addAction('预览',lambda:self.preview('view'))
        if row['kind']=='text':
            menu.addSeparator();menu.addAction('清洗为纯文本',lambda:self.preview('clean'));menu.addAction('提取网址',lambda:self.preview('urls'));menu.addAction('提取邮箱',lambda:self.preview('emails'));menu.addAction('在线翻译…',self.translate)
        menu.addSeparator();menu.addAction('删除这条',lambda:self.delete_clip(id));menu.exec(self.list.mapToGlobal(point))
    def delete_clip(self,id):self.history.delete(id);self.refresh();self.status.setText('已删除这条历史。')
    def clear_history(self):
        if QMessageBox.question(self,'清空历史','删除本地全部 50 条以内的历史？系统剪贴板当前内容不会被清空。')==QMessageBox.StandardButton.Yes:self.history.clear();self.refresh();self.status.setText('本地历史已清空。')
    def process_text(self,mode):
        row=self.history.get(self.selected_id())
        if not row or row['kind']!='text':return ''
        text=row['text']
        return {'clean':clean_text,'urls':lambda s:'\n'.join(extract_urls(s)),'emails':lambda s:'\n'.join(extract_emails(s)),'view':lambda s:s}[mode](text)
    def preview(self,mode):
        row=self.history.get(self.selected_id())
        if not row:return
        d=QDialog(self);d.setWindowTitle({'clean':'清洗为纯文本','urls':'提取网址','emails':'提取邮箱','view':'预览'}[mode]);d.resize(620,440);v=QVBoxLayout(d)
        if row['kind']=='image':
            label=QLabel();pix=QPixmap();pix.loadFromData(row['image'],'PNG');label.setPixmap(pix.scaled(580,340,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));v.addWidget(label);v.addWidget(btn('关闭',d.accept));d.exec();return
        result=self.process_text(mode);edit=QPlainTextEdit(result);v.addWidget(edit)
        v.addWidget(text_label('结果可编辑。复制结果为纯文本，不含富文本格式。' if result else '没有找到匹配内容。',True))
        h=QHBoxLayout()
        def copy():self.copy_text(edit.toPlainText());self.status.setText('结果已复制为纯文本。');d.accept()
        def paste():self.copy_text(edit.toPlainText());d.accept();self.perform_paste()
        h.addWidget(btn('复制结果',copy));h.addWidget(btn('粘贴回原窗口',paste,True));h.addWidget(btn('关闭',d.reject));v.addLayout(h);d.exec()
    def translate(self):
        row=self.history.get(self.selected_id())
        if not row or row['kind']!='text':return
        try:url=translation_url(row['text'])
        except ValueError as exc:self.status.setText(str(exc));return
        if QMessageBox.question(self,'打开在线翻译','将把当前这一条文字发送至 Bing 翻译网页。其他历史不会发送。是否继续？')==QMessageBox.StandardButton.Yes:QDesktopServices.openUrl(QUrl(url))
    def settings_dialog(self):
        d=QDialog(self);d.setWindowTitle('Reclip 设置');v=QVBoxLayout(d);v.addWidget(text_label('呼出快捷键'))
        editor=QKeySequenceEdit(QKeySequence(self.hotkey_text));editor.setMaximumSequenceLength(1);v.addWidget(editor)
        v.addWidget(text_label('使用修饰键加字母、数字或 F1–F11，例如 Alt+V、Ctrl+Alt+V。冲突时会保留旧热键。',True));v.addWidget(text_label(f'本地记录：{self.history.path}\n文本上限 1 MiB，单图上限 20 MiB。\n关闭浮窗会收起到托盘；窗口“退出”或托盘菜单可退出。',True))
        row=QHBoxLayout()
        def save():
            combo=editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            try:
                parse_hotkey(combo)
                if not self.hk.register(combo):QMessageBox.warning(d,'热键被占用','这个组合键无法注册。原热键仍保留，请选择其他组合。');return
            except ValueError as exc:QMessageBox.warning(d,'组合键无效',str(exc));return
            self.hotkey_registered=True;self.hotkey_text=combo;self.history.setting('hotkey',combo);self.hotkey_badge.setText(combo);self.tray.setToolTip('Reclip｜回拾 · '+combo);self.update_pause();d.accept()
        row.addWidget(btn('保存',save,True));row.addWidget(btn('取消',d.reject));v.addLayout(row);d.exec()
    def closeEvent(self,event):
        if not self.quitting and self.tray.isVisible():self.hide();event.ignore()
        else:event.accept()
    def shutdown(self):
        if self.closed:return
        self.quitting=True;self.closed=True;self.pending_paste=None
        try:self.clipboard.dataChanged.disconnect(self.capture)
        except (TypeError,RuntimeError):pass
        self.hk.close();self.tray.hide();self.history.close();self.close()
    def request_quit(self):self.quit_requested.emit()
