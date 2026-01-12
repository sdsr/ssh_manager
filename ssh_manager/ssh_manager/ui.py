"""
TUI (Terminal User Interface) 모듈 - rich 라이브러리 기반 터미널 UI

구현 방식:
- rich 라이브러리로 테이블, 패널, 프로그레스바 등 표시
- 메뉴 기반 인터페이스
- 컬러풀한 출력으로 가독성 향상

rich 라이브러리 장점:
- 설치 간편 (순수 Python)
- 아름다운 출력 (마크업 지원)
- 테이블, 트리, 패널 등 다양한 위젯
- 프로그레스바, 스피너 지원
"""

import os
import sys
import time
import getpass
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich import box

from .server import Server, ServerManager
from .ssh_client import MultiSSHManager, CommandResult, SSHConnection
from .file_transfer import MultiFileTransfer, TransferResult, TransferProgress, format_size, format_speed
from .multi_terminal import launch_multi_terminal, check_dependencies, is_tmux_available, TEXTUAL_AVAILABLE


# 콘솔 인스턴스 (전역)
console = Console()


def clear_screen():
    """화면 지우기"""
    os.system('clear' if os.name != 'nt' else 'cls')


def print_header():
    """헤더 출력"""
    header = Panel(
        Text("SSH Manager v1.0", style="bold cyan", justify="center"),
        subtitle="Multi-Server SSH Management Tool",
        box=box.DOUBLE
    )
    console.print(header)
    console.print()


def print_menu(title: str, options: list[tuple[str, str]]) -> str:
    """
    메뉴 출력 및 선택 받기
    
    Args:
        title: 메뉴 제목
        options: (키, 설명) 튜플 리스트
        
    Returns:
        선택된 키
    """
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=False,
        padding=(0, 2)
    )
    table.add_column("Key", style="bold yellow", width=8)
    table.add_column("Description", style="white")
    
    for key, desc in options:
        # rich 마크업 이스케이프: [b]는 bold로 해석되므로 \[ 사용
        table.add_row(f"\\[{key}]", desc)
    
    console.print(table)
    console.print()
    
    valid_keys = [opt[0].lower() for opt in options]
    while True:
        choice = Prompt.ask("선택", default="q").lower().strip()
        if choice in valid_keys:
            return choice
        console.print("[red]잘못된 선택입니다. 다시 입력하세요.[/red]")


def print_servers_table(servers: list[Server], show_index: bool = False, title: str = "서버 목록"):
    """서버 목록 테이블 출력"""
    if not servers:
        console.print(Panel("[yellow]등록된 서버가 없습니다.[/yellow]", title=title))
        return
    
    table = Table(title=title, box=box.ROUNDED)
    
    if show_index:
        table.add_column("#", style="dim", width=4)
    table.add_column("이름", style="cyan", no_wrap=True)
    table.add_column("호스트", style="green")
    table.add_column("포트", style="yellow", justify="right")
    table.add_column("사용자", style="blue")
    table.add_column("그룹", style="magenta")
    table.add_column("설명", style="dim")
    
    for i, server in enumerate(servers, 1):
        row = []
        if show_index:
            row.append(str(i))
        row.extend([
            server.name,
            server.host,
            str(server.port),
            server.username,
            server.group,
            server.description[:30] + "..." if len(server.description) > 30 else server.description
        ])
        table.add_row(*row)
    
    console.print(table)


def print_command_results(results: list[CommandResult]):
    """명령 실행 결과 출력"""
    for result in results:
        if result.success:
            status = "[green]SUCCESS[/green]"
        else:
            status = "[red]FAILED[/red]"
        
        title = f"{result.server.name} ({result.server.host}) - {status}"
        
        content = []
        if result.stdout:
            content.append(result.stdout.rstrip())
        if result.stderr:
            content.append(f"[red]{result.stderr.rstrip()}[/red]")
        if result.error_message:
            content.append(f"[red]Error: {result.error_message}[/red]")
        
        if not content:
            content.append("[dim](출력 없음)[/dim]")
        
        panel = Panel(
            "\n".join(content),
            title=title,
            title_align="left",
            border_style="green" if result.success else "red",
            box=box.ROUNDED
        )
        console.print(panel)
        console.print()


def print_transfer_results(results: list[TransferResult]):
    """파일 전송 결과 출력"""
    table = Table(title="전송 결과", box=box.ROUNDED)
    table.add_column("서버", style="cyan")
    table.add_column("상태", justify="center")
    table.add_column("크기", justify="right")
    table.add_column("속도", justify="right")
    table.add_column("메시지")
    
    for result in results:
        if result.success:
            status = "[green]성공[/green]"
            message = ""
        else:
            status = "[red]실패[/red]"
            message = result.error_message[:40]
        
        table.add_row(
            f"{result.server.name}",
            status,
            format_size(result.transferred_bytes),
            format_speed(result.speed),
            message
        )
    
    console.print(table)


class SSHManagerUI:
    """SSH Manager 메인 UI 클래스"""
    
    def __init__(self):
        self.server_manager: Optional[ServerManager] = None
        self.ssh_manager = MultiSSHManager()
        self.file_transfer = MultiFileTransfer()
        self._running = True
    
    def run(self):
        """메인 루프 실행"""
        clear_screen()
        print_header()
        
        # 마스터 비밀번호 입력 및 초기화
        if not self._initialize():
            return
        
        # 메인 메뉴 루프
        while self._running:
            self._main_menu()
        
        # 정리
        self.ssh_manager.disconnect_all()
        console.print("\n[cyan]SSH Manager를 종료합니다. 안녕히 가세요![/cyan]\n")
    
    def _initialize(self) -> bool:
        """초기화 (마스터 비밀번호 설정/입력)"""
        self.server_manager = ServerManager()
        
        if self.server_manager.is_first_run():
            console.print(Panel(
                "[yellow]처음 실행입니다. 마스터 비밀번호를 설정하세요.[/yellow]\n"
                "이 비밀번호는 서버 정보를 암호화하는 데 사용됩니다.\n"
                "[red]비밀번호를 잊으면 저장된 서버 정보를 복구할 수 없습니다![/red]",
                title="초기 설정"
            ))
            
            while True:
                password = getpass.getpass("마스터 비밀번호 설정: ")
                if len(password) < 4:
                    console.print("[red]비밀번호는 4자 이상이어야 합니다.[/red]")
                    continue
                
                password_confirm = getpass.getpass("비밀번호 확인: ")
                if password != password_confirm:
                    console.print("[red]비밀번호가 일치하지 않습니다.[/red]")
                    continue
                
                break
            
            if self.server_manager.initialize(password, is_new=True):
                console.print("[green]마스터 비밀번호가 설정되었습니다.[/green]\n")
                return True
            else:
                console.print("[red]초기화에 실패했습니다.[/red]")
                return False
        else:
            # 기존 비밀번호 입력
            for attempt in range(3):
                password = getpass.getpass("마스터 비밀번호: ")
                
                if self.server_manager.initialize(password):
                    console.print("[green]로그인 성공![/green]\n")
                    return True
                
                remaining = 2 - attempt
                if remaining > 0:
                    console.print(f"[red]비밀번호가 틀렸습니다. 남은 시도: {remaining}[/red]")
            
            console.print("[red]비밀번호 시도 횟수 초과. 프로그램을 종료합니다.[/red]")
            return False
    
    def _main_menu(self):
        """메인 메뉴"""
        clear_screen()
        print_header()
        
        # 현재 상태 표시
        server_count = self.server_manager.server_count
        connected_count = self.ssh_manager.connection_count
        
        status = f"등록 서버: [cyan]{server_count}[/cyan] | 연결됨: [green]{connected_count}[/green]"
        console.print(Panel(status, title="상태"))
        console.print()
        
        options = [
            ("1", "서버 관리 (추가/수정/삭제)"),
            ("2", "서버 목록 보기"),
            ("3", "서버 연결 (명령 브로드캐스트용)"),
            ("4", "명령 실행 (연결된 서버에)"),
            ("5", "파일 전송 (연결된 서버에)"),
            ("6", "연결 해제"),
            ("7", "멀티 터미널 (분할 화면)"),
            ("q", "종료"),
        ]
        
        choice = print_menu("메인 메뉴", options)
        
        if choice == "1":
            self._server_management_menu()
        elif choice == "2":
            self._view_servers()
        elif choice == "3":
            self._connect_servers()
        elif choice == "4":
            self._execute_command()
        elif choice == "5":
            self._file_transfer_menu()
        elif choice == "6":
            self._disconnect_servers()
        elif choice == "7":
            self._multi_terminal()
        elif choice == "q":
            if Confirm.ask("정말 종료하시겠습니까?"):
                self._running = False
    
    def _server_management_menu(self):
        """서버 관리 메뉴"""
        while True:
            clear_screen()
            print_header()
            
            options = [
                ("1", "서버 추가"),
                ("2", "서버 수정"),
                ("3", "서버 삭제"),
                ("b", "뒤로 가기"),
            ]
            
            choice = print_menu("서버 관리", options)
            
            if choice == "1":
                self._add_server()
            elif choice == "2":
                self._edit_server()
            elif choice == "3":
                self._delete_server()
            elif choice == "b":
                break
    
    def _add_server(self):
        """서버 추가"""
        console.print(Panel("새 서버 정보를 입력하세요", title="서버 추가"))
        
        try:
            name = Prompt.ask("서버 이름 (별칭)")
            host = Prompt.ask("호스트 (IP 또는 도메인)")
            port = IntPrompt.ask("SSH 포트", default=22)
            username = Prompt.ask("사용자 이름")
            password = getpass.getpass("비밀번호: ")
            group = Prompt.ask("그룹", default="default")
            description = Prompt.ask("설명 (선택)", default="")
            
            server = Server(
                name=name,
                host=host,
                port=port,
                username=username,
                password=password,
                group=group,
                description=description
            )
            
            self.server_manager.add_server(server)
            console.print(f"\n[green]서버 '{name}'이(가) 추가되었습니다.[/green]")
            
        except KeyboardInterrupt:
            console.print("\n[yellow]취소되었습니다.[/yellow]")
        
        Prompt.ask("\n계속하려면 Enter를 누르세요")
    
    def _edit_server(self):
        """서버 수정"""
        servers = self.server_manager.list_servers()
        if not servers:
            console.print("[yellow]등록된 서버가 없습니다.[/yellow]")
            Prompt.ask("\n계속하려면 Enter를 누르세요")
            return
        
        print_servers_table(servers, show_index=True, title="수정할 서버 선택")
        
        try:
            idx = IntPrompt.ask("서버 번호 (0: 취소)", default=0)
            if idx == 0 or idx > len(servers):
                return
            
            server = servers[idx - 1]
            console.print(f"\n[cyan]'{server.name}' 수정 (Enter로 기존 값 유지)[/cyan]\n")
            
            name = Prompt.ask("서버 이름", default=server.name)
            host = Prompt.ask("호스트", default=server.host)
            port = IntPrompt.ask("SSH 포트", default=server.port)
            username = Prompt.ask("사용자 이름", default=server.username)
            
            change_password = Confirm.ask("비밀번호 변경?", default=False)
            password = getpass.getpass("새 비밀번호: ") if change_password else server.password
            
            group = Prompt.ask("그룹", default=server.group)
            description = Prompt.ask("설명", default=server.description)
            
            self.server_manager.update_server(
                server.id,
                name=name,
                host=host,
                port=port,
                username=username,
                password=password,
                group=group,
                description=description
            )
            
            console.print(f"\n[green]서버 정보가 수정되었습니다.[/green]")
            
        except (KeyboardInterrupt, ValueError):
            console.print("\n[yellow]취소되었습니다.[/yellow]")
        
        Prompt.ask("\n계속하려면 Enter를 누르세요")
    
    def _delete_server(self):
        """서버 삭제"""
        servers = self.server_manager.list_servers()
        if not servers:
            console.print("[yellow]등록된 서버가 없습니다.[/yellow]")
            Prompt.ask("\n계속하려면 Enter를 누르세요")
            return
        
        print_servers_table(servers, show_index=True, title="삭제할 서버 선택")
        
        try:
            idx = IntPrompt.ask("서버 번호 (0: 취소)", default=0)
            if idx == 0 or idx > len(servers):
                return
            
            server = servers[idx - 1]
            
            if Confirm.ask(f"[red]정말 '{server.name}'을(를) 삭제하시겠습니까?[/red]"):
                # 연결되어 있으면 먼저 연결 해제
                self.ssh_manager.remove_connection(server.id)
                self.server_manager.remove_server(server.id)
                console.print(f"\n[green]서버 '{server.name}'이(가) 삭제되었습니다.[/green]")
            
        except (KeyboardInterrupt, ValueError):
            console.print("\n[yellow]취소되었습니다.[/yellow]")
        
        Prompt.ask("\n계속하려면 Enter를 누르세요")
    
    def _view_servers(self):
        """서버 목록 보기"""
        clear_screen()
        print_header()
        
        servers = self.server_manager.list_servers()
        print_servers_table(servers)
        
        # 그룹별 통계
        if servers:
            groups = self.server_manager.list_groups()
            console.print(f"\n그룹: {', '.join(groups)}")
        
        Prompt.ask("\n계속하려면 Enter를 누르세요")
    
    def _connect_servers(self):
        """서버 연결"""
        servers = self.server_manager.list_servers()
        if not servers:
            console.print("[yellow]등록된 서버가 없습니다.[/yellow]")
            Prompt.ask("\n계속하려면 Enter를 누르세요")
            return
        
        clear_screen()
        print_header()
        print_servers_table(servers, show_index=True, title="연결할 서버 선택")
        
        console.print("\n[dim]여러 서버: 번호를 쉼표로 구분 (예: 1,2,3)[/dim]")
        console.print("[dim]전체 서버: 'all' 입력[/dim]")
        
        try:
            selection = Prompt.ask("연결할 서버", default="").strip()
            
            if not selection:
                return
            
            if selection.lower() == "all":
                selected_servers = servers
            else:
                indices = [int(x.strip()) - 1 for x in selection.split(",")]
                selected_servers = [servers[i] for i in indices if 0 <= i < len(servers)]
            
            if not selected_servers:
                console.print("[red]선택된 서버가 없습니다.[/red]")
                Prompt.ask("\n계속하려면 Enter를 누르세요")
                return
            
            # 연결 시도
            console.print()
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console
            ) as progress:
                task = progress.add_task("서버 연결 중...", total=len(selected_servers))
                
                for server in selected_servers:
                    progress.update(task, description=f"연결 중: {server.name}")
                    success, error = self.ssh_manager.add_connection(server)
                    
                    if success:
                        console.print(f"  [green]V[/green] {server.name}: 연결됨")
                    else:
                        console.print(f"  [red]X[/red] {server.name}: {error}")
                    
                    progress.advance(task)
            
            connected = self.ssh_manager.connection_count
            console.print(f"\n[cyan]연결된 서버: {connected}개[/cyan]")
            
        except (KeyboardInterrupt, ValueError) as e:
            console.print(f"\n[yellow]취소되었습니다: {e}[/yellow]")
        
        Prompt.ask("\n계속하려면 Enter를 누르세요")
    
    def _disconnect_servers(self):
        """서버 연결 해제"""
        connected = self.ssh_manager.connected_servers
        if not connected:
            console.print("[yellow]연결된 서버가 없습니다.[/yellow]")
            Prompt.ask("\n계속하려면 Enter를 누르세요")
            return
        
        clear_screen()
        print_header()
        print_servers_table(connected, show_index=True, title="연결된 서버")
        
        if Confirm.ask("\n모든 서버 연결을 해제하시겠습니까?"):
            self.ssh_manager.disconnect_all()
            console.print("[green]모든 연결이 해제되었습니다.[/green]")
        
        Prompt.ask("\n계속하려면 Enter를 누르세요")
    
    def _execute_command(self):
        """명령 실행"""
        connected = self.ssh_manager.connected_servers
        if not connected:
            console.print("[yellow]연결된 서버가 없습니다. 먼저 서버에 연결하세요.[/yellow]")
            Prompt.ask("\n계속하려면 Enter를 누르세요")
            return
        
        clear_screen()
        print_header()
        print_servers_table(connected, show_index=True, title="연결된 서버")
        
        console.print("\n[dim]선택한 서버에 명령을 실행합니다.[/dim]")
        console.print("[dim]여러 서버: 번호를 쉼표로 구분 / 전체: 'all'[/dim]")
        
        try:
            selection = Prompt.ask("대상 서버", default="all").strip()
            
            if selection.lower() == "all":
                selected_ids = [s.id for s in connected]
            else:
                indices = [int(x.strip()) - 1 for x in selection.split(",")]
                selected_ids = [connected[i].id for i in indices if 0 <= i < len(connected)]
            
            if not selected_ids:
                console.print("[red]선택된 서버가 없습니다.[/red]")
                Prompt.ask("\n계속하려면 Enter를 누르세요")
                return
            
            # 명령 실행 루프 (readline으로 히스토리/자동완성 지원)
            console.print("\n[cyan]명령어를 입력하세요. 종료하려면 'exit' 또는 빈 줄 입력[/cyan]")
            console.print("[dim]화살표 위/아래: 이전 명령, Ctrl+C: 취소[/dim]")
            
            # readline 설정 (히스토리, 자동완성)
            try:
                import readline
                readline.parse_and_bind('tab: complete')
                readline.parse_and_bind('set editing-mode emacs')
            except ImportError:
                pass  # Windows에서는 readline이 없을 수 있음
            
            while True:
                try:
                    console.print()
                    command = input("\033[1;33m$ \033[0m").strip()
                    
                    if not command or command.lower() == "exit":
                        break
                    
                    console.print()
                    with console.status("[bold green]실행 중...[/bold green]"):
                        results = self.ssh_manager.execute_on_selected(
                            selected_ids, 
                            command,
                            timeout=60
                        )
                    
                    print_command_results(results)
                except EOFError:
                    break
            
        except KeyboardInterrupt:
            console.print("\n[yellow]취소되었습니다.[/yellow]")
        
        Prompt.ask("\n계속하려면 Enter를 누르세요")
    
    def _file_transfer_menu(self):
        """파일 전송 메뉴"""
        connected = self.ssh_manager.connected_servers
        if not connected:
            console.print("[yellow]연결된 서버가 없습니다. 먼저 서버에 연결하세요.[/yellow]")
            Prompt.ask("\n계속하려면 Enter를 누르세요")
            return
        
        clear_screen()
        print_header()
        print_servers_table(connected, show_index=True, title="연결된 서버")
        
        options = [
            ("1", "파일 업로드 (로컬 -> 원격)"),
            ("2", "파일 다운로드 (원격 -> 로컬)"),
            ("b", "뒤로 가기"),
        ]
        
        choice = print_menu("파일 전송", options)
        
        if choice == "1":
            self._upload_file(connected)
        elif choice == "2":
            self._download_file(connected)
    
    def _upload_file(self, servers: list[Server]):
        """파일 업로드"""
        console.print("\n[dim]여러 서버: 번호를 쉼표로 구분 / 전체: 'all'[/dim]")
        
        try:
            selection = Prompt.ask("대상 서버", default="all").strip()
            
            if selection.lower() == "all":
                selected_servers = servers
            else:
                indices = [int(x.strip()) - 1 for x in selection.split(",")]
                selected_servers = [servers[i] for i in indices if 0 <= i < len(servers)]
            
            if not selected_servers:
                console.print("[red]선택된 서버가 없습니다.[/red]")
                return
            
            local_path = Prompt.ask("로컬 파일 경로")
            remote_path = Prompt.ask("원격 저장 경로")
            
            console.print(f"\n[cyan]{len(selected_servers)}개 서버에 파일 전송 시작...[/cyan]\n")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console
            ) as progress:
                task = progress.add_task("전송 중...", total=len(selected_servers))
                
                def on_result(result: TransferResult):
                    status = "[green]성공[/green]" if result.success else f"[red]실패: {result.error_message}[/red]"
                    console.print(f"  {result.server.name}: {status}")
                    progress.advance(task)
                
                results = self.file_transfer.upload_to_servers(
                    selected_servers,
                    local_path,
                    remote_path,
                    result_callback=on_result
                )
            
            console.print()
            print_transfer_results(results)
            
        except (KeyboardInterrupt, ValueError):
            console.print("\n[yellow]취소되었습니다.[/yellow]")
        
        Prompt.ask("\n계속하려면 Enter를 누르세요")
    
    def _download_file(self, servers: list[Server]):
        """파일 다운로드"""
        print_servers_table(servers, show_index=True)
        
        try:
            idx = IntPrompt.ask("다운로드할 서버 번호", default=1)
            if idx < 1 or idx > len(servers):
                console.print("[red]잘못된 번호입니다.[/red]")
                return
            
            server = servers[idx - 1]
            
            remote_path = Prompt.ask("원격 파일 경로")
            local_path = Prompt.ask("로컬 저장 경로")
            
            console.print(f"\n[cyan]{server.name}에서 파일 다운로드 중...[/cyan]\n")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console
            ) as progress:
                task = progress.add_task("다운로드 중...", total=100)
                
                def on_progress(p: TransferProgress):
                    progress.update(task, completed=p.percentage)
                
                result = self.file_transfer.download_from_server(
                    server,
                    remote_path,
                    local_path,
                    progress_callback=on_progress
                )
            
            if result.success:
                console.print(f"\n[green]다운로드 완료![/green]")
                console.print(f"크기: {format_size(result.transferred_bytes)}")
                console.print(f"속도: {format_speed(result.speed)}")
            else:
                console.print(f"\n[red]다운로드 실패: {result.error_message}[/red]")
            
        except (KeyboardInterrupt, ValueError):
            console.print("\n[yellow]취소되었습니다.[/yellow]")
        
        Prompt.ask("\n계속하려면 Enter를 누르세요")
    
    def _multi_terminal(self):
        """멀티 터미널 (분할 화면) - 여러 SSH 세션을 동시에 표시"""
        servers = self.server_manager.list_servers()
        if not servers:
            console.print("[yellow]등록된 서버가 없습니다.[/yellow]")
            Prompt.ask("\n계속하려면 Enter를 누르세요")
            return
        
        clear_screen()
        print_header()
        
        # 의존성 상태 표시
        deps = check_dependencies()
        console.print(Panel(
            f"tmux: {'[green]사용 가능[/green]' if deps['tmux'] else '[red]없음[/red]'} | "
            f"sshpass: {'[green]있음[/green]' if deps['sshpass'] else '[yellow]없음 (수동 비밀번호)[/yellow]'} | "
            f"textual: {'[green]사용 가능[/green]' if deps['textual'] else '[red]없음[/red]'}",
            title="환경"
        ))
        console.print()
        
        print_servers_table(servers, show_index=True, title="멀티 터미널로 연결할 서버 선택")
        
        console.print("\n[dim]여러 서버: 번호를 쉼표로 구분 (예: 1,2,3)[/dim]")
        console.print("[dim]전체 서버: 'all' 입력[/dim]")
        
        try:
            selection = Prompt.ask("연결할 서버", default="").strip()
            
            if not selection:
                return
            
            if selection.lower() == "all":
                selected_servers = servers
            else:
                indices = [int(x.strip()) - 1 for x in selection.split(",")]
                selected_servers = [servers[i] for i in indices if 0 <= i < len(servers)]
            
            if not selected_servers:
                console.print("[red]선택된 서버가 없습니다.[/red]")
                Prompt.ask("\n계속하려면 Enter를 누르세요")
                return
            
            if len(selected_servers) > 9:
                console.print("[yellow]최대 9개 서버까지 분할 화면 지원됩니다.[/yellow]")
                selected_servers = selected_servers[:9]
            
            console.print(f"\n[cyan]{len(selected_servers)}개 서버에 분할 화면으로 연결합니다...[/cyan]")
            
            # 리눅스에서 tmux 사용 가능하면 안내
            import os
            if os.name != 'nt' and deps['tmux']:
                console.print("[dim]tmux 사용 - 동기화 입력 ON (모든 창에 동시 입력)[/dim]")
                console.print("[dim]동기화 끄기: Ctrl+B 후 :setw synchronize-panes off[/dim]")
            elif deps['textual']:
                console.print("[dim]textual TUI 사용 - Enter로 명령 전송, Ctrl+C로 종료[/dim]")
            
            time.sleep(1)
            
            # 멀티 터미널 실행
            # tmux 사용 시 이 함수는 반환되지 않음 (exec로 대체됨)
            success = launch_multi_terminal(selected_servers, prefer_tmux=True)
            
            if not success:
                console.print("[red]멀티 터미널 실행 실패[/red]")
                Prompt.ask("\n계속하려면 Enter를 누르세요")
            
        except (KeyboardInterrupt, ValueError) as e:
            console.print(f"\n[yellow]취소되었습니다: {e}[/yellow]")
            Prompt.ask("\n계속하려면 Enter를 누르세요")


def main():
    """메인 진입점"""
    try:
        ui = SSHManagerUI()
        ui.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]프로그램이 중단되었습니다.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]오류 발생: {e}[/red]")
        sys.exit(1)

