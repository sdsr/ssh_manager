"""
암호화 모듈 - 서버 비밀번호를 안전하게 저장하기 위한 암호화/복호화 기능

사용 방식:
- Fernet 대칭키 암호화 사용 (AES-128-CBC)
- 마스터 비밀번호에서 키 파생 (PBKDF2HMAC)
- 솔트를 사용하여 레인보우 테이블 공격 방지

장점:
- 강력한 암호화 (산업 표준 AES)
- 마스터 비밀번호만 기억하면 됨
- 솔트로 동일 비밀번호도 다른 암호문 생성

단점:
- 마스터 비밀번호 분실 시 복구 불가
- 메모리에 복호화된 비밀번호가 잠시 존재
"""

import os
import base64
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CryptoManager:
    """비밀번호 암호화/복호화 관리 클래스"""
    
    # 키 파생에 사용할 반복 횟수 (높을수록 무차별 대입 공격에 강함)
    ITERATIONS = 480000
    
    def __init__(self, config_dir: Path):
        """
        Args:
            config_dir: 설정 파일이 저장될 디렉토리 경로
        """
        self.config_dir = config_dir
        self.salt_file = config_dir / ".salt"
        self._fernet = None
        
    def _get_or_create_salt(self) -> bytes:
        """
        솔트를 파일에서 읽거나 새로 생성
        
        솔트(Salt)란?
        - 비밀번호에 추가되는 무작위 데이터
        - 같은 비밀번호도 다른 솔트와 결합하면 다른 키가 생성됨
        - 사전 계산된 해시 테이블(레인보우 테이블) 공격 방지
        """
        if self.salt_file.exists():
            return self.salt_file.read_bytes()
        
        # 16바이트(128비트) 무작위 솔트 생성
        salt = os.urandom(16)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.salt_file.write_bytes(salt)
        
        # 솔트 파일 권한을 소유자만 읽기/쓰기로 제한 (보안)
        self.salt_file.chmod(0o600)
        return salt
    
    def _derive_key(self, master_password: str) -> bytes:
        """
        마스터 비밀번호에서 암호화 키 파생
        
        PBKDF2 (Password-Based Key Derivation Function 2):
        - 비밀번호를 암호화 키로 변환하는 표준 알고리즘
        - 반복 횟수가 많아 무차별 대입 공격 시간 증가
        - SHA256 해시 함수 사용
        
        Args:
            master_password: 사용자가 입력한 마스터 비밀번호
            
        Returns:
            32바이트 암호화 키 (base64 인코딩됨)
        """
        salt = self._get_or_create_salt()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # Fernet은 32바이트 키 필요
            salt=salt,
            iterations=self.ITERATIONS,
        )
        
        # Fernet은 base64로 인코딩된 키 필요
        key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
        return key
    
    def initialize(self, master_password: str) -> bool:
        """
        마스터 비밀번호로 암호화 시스템 초기화
        
        Args:
            master_password: 마스터 비밀번호
            
        Returns:
            초기화 성공 여부
        """
        try:
            key = self._derive_key(master_password)
            self._fernet = Fernet(key)
            return True
        except Exception:
            return False
    
    def encrypt(self, plaintext: str) -> str:
        """
        문자열 암호화
        
        Fernet 암호화 특징:
        - 타임스탬프 포함 (TTL 검증 가능)
        - HMAC으로 무결성 검증
        - IV(초기화 벡터) 자동 생성
        
        Args:
            plaintext: 암호화할 평문
            
        Returns:
            base64로 인코딩된 암호문
        """
        if not self._fernet:
            raise RuntimeError("암호화 시스템이 초기화되지 않았습니다. initialize()를 먼저 호출하세요.")
        
        encrypted = self._fernet.encrypt(plaintext.encode())
        return encrypted.decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """
        암호문 복호화
        
        Args:
            ciphertext: base64로 인코딩된 암호문
            
        Returns:
            복호화된 평문
            
        Raises:
            InvalidToken: 잘못된 암호문이거나 키가 틀린 경우
        """
        if not self._fernet:
            raise RuntimeError("암호화 시스템이 초기화되지 않았습니다. initialize()를 먼저 호출하세요.")
        
        try:
            decrypted = self._fernet.decrypt(ciphertext.encode())
            return decrypted.decode()
        except InvalidToken:
            raise ValueError("복호화 실패: 마스터 비밀번호가 틀리거나 데이터가 손상되었습니다.")
    
    def verify_password(self, test_data: str = None) -> bool:
        """
        마스터 비밀번호 검증
        
        Args:
            test_data: 테스트용 암호화된 데이터
            
        Returns:
            비밀번호 일치 여부
        """
        if not test_data:
            return self._fernet is not None
        
        try:
            self.decrypt(test_data)
            return True
        except (ValueError, RuntimeError):
            return False
    
    @property
    def is_initialized(self) -> bool:
        """암호화 시스템 초기화 여부"""
        return self._fernet is not None
    
    def is_first_run(self) -> bool:
        """처음 실행 여부 (솔트 파일 존재 확인)"""
        return not self.salt_file.exists()

