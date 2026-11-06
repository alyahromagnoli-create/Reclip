import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication,QMessageBox
from app import ReclipWindow
from windows_api import SingleInstance
from portable_paths import database_path

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--smoke-test',type=Path,help=argparse.SUPPRESS);args=parser.parse_args()
    app=QApplication(sys.argv);app.setApplicationName('Reclip');app.setQuitOnLastWindowClosed(False)
    lock=None if args.smoke_test else SingleInstance()
    if lock and lock.already_running:
        QMessageBox.information(None,'Reclip 已在运行','回拾已在托盘中运行。请使用已设置的快捷键或托盘图标呼出。');lock.close();return 0
    data=database_path('Reclip')
    if args.smoke_test:
        from history import History
        history=History(data);history.setting('paused','1');history.close()
    try:window=ReclipWindow(data,register_hotkey=not bool(args.smoke_test))
    except Exception as exc:
        QMessageBox.critical(None,'无法启动 Reclip',f'数据目录不可写或无法初始化：{data}\n请把 EXE 和 data 一起放到可写文件夹。\n{exc}')
        if lock:lock.close()
        return 1
    # Explicit tray Exit closes the application; close-window otherwise hides it.
    original_shutdown=window.shutdown
    app.aboutToQuit.connect(original_shutdown)
    window.destroyed.connect(app.quit)
    window.quit_requested.connect(app.quit)
    if not window.tray.isVisible():app.setQuitOnLastWindowClosed(True)
    window.show()
    if args.smoke_test:
        from PyQt6.QtCore import QTimer
        import json
        def smoke():
            before=len(window.history.items());window.history.add_text('portable smoke synthetic text');window.refresh()
            report={'visible':window.isVisible(),'database':str(data),'records_before':before,'records_after':len(window.history.items()),'paused':window.paused,'runtime':str(getattr(sys,'_MEIPASS','')),'hotkey_registered':window.hotkey_registered}
            window.grab().save(str(args.smoke_test.with_suffix('.png')));args.smoke_test.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');window.exit_button.click()
        QTimer.singleShot(400,smoke)
    result=app.exec();original_shutdown()
    if lock:lock.close()
    return result

if __name__=='__main__':sys.exit(main())
