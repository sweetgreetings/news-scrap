# Design Ref: 스케줄러 스레드(정기 재생성)와 설정 서버 스레드(숨김/되돌리기 후 재생성)가
# index.html 등 같은 정적 화면 파일에 동시에 쓸 수 있어, 임시 파일에 쓴 뒤 교체하는 방식으로
# 두 쓰기가 겹쳐도 반쪽짜리 파일이 남지 않게 한다.
import threading
from pathlib import Path


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """path에 원자적으로 쓴다 (임시 파일에 쓴 뒤 os.replace 성격의 Path.replace로 교체).

    임시 파일 이름에 스레드 ID를 넣어, 동시에 쓰는 다른 스레드와 임시 파일 자체가
    겹치지 않게 한다.
    """
    tmp_path = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    tmp_path.write_text(text, encoding=encoding)
    tmp_path.replace(path)
