"""
파일 전송 모듈 - SCP/SFTP를 통한 파일 업로드/다운로드

구현 방식:
- paramiko의 SFTP 클라이언트 사용
- SCP 프로토콜 대신 SFTP 사용 (더 안정적)
- 진행률 콜백 지원

SFTP vs SCP:
- SFTP: SSH 서브시스템, 더 많은 기능 (디렉토리 작업, 권한 설정 등)
- SCP: 단순 파일 복사, 약간 빠름
- 여기서는 SFTP 사용 (paramiko 기본 지원, 더 유연함)
"""

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from queue import Queue, Empty

import paramiko
from paramiko import SFTPClient, SSHClient, AutoAddPolicy

from .server import Server


@dataclass
class TransferProgress:
    """전송 진행 상황"""
    server: Server
    filename: str
    transferred: int      # 전송된 바이트
    total: int            # 전체 바이트
    percentage: float     # 진행률 (0-100)
    speed: float          # 전송 속도 (bytes/sec)


@dataclass  
class TransferResult:
    """파일 전송 결과"""
    server: Server
    local_path: str
    remote_path: str
    success: bool
    error_message: str = ""
    transferred_bytes: int = 0
    elapsed_time: float = 0.0
    
    @property
    def speed(self) -> float:
        """전송 속도 (bytes/sec)"""
        if self.elapsed_time > 0:
            return self.transferred_bytes / self.elapsed_time
        return 0.0


class SFTPTransfer:
    """단일 서버 SFTP 전송 클래스"""
    
    def __init__(self, server: Server, timeout: int = 30):
        self.server = server
        self.timeout = timeout
        self._ssh_client: Optional[SSHClient] = None
        self._sftp_client: Optional[SFTPClient] = None
    
    def connect(self) -> tuple[bool, str]:
        """SFTP 연결 수립"""
        try:
            self._ssh_client = SSHClient()
            self._ssh_client.set_missing_host_key_policy(AutoAddPolicy())
            
            self._ssh_client.connect(
                hostname=self.server.host,
                port=self.server.port,
                username=self.server.username,
                password=self.server.password,
                timeout=self.timeout,
                allow_agent=False,
                look_for_keys=False,
            )
            
            # SFTP 세션 열기
            self._sftp_client = self._ssh_client.open_sftp()
            return True, ""
            
        except Exception as e:
            return False, str(e)
    
    def disconnect(self) -> None:
        """연결 종료"""
        try:
            if self._sftp_client:
                self._sftp_client.close()
            if self._ssh_client:
                self._ssh_client.close()
        except Exception:
            pass
        finally:
            self._sftp_client = None
            self._ssh_client = None
    
    def upload(
        self, 
        local_path: str, 
        remote_path: str,
        progress_callback: Callable[[TransferProgress], None] = None
    ) -> TransferResult:
        """
        파일 업로드
        
        Args:
            local_path: 로컬 파일 경로
            remote_path: 원격 저장 경로
            progress_callback: 진행률 콜백
            
        Returns:
            전송 결과
        """
        import time
        start_time = time.time()
        
        if not self._sftp_client:
            success, error = self.connect()
            if not success:
                return TransferResult(
                    server=self.server,
                    local_path=local_path,
                    remote_path=remote_path,
                    success=False,
                    error_message=error
                )
        
        try:
            local_file = Path(local_path)
            if not local_file.exists():
                return TransferResult(
                    server=self.server,
                    local_path=local_path,
                    remote_path=remote_path,
                    success=False,
                    error_message=f"로컬 파일을 찾을 수 없습니다: {local_path}"
                )
            
            file_size = local_file.stat().st_size
            transferred = [0]  # 리스트로 감싸서 클로저에서 수정 가능하게
            last_time = [start_time]
            
            # 원격 경로가 디렉토리면 파일명 자동 추가
            if remote_path.endswith('/'):
                remote_path = remote_path + local_file.name
            
            def callback(current: int, total: int):
                """paramiko SFTP 콜백"""
                transferred[0] = current
                current_time = time.time()
                elapsed = current_time - last_time[0]
                
                if progress_callback and elapsed > 0.1:  # 100ms마다 업데이트
                    speed = current / (current_time - start_time) if current_time > start_time else 0
                    progress = TransferProgress(
                        server=self.server,
                        filename=local_file.name,
                        transferred=current,
                        total=total,
                        percentage=(current / total * 100) if total > 0 else 0,
                        speed=speed
                    )
                    progress_callback(progress)
                    last_time[0] = current_time
            
            # 원격 디렉토리 생성 (필요한 경우)
            remote_dir = str(Path(remote_path).parent)
            self._mkdir_p(remote_dir)
            
            # 파일 업로드
            self._sftp_client.put(local_path, remote_path, callback=callback)
            
            elapsed = time.time() - start_time
            
            return TransferResult(
                server=self.server,
                local_path=local_path,
                remote_path=remote_path,
                success=True,
                transferred_bytes=file_size,
                elapsed_time=elapsed
            )
            
        except Exception as e:
            return TransferResult(
                server=self.server,
                local_path=local_path,
                remote_path=remote_path,
                success=False,
                error_message=str(e),
                elapsed_time=time.time() - start_time
            )
    
    def download(
        self,
        remote_path: str,
        local_path: str,
        progress_callback: Callable[[TransferProgress], None] = None
    ) -> TransferResult:
        """
        파일 다운로드
        
        Args:
            remote_path: 원격 파일 경로
            local_path: 로컬 저장 경로
            progress_callback: 진행률 콜백
        """
        import time
        start_time = time.time()
        
        if not self._sftp_client:
            success, error = self.connect()
            if not success:
                return TransferResult(
                    server=self.server,
                    local_path=local_path,
                    remote_path=remote_path,
                    success=False,
                    error_message=error
                )
        
        try:
            # 원격 파일 크기 확인
            file_stat = self._sftp_client.stat(remote_path)
            file_size = file_stat.st_size
            
            transferred = [0]
            last_time = [start_time]
            
            def callback(current: int, total: int):
                transferred[0] = current
                current_time = time.time()
                elapsed = current_time - last_time[0]
                
                if progress_callback and elapsed > 0.1:
                    speed = current / (current_time - start_time) if current_time > start_time else 0
                    progress = TransferProgress(
                        server=self.server,
                        filename=Path(remote_path).name,
                        transferred=current,
                        total=total,
                        percentage=(current / total * 100) if total > 0 else 0,
                        speed=speed
                    )
                    progress_callback(progress)
                    last_time[0] = current_time
            
            # 로컬 디렉토리 생성
            local_dir = Path(local_path).parent
            local_dir.mkdir(parents=True, exist_ok=True)
            
            # 파일 다운로드
            self._sftp_client.get(remote_path, local_path, callback=callback)
            
            elapsed = time.time() - start_time
            
            return TransferResult(
                server=self.server,
                local_path=local_path,
                remote_path=remote_path,
                success=True,
                transferred_bytes=file_size,
                elapsed_time=elapsed
            )
            
        except FileNotFoundError:
            return TransferResult(
                server=self.server,
                local_path=local_path,
                remote_path=remote_path,
                success=False,
                error_message=f"원격 파일을 찾을 수 없습니다: {remote_path}",
                elapsed_time=time.time() - start_time
            )
        except Exception as e:
            return TransferResult(
                server=self.server,
                local_path=local_path,
                remote_path=remote_path,
                success=False,
                error_message=str(e),
                elapsed_time=time.time() - start_time
            )
    
    def upload_directory(
        self,
        local_dir: str,
        remote_dir: str,
        progress_callback: Callable[[TransferProgress], None] = None
    ) -> list[TransferResult]:
        """
        폴더 전체 업로드 (재귀적)
        
        Args:
            local_dir: 로컬 폴더 경로
            remote_dir: 원격 폴더 경로
            progress_callback: 진행률 콜백
            
        Returns:
            각 파일의 전송 결과 리스트
        """
        import glob
        
        results = []
        local_path = Path(local_dir)
        
        if not local_path.exists():
            return [TransferResult(
                server=self.server,
                local_path=local_dir,
                remote_path=remote_dir,
                success=False,
                error_message=f"로컬 경로를 찾을 수 없습니다: {local_dir}"
            )]
        
        # 와일드카드 패턴 처리 (예: /path/*.txt, /path/*)
        if '*' in local_dir:
            files = glob.glob(local_dir, recursive=True)
            base_dir = str(Path(local_dir.split('*')[0]).parent)
        elif local_path.is_file():
            # 단일 파일
            return [self.upload(local_dir, remote_dir, progress_callback)]
        else:
            # 폴더 전체
            files = []
            for f in local_path.rglob('*'):
                if f.is_file():
                    files.append(str(f))
            base_dir = str(local_path)
        
        if not files:
            return [TransferResult(
                server=self.server,
                local_path=local_dir,
                remote_path=remote_dir,
                success=False,
                error_message="전송할 파일이 없습니다."
            )]
        
        # 각 파일 업로드
        for local_file in files:
            # 상대 경로 계산
            rel_path = os.path.relpath(local_file, base_dir)
            remote_file = os.path.join(remote_dir, rel_path).replace('\\', '/')
            
            result = self.upload(local_file, remote_file, progress_callback)
            results.append(result)
        
        return results
    
    def _mkdir_p(self, remote_dir: str) -> None:
        """
        원격 디렉토리 재귀적 생성 (mkdir -p와 동일)
        
        구현 방식:
        - 경로를 위에서부터 순차적으로 생성 시도
        - 이미 존재하면 무시
        """
        if remote_dir in ('', '/', '.'):
            return
        
        dirs = []
        current = remote_dir
        
        # 존재하지 않는 디렉토리 경로 수집
        while current and current != '/':
            try:
                self._sftp_client.stat(current)
                break  # 존재하면 중단
            except FileNotFoundError:
                dirs.append(current)
                current = str(Path(current).parent)
        
        # 역순으로 생성 (상위 디렉토리부터)
        for d in reversed(dirs):
            try:
                self._sftp_client.mkdir(d)
            except Exception:
                pass  # 이미 존재하거나 권한 문제
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


class MultiFileTransfer:
    """다중 서버 파일 전송 관리 클래스"""
    
    def __init__(self):
        self._lock = threading.Lock()
    
    def upload_to_servers(
        self,
        servers: list[Server],
        local_path: str,
        remote_path: str,
        progress_callback: Callable[[TransferProgress], None] = None,
        result_callback: Callable[[TransferResult], None] = None
    ) -> list[TransferResult]:
        """
        여러 서버에 같은 파일/폴더 동시 업로드
        
        Args:
            servers: 대상 서버 목록
            local_path: 로컬 파일/폴더 경로 (와일드카드 지원: *, **/*)
            remote_path: 원격 저장 경로
            progress_callback: 진행률 콜백
            result_callback: 각 서버 전송 완료 시 콜백
            
        Returns:
            모든 서버의 전송 결과
        """
        results = []
        result_queue = Queue()
        threads = []
        
        # 폴더/와일드카드 여부 확인
        is_directory = Path(local_path).is_dir() if '*' not in local_path else False
        is_pattern = '*' in local_path
        
        def upload_task(server: Server):
            transfer = SFTPTransfer(server)
            try:
                if is_directory or is_pattern:
                    # 폴더 또는 패턴 업로드
                    file_results = transfer.upload_directory(local_path, remote_path, progress_callback)
                    for r in file_results:
                        result_queue.put(r)
                        if result_callback:
                            result_callback(r)
                else:
                    # 단일 파일 업로드
                    result = transfer.upload(local_path, remote_path, progress_callback)
                    result_queue.put(result)
                    if result_callback:
                        result_callback(result)
            finally:
                transfer.disconnect()
        
        # 각 서버마다 스레드 생성
        for server in servers:
            thread = threading.Thread(target=upload_task, args=(server,))
            thread.start()
            threads.append(thread)
        
        # 모든 스레드 완료 대기
        for thread in threads:
            thread.join()
        
        # 결과 수집
        while True:
            try:
                result = result_queue.get_nowait()
                results.append(result)
            except Empty:
                break
        
        return results
    
    def download_from_server(
        self,
        server: Server,
        remote_path: str,
        local_path: str,
        progress_callback: Callable[[TransferProgress], None] = None
    ) -> TransferResult:
        """
        단일 서버에서 파일 다운로드
        
        Args:
            server: 대상 서버
            remote_path: 원격 파일 경로
            local_path: 로컬 저장 경로
            progress_callback: 진행률 콜백
        """
        transfer = SFTPTransfer(server)
        try:
            return transfer.download(remote_path, local_path, progress_callback)
        finally:
            transfer.disconnect()


def format_size(size_bytes: int) -> str:
    """바이트를 읽기 쉬운 단위로 변환"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def format_speed(bytes_per_sec: float) -> str:
    """전송 속도를 읽기 쉬운 형식으로 변환"""
    return f"{format_size(int(bytes_per_sec))}/s"

