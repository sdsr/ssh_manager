"""
서버 정보 관리 모듈 - SSH 서버 정보를 암호화하여 저장/관리

데이터 구조:
- JSON 형식으로 저장
- 비밀번호만 암호화, 나머지는 평문 (검색 용이)
- 서버별 그룹 지원

저장 파일 구조 예시:
{
    "version": 1,
    "verification": "encrypted_test_string",  # 마스터 비밀번호 검증용
    "servers": [
        {
            "id": "uuid",
            "name": "웹서버1",
            "host": "192.168.1.10",
            "port": 22,
            "username": "admin",
            "password": "encrypted_password",
            "group": "production",
            "description": "메인 웹서버"
        }
    ]
}
"""

import json
import uuid
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from .crypto import CryptoManager


@dataclass
class Server:
    """SSH 서버 정보를 담는 데이터 클래스"""
    
    host: str                           # IP 주소 또는 호스트명
    username: str                       # SSH 사용자 이름
    password: str                       # SSH 비밀번호 (메모리에서는 평문)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""                      # 서버 별칭 (표시용)
    port: int = 22                      # SSH 포트
    group: str = "default"              # 서버 그룹
    description: str = ""               # 서버 설명
    
    def __post_init__(self):
        """이름이 없으면 호스트를 이름으로 사용"""
        if not self.name:
            self.name = self.host
    
    def to_dict(self, include_password: bool = True) -> dict:
        """
        딕셔너리로 변환
        
        Args:
            include_password: 비밀번호 포함 여부
        """
        data = asdict(self)
        if not include_password:
            data.pop('password', None)
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Server':
        """딕셔너리에서 Server 객체 생성"""
        return cls(**data)
    
    def __str__(self) -> str:
        return f"{self.name} ({self.username}@{self.host}:{self.port})"


def get_app_directory() -> Path:
    """
    실행 파일과 같은 디렉토리 반환 (휴대용)
    
    PyInstaller로 빌드된 경우: exe 파일 위치
    일반 Python 실행: 스크립트 위치
    """
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstaller로 빌드된 exe 실행 시
        return Path(sys.executable).parent
    else:
        # 일반 Python 스크립트 실행 시
        return Path(__file__).parent.parent


class ServerManager:
    """서버 목록을 암호화하여 관리하는 클래스"""
    
    CONFIG_VERSION = 1
    VERIFICATION_TEXT = "ssh_manager_verification_string"
    
    def __init__(self, config_dir: Path = None):
        """
        Args:
            config_dir: 설정 파일 저장 디렉토리 (기본: exe와 같은 폴더의 .ssh_manager)
        """
        if config_dir is None:
            # exe 파일과 같은 디렉토리에 저장 (휴대용)
            config_dir = get_app_directory() / ".ssh_manager"
        
        self.config_dir = Path(config_dir)
        self.servers_file = self.config_dir / "servers.json"
        self.crypto = CryptoManager(self.config_dir)
        self._servers: list[Server] = []
        self._loaded = False
    
    def initialize(self, master_password: str, is_new: bool = False) -> bool:
        """
        마스터 비밀번호로 초기화
        
        Args:
            master_password: 마스터 비밀번호
            is_new: 새로운 설정 생성 여부
            
        Returns:
            초기화 성공 여부
        """
        if not self.crypto.initialize(master_password):
            return False
        
        if is_new:
            # 새로운 설정 파일 생성
            self._servers = []
            self._save()
            return True
        
        # 기존 설정 로드 및 비밀번호 검증
        return self._load()
    
    def is_first_run(self) -> bool:
        """처음 실행 여부"""
        return not self.servers_file.exists()
    
    def _load(self) -> bool:
        """
        서버 목록 로드 및 복호화
        
        Returns:
            로드 성공 여부 (마스터 비밀번호 검증 포함)
        """
        if not self.servers_file.exists():
            self._servers = []
            self._loaded = True
            return True
        
        try:
            with open(self.servers_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 마스터 비밀번호 검증
            verification = data.get('verification', '')
            if verification:
                decrypted = self.crypto.decrypt(verification)
                if decrypted != self.VERIFICATION_TEXT:
                    return False
            
            # 서버 목록 로드 및 비밀번호 복호화
            self._servers = []
            for server_data in data.get('servers', []):
                # 비밀번호 복호화
                if 'password' in server_data and server_data['password']:
                    server_data['password'] = self.crypto.decrypt(server_data['password'])
                
                self._servers.append(Server.from_dict(server_data))
            
            self._loaded = True
            return True
            
        except (json.JSONDecodeError, ValueError, KeyError):
            return False
    
    def _save(self) -> None:
        """서버 목록을 암호화하여 저장"""
        if not self.crypto.is_initialized:
            raise RuntimeError("암호화 시스템이 초기화되지 않았습니다.")
        
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 비밀번호 암호화
        servers_data = []
        for server in self._servers:
            data = server.to_dict()
            if data['password']:
                data['password'] = self.crypto.encrypt(data['password'])
            servers_data.append(data)
        
        config = {
            'version': self.CONFIG_VERSION,
            'verification': self.crypto.encrypt(self.VERIFICATION_TEXT),
            'servers': servers_data
        }
        
        with open(self.servers_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # 파일 권한 제한 (소유자만 읽기/쓰기)
        self.servers_file.chmod(0o600)
    
    def add_server(self, server: Server) -> None:
        """서버 추가"""
        self._servers.append(server)
        self._save()
    
    def remove_server(self, server_id: str) -> bool:
        """
        서버 삭제
        
        Args:
            server_id: 삭제할 서버 ID
            
        Returns:
            삭제 성공 여부
        """
        for i, server in enumerate(self._servers):
            if server.id == server_id:
                del self._servers[i]
                self._save()
                return True
        return False
    
    def update_server(self, server_id: str, **kwargs) -> bool:
        """
        서버 정보 수정
        
        Args:
            server_id: 수정할 서버 ID
            **kwargs: 수정할 필드들
            
        Returns:
            수정 성공 여부
        """
        for server in self._servers:
            if server.id == server_id:
                for key, value in kwargs.items():
                    if hasattr(server, key):
                        setattr(server, key, value)
                self._save()
                return True
        return False
    
    def get_server(self, server_id: str) -> Optional[Server]:
        """ID로 서버 조회"""
        for server in self._servers:
            if server.id == server_id:
                return server
        return None
    
    def get_server_by_name(self, name: str) -> Optional[Server]:
        """이름으로 서버 조회"""
        for server in self._servers:
            if server.name == name:
                return server
        return None
    
    def list_servers(self, group: str = None) -> list[Server]:
        """
        서버 목록 조회
        
        Args:
            group: 필터링할 그룹 (None이면 전체)
        """
        if group is None:
            return list(self._servers)
        return [s for s in self._servers if s.group == group]
    
    def list_groups(self) -> list[str]:
        """그룹 목록 조회"""
        groups = set(s.group for s in self._servers)
        return sorted(groups)
    
    def search_servers(self, query: str) -> list[Server]:
        """
        서버 검색 (이름, 호스트, 설명에서 검색)
        
        Args:
            query: 검색어
        """
        query = query.lower()
        results = []
        for server in self._servers:
            if (query in server.name.lower() or 
                query in server.host.lower() or 
                query in server.description.lower()):
                results.append(server)
        return results
    
    @property
    def server_count(self) -> int:
        """등록된 서버 수"""
        return len(self._servers)

