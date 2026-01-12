"""
멀티 터미널 모듈 - 여러 SSH 세션을 분할 화면으로 표시

구현 방식:
1. textual 라이브러리: 윈도우/리눅스 모두 지원하는 TUI 분할 화면
2. tmux 연동: 리눅스에서 tmux가 있으면 더 안정적인 분할 화면

textual 장점:
- 크로스 플랫폼 (Windows, Linux, Mac)
- 현대적인 TUI 프레임워크
- 비동기 이벤트 처리

tmux 장점:
- 네이티브 터미널 성능
- 안정적인 SSH 세션 유지
- 세션 분리/재연결 가능
"""

import os
import sys
import shutil
import subprocess
import threading
import time
from typing import Optional
from pathlib import Path

from .server import Server


def is_tmux_available() -> bool:
    """tmux 설치 여부 확인"""
    return shutil.which('tmux') is not None


def is_running_in_tmux() -> bool:
    """현재 tmux 세션 내에서 실행 중인지 확인"""
    return os.environ.get('TMUX') is not None


class TmuxMultiTerminal:
    """
    tmux를 사용한 멀티 터미널 관리
    
    tmux 구조:
    - 세션(session): 여러 윈도우를 포함
    - 윈도우(window): 여러 패인을 포함
    - 패인(pane): 실제 터미널 화면
    
    이 클래스는 하나의 윈도우에 여러 패인을 만들어
    각 패인에서 SSH 접속을 실행합니다.
    """
    
    SESSION_NAME = "ssh_manager"
    
    def __init__(self):
        self.servers: list[Server] = []
    
    def launch(self, servers: list[Server], sync_input: bool = True) -> bool:
        """
        tmux 분할 화면으로 SSH 접속 실행
        
        Args:
            servers: SSH 접속할 서버 목록
            sync_input: True면 모든 패인에 동시 입력 (synchronize-panes)
            
        Returns:
            실행 성공 여부
        """
        if not servers:
            return False
        
        if not is_tmux_available():
            print("tmux가 설치되어 있지 않습니다.")
            print("설치: sudo apt install tmux")
            return False
        
        self.servers = servers
        
        # 기존 세션 종료
        subprocess.run(
            ['tmux', 'kill-session', '-t', self.SESSION_NAME],
            capture_output=True
        )
        
        # 첫 번째 서버로 새 세션 생성
        first_server = servers[0]
        ssh_cmd = self._build_ssh_command(first_server)
        
        subprocess.run([
            'tmux', 'new-session', '-d',
            '-s', self.SESSION_NAME,
            '-n', 'ssh',
            ssh_cmd
        ])
        
        # 나머지 서버들을 분할 패인으로 추가
        for i, server in enumerate(servers[1:], start=1):
            ssh_cmd = self._build_ssh_command(server)
            
            # 수평/수직 분할 번갈아 사용
            split_opt = '-h' if i % 2 == 1 else '-v'
            
            subprocess.run([
                'tmux', 'split-window', split_opt,
                '-t', f'{self.SESSION_NAME}:ssh',
                ssh_cmd
            ])
            
            # 레이아웃 균등 분배
            subprocess.run([
                'tmux', 'select-layout', '-t', f'{self.SESSION_NAME}:ssh',
                'tiled'
            ])
        
        # 동기화 입력 설정 (모든 패인에 동시 입력)
        if sync_input:
            subprocess.run([
                'tmux', 'set-window-option', '-t', f'{self.SESSION_NAME}:ssh',
                'synchronize-panes', 'on'
            ])
        
        # 패인 테두리에 서버 정보 표시
        subprocess.run([
            'tmux', 'set-option', '-t', self.SESSION_NAME,
            'pane-border-status', 'top'
        ])
        subprocess.run([
            'tmux', 'set-option', '-t', self.SESSION_NAME,
            'pane-border-format', ' #{pane_index}: #{pane_title} '
        ])
        
        # 세션 attach (현재 터미널에 표시)
        # subprocess.call 사용하여 tmux 종료 후 메인 메뉴로 돌아오기
        if is_running_in_tmux():
            # 이미 tmux 안이면 switch
            subprocess.run(['tmux', 'switch-client', '-t', self.SESSION_NAME])
        else:
            # tmux 밖이면 attach (종료 후 돌아옴)
            subprocess.call(['tmux', 'attach-session', '-t', self.SESSION_NAME])
        
        return True
    
    def _build_ssh_command(self, server: Server) -> str:
        """
        SSH 명령어 생성
        
        sshpass를 사용하여 비밀번호 자동 입력
        sshpass가 없으면 일반 ssh (수동 비밀번호 입력)
        """
        if shutil.which('sshpass'):
            # sshpass로 비밀번호 자동 입력
            return (
                f"sshpass -p '{server.password}' ssh -o StrictHostKeyChecking=no "
                f"-p {server.port} {server.username}@{server.host}"
            )
        else:
            # 일반 SSH (비밀번호 수동 입력)
            return (
                f"ssh -o StrictHostKeyChecking=no "
                f"-p {server.port} {server.username}@{server.host}"
            )
    
    @staticmethod
    def toggle_sync() -> None:
        """동기화 입력 토글 (tmux 세션 내에서 실행)"""
        subprocess.run([
            'tmux', 'set-window-option', 'synchronize-panes'
        ])
    
    @staticmethod
    def kill_session() -> None:
        """세션 종료"""
        subprocess.run([
            'tmux', 'kill-session', '-t', TmuxMultiTerminal.SESSION_NAME
        ], capture_output=True)


# ============================================================
# Textual 기반 멀티 터미널 (윈도우/리눅스 모두 지원)
# ============================================================

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical, Grid
    from textual.widgets import Header, Footer, Static, Input, RichLog, Label
    from textual.binding import Binding
    from textual import events
    from rich.text import Text
    from rich.panel import Panel
    import asyncio
    
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


if TEXTUAL_AVAILABLE:
    
    class TerminalPane(Static):
        """단일 SSH 터미널 패인"""
        
        def __init__(self, server: Server, pane_id: int, **kwargs):
            super().__init__(**kwargs)
            self.server = server
            self.pane_id = pane_id
            self.ssh_conn = None
            self.channel = None
            self.output_buffer = []
            self._running = False
        
        def compose(self) -> ComposeResult:
            yield RichLog(id=f"log_{self.pane_id}", wrap=True, markup=True)
        
        async def on_mount(self) -> None:
            """마운트 시 SSH 연결"""
            self._running = True
            asyncio.create_task(self._connect_ssh())
        
        async def _connect_ssh(self) -> None:
            """SSH 연결 및 출력 읽기"""
            log = self.query_one(f"#log_{self.pane_id}", RichLog)
            log.write(f"[yellow]연결 중: {self.server.name}[/yellow]")
            log.write(f"[dim]{self.server.username}@{self.server.host}:{self.server.port}[/dim]")
            
            try:
                import paramiko
                
                # SSH 연결
                self.ssh_conn = paramiko.SSHClient()
                self.ssh_conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.ssh_conn.connect(
                        hostname=self.server.host,
                        port=self.server.port,
                        username=self.server.username,
                        password=self.server.password,
                        timeout=30,
                        allow_agent=False,
                        look_for_keys=False,
                    )
                )
                
                # 인터랙티브 쉘 열기
                self.channel = self.ssh_conn.invoke_shell(
                    term='xterm-256color',
                    width=80,
                    height=24
                )
                self.channel.settimeout(0.1)
                
                log.write(f"[green]연결됨![/green]\n")
                
                # 출력 읽기 루프
                while self._running:
                    try:
                        if self.channel.recv_ready():
                            data = self.channel.recv(4096)
                            if data:
                                text = data.decode('utf-8', errors='replace')
                                # ANSI 이스케이프 코드 일부 처리
                                text = self._clean_ansi(text)
                                log.write(text)
                        await asyncio.sleep(0.05)
                    except Exception:
                        await asyncio.sleep(0.1)
                        
            except Exception as e:
                log.write(f"[red]연결 실패: {e}[/red]")
        
        def _clean_ansi(self, text: str) -> str:
            """ANSI 이스케이프 코드 정리 (기본적인 것만)"""
            import re
            # 커서 이동 등 일부 제어 문자 제거
            text = re.sub(r'\x1b\[\??\d*[hlJK]', '', text)
            text = re.sub(r'\x1b\[\d*[ABCD]', '', text)
            text = re.sub(r'\x1b\[[\d;]*m', '', text)  # 색상 코드 제거
            return text
        
        def send_input(self, text: str) -> None:
            """입력 전송"""
            if self.channel:
                try:
                    self.channel.send(text)
                except Exception:
                    pass
        
        def disconnect(self) -> None:
            """연결 종료"""
            self._running = False
            if self.channel:
                try:
                    self.channel.close()
                except Exception:
                    pass
            if self.ssh_conn:
                try:
                    self.ssh_conn.close()
                except Exception:
                    pass
    
    
    class MultiTerminalApp(App):
        """멀티 터미널 TUI 애플리케이션"""
        
        CSS = """
        Screen {
            layout: grid;
            grid-size: 2;
            grid-gutter: 1;
        }
        
        TerminalPane {
            border: solid green;
            height: 100%;
        }
        
        #input_container {
            dock: bottom;
            height: 3;
            background: $surface;
        }
        
        #command_input {
            width: 100%;
        }
        
        .pane-title {
            background: $primary;
            color: $text;
            text-align: center;
            height: 1;
        }
        
        RichLog {
            height: 100%;
            scrollbar-gutter: stable;
        }
        """
        
        BINDINGS = [
            Binding("ctrl+c", "quit", "종료"),
            Binding("ctrl+a", "toggle_sync", "동기화 토글"),
            Binding("escape", "quit", "종료"),
        ]
        
        def __init__(self, servers: list[Server], **kwargs):
            super().__init__(**kwargs)
            self.servers = servers
            self.panes: list[TerminalPane] = []
            self.sync_mode = True  # 동기화 입력 모드
        
        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            
            # 서버 수에 따라 그리드 레이아웃 조정
            num_servers = len(self.servers)
            
            for i, server in enumerate(self.servers):
                pane = TerminalPane(server, i, id=f"pane_{i}")
                self.panes.append(pane)
                
                with Container(id=f"container_{i}"):
                    yield Label(f" {server.name} ({server.host}) ", classes="pane-title")
                    yield pane
            
            with Container(id="input_container"):
                yield Input(
                    placeholder="명령어 입력 (Enter로 전송, Ctrl+C로 종료)",
                    id="command_input"
                )
            
            yield Footer()
        
        async def on_input_submitted(self, event: Input.Submitted) -> None:
            """명령어 입력 처리"""
            command = event.value + "\n"
            event.input.clear()
            
            if self.sync_mode:
                # 모든 패인에 명령 전송
                for pane in self.panes:
                    pane.send_input(command)
            else:
                # 현재 포커스된 패인에만 전송 (추후 구현)
                for pane in self.panes:
                    pane.send_input(command)
        
        def action_toggle_sync(self) -> None:
            """동기화 모드 토글"""
            self.sync_mode = not self.sync_mode
            status = "ON" if self.sync_mode else "OFF"
            self.notify(f"동기화 입력: {status}")
        
        def action_quit(self) -> None:
            """종료"""
            for pane in self.panes:
                pane.disconnect()
            self.exit()


def launch_multi_terminal(servers: list[Server], prefer_tmux: bool = True) -> bool:
    """
    멀티 터미널 실행
    
    Args:
        servers: SSH 접속할 서버 목록
        prefer_tmux: True면 리눅스에서 tmux 우선 사용
        
    Returns:
        실행 성공 여부
    """
    if not servers:
        print("연결할 서버가 없습니다.")
        return False
    
    # 리눅스에서 tmux 사용 가능하면 tmux 우선
    if prefer_tmux and os.name != 'nt' and is_tmux_available():
        print(f"tmux로 {len(servers)}개 서버에 연결합니다...")
        print("동기화 입력이 켜져 있습니다. (Ctrl+B 후 :set synchronize-panes off 로 끄기)")
        time.sleep(1)
        
        tmux = TmuxMultiTerminal()
        return tmux.launch(servers, sync_input=True)
    
    # 윈도우거나 tmux 없으면 textual 사용
    if TEXTUAL_AVAILABLE:
        print(f"분할 화면으로 {len(servers)}개 서버에 연결합니다...")
        app = MultiTerminalApp(servers)
        app.run()
        return True
    
    print("textual 라이브러리가 설치되어 있지 않습니다.")
    print("설치: pip install textual")
    return False


def check_dependencies() -> dict:
    """의존성 확인"""
    return {
        'tmux': is_tmux_available(),
        'sshpass': shutil.which('sshpass') is not None,
        'textual': TEXTUAL_AVAILABLE,
    }

