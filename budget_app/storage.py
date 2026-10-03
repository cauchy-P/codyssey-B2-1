import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator
from .models import AppError


def atomic_write(path: Path, writer) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
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
            for number, line in enumerate(stream, 1):
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict): raise ValueError()
                except ValueError:
                    raise AppError(f'{name}.jsonl {number}행이 손상되었습니다. 백업을 복구하세요.') from None
                yield row

    def write(self, name: str, rows: Iterable[dict[str, Any]]) -> None:
        def serialize(stream):
            for row in rows: stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        atomic_write(self.path(name), serialize)
