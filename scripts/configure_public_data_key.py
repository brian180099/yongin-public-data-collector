"""Paste a portal decoding key into the collector-only ignored environment file."""

import getpass
import os
from pathlib import Path

from dotenv import dotenv_values, set_key

from yongin_collector.store import ROOT


def save_key(value: str, runtime_dir: Path) -> None:
    key = value.strip()
    if len(key) < 20 or any(character.isspace() for character in key):
        raise ValueError("invalid key format; use the portal's decoding key")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    env_path = runtime_dir / "collector.env"
    if not env_path.exists():
        env_path.write_text("", encoding="utf-8")
    set_key(str(env_path), "DATA_GO_KR_SERVICE_KEY", key)
    if os.name != "nt":
        env_path.chmod(0o600)


def main() -> int:
    runtime_dir = ROOT / ".runtime"
    env_path = runtime_dir / "collector.env"
    current = dotenv_values(env_path) if env_path.exists() else {}
    print("현재 인증키 설정:", "있음" if current.get("DATA_GO_KR_SERVICE_KEY") else "없음")
    key = getpass.getpass("공공데이터포털 디코딩 인증키 붙여넣기 (화면에 표시되지 않음): ")
    try:
        save_key(key, runtime_dir)
    except ValueError as exc:
        print(str(exc))
        return 1
    print("수집 서비스 전용 비밀 파일에 저장했습니다. 적용하려면 수집 컨테이너를 다시 만드세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
