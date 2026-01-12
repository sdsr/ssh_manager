#!/bin/bash
# SSH Manager 리눅스 오프라인 설치 스크립트

echo "=========================================="
echo "SSH Manager 리눅스 설치"
echo "=========================================="

# 스크립트가 있는 디렉토리로 이동
cd "$(dirname "$0")"

# Python3 확인
if ! command -v python3 &> /dev/null; then
    echo "[오류] python3가 설치되어 있지 않습니다."
    echo "설치: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

echo "[1/3] 가상환경 생성 중..."
python3 -m venv venv

echo "[2/3] 가상환경 활성화..."
source venv/bin/activate

echo "[3/3] 패키지 설치 중 (오프라인)..."
pip install --no-index --find-links=./packages \
    paramiko rich textual cryptography

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "설치 완료!"
    echo "=========================================="
    echo ""
    echo "실행 방법:"
    echo "  cd $(pwd)"
    echo "  source venv/bin/activate"
    echo "  python run.py"
    echo ""
    echo "또는 바로 실행:"
    echo "  ./run_linux.sh"
    echo ""
else
    echo ""
    echo "[오류] 패키지 설치 실패"
    echo "Python 버전을 확인하세요 (3.10 권장)"
    exit 1
fi

