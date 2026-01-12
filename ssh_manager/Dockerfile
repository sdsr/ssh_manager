# SSH Manager 리눅스 빌드용 Dockerfile
# 윈도우에서 리눅스용 실행 파일 빌드

FROM python:3.10-slim

WORKDIR /app

# 필요한 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    binutils \
    && rm -rf /var/lib/apt/lists/*

# 소스코드 복사
COPY requirements.txt .
COPY run.py .
COPY build.py .
COPY ssh_manager/ ./ssh_manager/

# 의존성 설치
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pyinstaller

# 빌드 실행
RUN python build.py

# 결과물은 /app/dist/ssh_manager/ 에 생성됨

