import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator
from .models import AppError


def atomic_write(path: Path, writer) -> None:
    # writer가 새 내용을 완성한 뒤 교체해, 쓰기 도중 오류로부터 기존 파일을 보호한다.
    temporary = None
    try:
        # 같은 파일시스템에서 원자적으로 교체할 수 있도록 같은 폴더에 임시 파일을 만든다.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer(stream)
            # Python 버퍼를 비우고 운영체제에 파일 내용을 저장 장치에 반영하도록 요청한다.
            stream.flush()
            os.fsync(stream.fileno())
        # 완성된 파일로 한 번에 교체한다. 여러 파일의 일괄 갱신이나 동시 쓰기 제어는 하지 않는다.
        os.replace(temporary, path)
    finally:
        # 오류로 남은 임시 파일을 정리한다. 교체 후 이미 없어진 파일은 무시한다.
        if temporary is not None: temporary.unlink(missing_ok=True)


class JsonlRepository:
    """파일 입출력과 단일 파일 원자적 교체를 담당한다."""
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        for name in ('transactions', 'categories', 'budgets'):
            if not self.path(name).exists():
                self.write(name, ({'name': c} for c in ('food', 'transport', 'rent', 'etc', 'salary')) if name == 'categories' else ())

    def path(self, name: str) -> Path:
        return self.directory / (name + '.jsonl')

    def read(self, name: str) -> Iterator[dict[str, Any]]:
        with self.path(name).open(encoding='utf-8') as stream:
            # JSONL은 한 줄에 JSON 객체 하나를 저장하므로 전체 파일 대신 한 줄씩 읽는다.
            for number, line in enumerate(stream, 1):
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict): raise ValueError()
                except ValueError:
                    raise AppError(f'{name}.jsonl {number}행이 손상되었습니다. 백업을 복구하세요.') from None
                # 한 줄의 데이터를 전달하고 다음 값 요청까지 실행을 멈춘다.
                yield row

    def write(self, name: str, rows: Iterable[dict[str, Any]]) -> None:
        def serialize(stream):
            # 각 데이터를 JSON으로 바꿔 줄바꿈으로 구분하고, 한글도 그대로 저장한다.
            for row in rows: stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        # serialize를 쓰기 함수로 전달해 파일 전체를 임시 파일 작성 후 교체한다.
        atomic_write(self.path(name), serialize)
