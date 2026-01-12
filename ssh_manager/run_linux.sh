#!/bin/bash
# SSH Manager 리눅스 실행 스크립트

cd "$(dirname "$0")"

# 가상환경이 없으면 설치 스크립트 실행
if [ ! -d "venv" ]; then
    echo "가상환경이 없습니다. 설치를 먼저 진행합니다..."
    ./install_linux.sh
fi

# 가상환경 활성화 및 실행
source venv/bin/activate
python run.py

