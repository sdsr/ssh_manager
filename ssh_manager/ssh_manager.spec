# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['paramiko', 'paramiko.transport', 'paramiko.sftp', 'paramiko.sftp_client', 'paramiko.channel', 'paramiko.auth_handler', 'cryptography', 'cryptography.fernet', 'cryptography.hazmat.primitives', 'cryptography.hazmat.primitives.kdf.pbkdf2', 'cryptography.hazmat.primitives.hashes', 'cryptography.hazmat.backends', 'cryptography.hazmat.backends.openssl', 'bcrypt', 'nacl', 'nacl.bindings', 'rich', 'rich.console', 'rich.table', 'rich.panel', 'rich.prompt', 'rich.progress', 'rich.live', 'rich.layout', 'rich.text', 'rich.box', 'json', 'uuid', 'getpass', 'threading', 'queue'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ssh_manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ssh_manager',
)
