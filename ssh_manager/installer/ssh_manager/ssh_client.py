"""
SSH 클라이언트 모듈 - SSH 연결 및 명령 실행 관리

구현 방식:
- paramiko 라이브러리 사용 (순수 Python SSH 구현)
- 연결 풀링으로 다중 서버 동시 접속
- 스레드 기반 비동기 명령 실행

장점:
- 플랫폼 독립적 (Windows, Linux, Mac)
- OpenSSH 없이도 동작
- 세밀한 제어 가능

단점:
- 네이티브 SSH보다 약간 느림
- 일부 고급 SSH 기능 미지원
"""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional
from queue import Queue, Empty
import paramiko
from paramiko import SSHClient, AutoAddPolicy, AuthenticationException, SSHException

from .server import Server


@dataclass
class CommandResult:
    """명령 실행 결과를 담는 데이터 클래스"""
    server: Server
    command: str
    stdout: str
    stderr: str
    exit_code: int
    success: bool
    error_message: str = ""
    execution_time: float = 0.0


class SSHConnection:
    """단일 SSH 연결 관리 클래스"""
    
    def __init__(self, server: Server, timeout: int = 30):
        """
        Args:
            server: 연결할 서버 정보
            timeout: 연결 타임아웃 (초)
        """
        self.server = server
        self.timeout = timeout
        self._client: Optional[SSHClient] = None
        self._connected = False
        self._lock = threading.Lock()
    
    def connect(self) -> tuple[bool, str]:
        """
        SSH 연결 수립
        
        Returns:
            (성공 여부, 오류 메시지)
        """
        with self._lock:
            if self._connected:
                return True, ""
            
            try:
                self._client = SSHClient()
                
                # 호스트 키 정책 설정
                # AutoAddPolicy: 처음 접속하는 호스트의 키를 자동으로 추가
                # 주의: 프로덕션에서는 보안상 RejectPolicy 권장
                self._client.set_missing_host_key_policy(AutoAddPolicy())
                
                self._client.connect(
                    hostname=self.server.host,
                    port=self.server.port,
                    username=self.server.username,
                    password=self.server.password,
                    timeout=self.timeout,
                    allow_agent=False,      # SSH 에이전트 사용 안함
                    look_for_keys=False,    # 로컬 키 파일 검색 안함
                )
                
                self._connected = True
                return True, ""
                
            except AuthenticationException:
                return False, "인증 실패: 사용자 이름 또는 비밀번호가 틀립니다."
            except SSHException as e:
                return False, f"SSH 오류: {str(e)}"
            except TimeoutError:
                return False, f"연결 타임아웃: {self.timeout}초 초과"
            except Exception as e:
                return False, f"연결 실패: {str(e)}"
    
    def disconnect(self) -> None:
        """SSH 연결 종료"""
        with self._lock:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
                finally:
                    self._client = None
                    self._connected = False
    
    def execute(self, command: str, timeout: int = None) -> CommandResult:
        """
        명령 실행
        
        Args:
            command: 실행할 명령어
            timeout: 명령 실행 타임아웃 (초)
            
        Returns:
            명령 실행 결과
        """
        start_time = time.time()
        
        if not self._connected:
            success, error = self.connect()
            if not success:
                return CommandResult(
                    server=self.server,
                    command=command,
                    stdout="",
                    stderr="",
                    exit_code=-1,
                    success=False,
                    error_message=error
                )
        
        try:
            # exec_command는 새 채널을 생성하여 명령 실행
            # get_pty=True: 의사 터미널 할당 (sudo 등에 필요할 수 있음)
            stdin, stdout, stderr = self._client.exec_command(
                command,
                timeout=timeout or self.timeout
            )
            
            # 출력 읽기
            stdout_text = stdout.read().decode('utf-8', errors='replace')
            stderr_text = stderr.read().decode('utf-8', errors='replace')
            exit_code = stdout.channel.recv_exit_status()
            
            execution_time = time.time() - start_time
            
            return CommandResult(
                server=self.server,
                command=command,
                stdout=stdout_text,
                stderr=stderr_text,
                exit_code=exit_code,
                success=(exit_code == 0),
                execution_time=execution_time
            )
            
        except Exception as e:
            return CommandResult(
                server=self.server,
                command=command,
                stdout="",
                stderr="",
                exit_code=-1,
                success=False,
                error_message=str(e),
                execution_time=time.time() - start_time
            )
    
    def get_shell(self) -> Optional[paramiko.Channel]:
        """
        인터랙티브 쉘 채널 반환
        
        Returns:
            SSH 채널 (쉘)
        """
        if not self._connected:
            success, _ = self.connect()
            if not success:
                return None
        
        try:
            channel = self._client.invoke_shell(
                term='xterm-256color',
                width=120,
                height=40
            )
            return channel
        except Exception:
            return None
    
    @property
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return self._connected and self._client is not None
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


class MultiSSHManager:
    """다중 SSH 연결 관리 및 병렬 명령 실행 클래스"""
    
    def __init__(self):
        self._connections: dict[str, SSHConnection] = {}
        self._lock = threading.Lock()
    
    def add_connection(self, server: Server) -> tuple[bool, str]:
        """
        서버 연결 추가
        
        Args:
            server: 연결할 서버
            
        Returns:
            (성공 여부, 오류 메시지)
        """
        with self._lock:
            if server.id in self._connections:
                return True, "이미 연결됨"
            
            conn = SSHConnection(server)
            success, error = conn.connect()
            
            if success:
                self._connections[server.id] = conn
            
            return success, error
    
    def remove_connection(self, server_id: str) -> None:
        """서버 연결 제거"""
        with self._lock:
            if server_id in self._connections:
                self._connections[server_id].disconnect()
                del self._connections[server_id]
    
    def get_connection(self, server_id: str) -> Optional[SSHConnection]:
        """서버 연결 조회"""
        return self._connections.get(server_id)
    
    def execute_on_all(
        self, 
        command: str, 
        callback: Callable[[CommandResult], None] = None,
        timeout: int = 30
    ) -> list[CommandResult]:
        """
        모든 연결된 서버에 명령 동시 실행
        
        구현 방식: 스레드 풀 사용
        - 각 서버마다 별도 스레드에서 명령 실행
        - Queue를 통해 결과 수집
        - 콜백으로 실시간 결과 전달 가능
        
        Args:
            command: 실행할 명령어
            callback: 각 서버 결과가 나올 때마다 호출될 함수
            timeout: 명령 타임아웃
            
        Returns:
            모든 서버의 실행 결과 리스트
        """
        results = []
        result_queue = Queue()
        threads = []
        
        def execute_task(conn: SSHConnection):
            result = conn.execute(command, timeout)
            result_queue.put(result)
            if callback:
                callback(result)
        
        # 모든 연결에 대해 스레드 생성
        for conn in self._connections.values():
            thread = threading.Thread(target=execute_task, args=(conn,))
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
    
    def execute_on_selected(
        self,
        server_ids: list[str],
        command: str,
        callback: Callable[[CommandResult], None] = None,
        timeout: int = 30
    ) -> list[CommandResult]:
        """
        선택한 서버들에만 명령 실행
        
        Args:
            server_ids: 대상 서버 ID 목록
            command: 실행할 명령어
            callback: 결과 콜백
            timeout: 타임아웃
        """
        results = []
        result_queue = Queue()
        threads = []
        
        def execute_task(conn: SSHConnection):
            result = conn.execute(command, timeout)
            result_queue.put(result)
            if callback:
                callback(result)
        
        for server_id in server_ids:
            if server_id in self._connections:
                conn = self._connections[server_id]
                thread = threading.Thread(target=execute_task, args=(conn,))
                thread.start()
                threads.append(thread)
        
        for thread in threads:
            thread.join()
        
        while True:
            try:
                result = result_queue.get_nowait()
                results.append(result)
            except Empty:
                break
        
        return results
    
    def disconnect_all(self) -> None:
        """모든 연결 종료"""
        with self._lock:
            for conn in self._connections.values():
                conn.disconnect()
            self._connections.clear()
    
    @property
    def connected_servers(self) -> list[Server]:
        """연결된 서버 목록"""
        return [conn.server for conn in self._connections.values() if conn.is_connected]
    
    @property
    def connection_count(self) -> int:
        """연결 수"""
        return len(self._connections)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect_all()

