@echo off
REM SSH Manager 리눅스용 빌드 스크립트 (Docker 사용)
REM 실행 전 Docker Desktop이 실행 중이어야 합니다.

echo ==========================================
echo SSH Manager 리눅스 빌드 (Docker)
echo ==========================================

REM Docker 실행 확인
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Docker가 설치되어 있지 않거나 실행 중이 아닙니다.
    echo Docker Desktop을 설치하고 실행하세요.
    echo https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

echo.
echo [1/3] Docker 이미지 빌드 중...
docker build -t ssh_manager_builder .

if %errorlevel% neq 0 (
    echo [오류] Docker 이미지 빌드 실패
    pause
    exit /b 1
)

echo.
echo [2/3] 컨테이너에서 빌드 결과물 추출 중...

REM 기존 linux_dist 폴더 삭제
if exist linux_dist rmdir /s /q linux_dist

REM 컨테이너 생성 및 파일 복사
docker create --name ssh_temp ssh_manager_builder
docker cp ssh_temp:/app/dist/ssh_manager ./linux_dist
docker rm ssh_temp

echo.
echo [3/3] 정리 중...
docker rmi ssh_manager_builder

echo.
echo ==========================================
echo 빌드 완료!
echo ==========================================
echo.
echo 리눅스 실행 파일 위치: linux_dist\ssh_manager
echo.
echo 사용법:
echo   1. linux_dist 폴더를 리눅스로 복사
echo   2. chmod +x ssh_manager
echo   3. ./ssh_manager
echo.
pause

