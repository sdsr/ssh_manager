#!/usr/bin/env python3
"""
SSH Manager 실행 스크립트

사용법:
    python run.py
    또는
    chmod +x run.py && ./run.py
"""

import sys
import os

# 현재 디렉토리를 모듈 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ssh_manager.ui import main

if __name__ == "__main__":
    main()

