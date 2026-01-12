#!/usr/bin/env python3
"""
SSH Manager - 메인 진입점

실행 방법:
    python -m ssh_manager.main
    또는
    python ssh_manager/main.py
"""

import sys
import argparse

from .ui import main as ui_main, console


def parse_args():
    """명령줄 인수 파싱"""
    parser = argparse.ArgumentParser(
        description="SSH Manager - 다중 SSH 서버 관리 및 동시 작업 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  ssh-manager                    # TUI 모드로 실행
  ssh-manager --version          # 버전 출력
  
기능:
  - SSH 서버 정보 암호화 저장
  - 다중 서버 동시 연결
  - 명령어 브로드캐스트 (같은 명령을 모든 서버에 실행)
  - 파일 일괄 전송 (SCP/SFTP)
"""
    )
    
    parser.add_argument(
        "-v", "--version",
        action="version",
        version="SSH Manager v1.0.0"
    )
    
    return parser.parse_args()


def main():
    """메인 함수"""
    args = parse_args()
    
    # 터미널 환경 체크
    if not sys.stdin.isatty():
        console.print("[red]오류: 터미널 환경에서 실행해주세요.[/red]")
        sys.exit(1)
    
    # TUI 실행
    ui_main()


if __name__ == "__main__":
    main()

