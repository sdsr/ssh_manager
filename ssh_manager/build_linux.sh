#!/bin/bash
# SSH Manager 리눅스 빌드 스크립트
# 실행 파일로 빌드하고 싶을 때 사용

echo "=========================================="
echo "SSH Manager 리눅스 빌드"
echo "=========================================="

cd "$(dirname "$0")"

# 가상환경 확인
if [ ! -d "venv" ]; then
    echo "가상환경이 없습니다. 먼저 install_linux.sh를 실행하세요."
    exit 1
fi

source venv/bin/activate

# PyInstaller 설치 (오프라인에서는 packages 폴더에 있어야 함)
echo "[1/2] PyInstaller 확인 중..."
if ! pip show pyinstaller &> /dev/null; then
    echo "PyInstaller 설치 중..."
    pip install --no-index --find-links=./packages pyinstaller 2>/dev/null || \
    pip install pyinstaller
fi

echo "[2/2] 빌드 중..."
python build.py

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "빌드 완료!"
    echo "=========================================="
    echo ""
    echo "실행 파일 위치: dist/ssh_manager/ssh_manager"
    echo ""
    echo "실행:"
    echo "  ./dist/ssh_manager/ssh_manager"
    echo ""
fi

