#!/usr/bin/env python3
"""
PyInstaller 빌드 스크립트 - 단일 실행 파일 생성

폐쇄망 환경에서 사용할 수 있도록 모든 의존성을 포함한
단일 실행 파일을 생성합니다.

사용법:
    python build.py

결과물:
    dist/ssh_manager (Linux)
    dist/ssh_manager.exe (Windows)

빌드 옵션 설명:
    --onefile: 단일 파일로 패키징 (느린 시작, 배포 편리)
    --onedir: 디렉토리로 패키징 (빠른 시작, 파일 많음)
    --noconsole: GUI 앱용 (콘솔 숨김) - 우리는 사용 안 함
    --hidden-import: 동적 import 모듈 명시
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def check_pyinstaller():
    """PyInstaller 설치 확인"""
    try:
        import PyInstaller
        print(f"PyInstaller 버전: {PyInstaller.__version__}")
        return True
    except ImportError:
        print("PyInstaller가 설치되어 있지 않습니다.")
        print("설치: pip install pyinstaller")
        return False


def build():
    """빌드 실행"""
    if not check_pyinstaller():
        sys.exit(1)
    
    # 현재 디렉토리 확인
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)
    
    print(f"빌드 디렉토리: {script_dir}")
    
    # 이전 빌드 결과물 정리
    for folder in ['build', 'dist']:
        if Path(folder).exists():
            print(f"이전 {folder} 폴더 삭제...")
            shutil.rmtree(folder)
    
    spec_file = Path('ssh_manager.spec')
    if spec_file.exists():
        spec_file.unlink()
    
    # PyInstaller 옵션
    # --onefile: 단일 실행 파일 생성
    # --name: 출력 파일 이름
    # --hidden-import: 동적으로 로드되는 모듈 명시
    #   - paramiko 관련: 암호화 백엔드
    #   - cryptography 관련: Fernet 암호화
    
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onedir',                     # 폴더 형태 (더 안정적)
        '--name', 'ssh_manager',        # 출력 이름
        '--clean',                      # 캐시 정리 후 빌드
        '--noconfirm',                  # 확인 없이 덮어쓰기
        
        # paramiko가 사용하는 암호화 모듈들
        '--hidden-import', 'paramiko',
        '--hidden-import', 'paramiko.transport',
        '--hidden-import', 'paramiko.sftp',
        '--hidden-import', 'paramiko.sftp_client',
        '--hidden-import', 'paramiko.channel',
        '--hidden-import', 'paramiko.auth_handler',
        
        # cryptography 모듈 (Fernet 암호화)
        '--hidden-import', 'cryptography',
        '--hidden-import', 'cryptography.fernet',
        '--hidden-import', 'cryptography.hazmat.primitives',
        '--hidden-import', 'cryptography.hazmat.primitives.kdf.pbkdf2',
        '--hidden-import', 'cryptography.hazmat.primitives.hashes',
        '--hidden-import', 'cryptography.hazmat.backends',
        '--hidden-import', 'cryptography.hazmat.backends.openssl',
        
        # bcrypt (paramiko 의존성)
        '--hidden-import', 'bcrypt',
        '--hidden-import', 'nacl',
        '--hidden-import', 'nacl.bindings',
        
        # rich TUI 라이브러리
        '--hidden-import', 'rich',
        '--hidden-import', 'rich.console',
        '--hidden-import', 'rich.table',
        '--hidden-import', 'rich.panel',
        '--hidden-import', 'rich.prompt',
        '--hidden-import', 'rich.progress',
        '--hidden-import', 'rich.live',
        '--hidden-import', 'rich.layout',
        '--hidden-import', 'rich.text',
        '--hidden-import', 'rich.box',
        
        # 표준 라이브러리 (일부 동적 로드)
        '--hidden-import', 'json',
        '--hidden-import', 'uuid',
        '--hidden-import', 'getpass',
        '--hidden-import', 'threading',
        '--hidden-import', 'queue',
        
        # 진입점
        'run.py'
    ]
    
    print("\n빌드 시작...")
    print(f"명령: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n" + "=" * 50)
        print("빌드 성공!")
        print("=" * 50)
        
        # 결과물 위치
        if sys.platform == 'win32':
            output = script_dir / 'dist' / 'ssh_manager.exe'
        else:
            output = script_dir / 'dist' / 'ssh_manager'
        
        if output.exists():
            size_mb = output.stat().st_size / (1024 * 1024)
            print(f"\n실행 파일: {output}")
            print(f"파일 크기: {size_mb:.1f} MB")
            print("\n사용법:")
            if sys.platform == 'win32':
                print("    dist\\ssh_manager.exe")
            else:
                print("    ./dist/ssh_manager")
                print("\n폐쇄망으로 복사 후 실행 권한 부여:")
                print("    chmod +x ssh_manager")
    else:
        print("\n빌드 실패!")
        sys.exit(1)


if __name__ == '__main__':
    build()

