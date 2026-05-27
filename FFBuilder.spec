# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets'), ('app/gui_qt/ui', 'app/gui_qt/ui'), ('app/templates/default_templates', 'app/templates/default_templates')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.QtQmlModels', 'PySide6.QtQmlWorkerScript', 'PySide6.QtQmlMeta', 'PySide6.QtPdf', 'PySide6.QtVirtualKeyboard', 'PySide6.QtBluetooth', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtSerialPort', 'PySide6.QtSerialBus', 'PySide6.QtTextToSpeech', 'PySide6.QtSensors', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras', 'PySide6.QtRemoteObjects', 'PySide6.QtStateMachine', 'PySide6.QtConcurrent', 'tkinter', 'unittest', 'xmlrpc', 'pydoc', 'doctest', 'matplotlib', 'numpy', 'PIL', 'contourpy', 'cycler', 'kiwisolver'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FFBuilder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',
    codesign_identity=None,
    entitlements_file=None,
    icon=['/Users/levi/Desktop/converter/assets/icons/app.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name='FFBuilder',
)
app = BUNDLE(
    coll,
    name='FFBuilder.app',
    icon='/Users/levi/Desktop/converter/assets/icons/app.icns',
    bundle_identifier=None,
)
