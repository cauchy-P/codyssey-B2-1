from dataclasses import dataclass, asdict
from datetime import date
from typing import Any
import re

class AppError(Exception):
    pass

def valid_date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise AppError('날짜는 YYYY-MM-DD 형식으로 입력하세요. 예: 2026-10-03')
    try: date.fromisoformat(value)
    except ValueError: raise AppError('실제로 존재하는 날짜를 입력하세요.') from None
    return value

def valid_month(value: str) -> str:
    valid_date(value + '-01')
    return value

def positive(value: Any) -> int:
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]+', str(value)) or int(value) <= 0:
        raise AppError('양수 정수를 입력하세요. 예: 15000')
    return int(value)

@dataclass(frozen=True)
class Transaction:
    id: str
    type: str
    date: str
    amount: int
    category: str
    memo: str = ''
    tags: tuple[str, ...] = ()

    @classmethod
    def create(cls, raw: dict[str, Any], categories: set[str]) -> 'Transaction':
        if raw.get('type') not in ('income', 'expense'):
            raise AppError('type은 income 또는 expense를 입력하세요.')
        if raw.get('category') not in categories:
            raise AppError('등록되지 않은 카테고리입니다. category add로 등록하세요.')
        if not isinstance(raw.get('id'), str) or not raw['id']:
            raise AppError('id가 없습니다. 저장 파일을 확인하세요.')
        tags = raw.get('tags', ())
        if isinstance(tags, str): tags = tags.split(',')
        if not isinstance(tags, (tuple, list)) or any(not isinstance(t, str) for t in tags):
            raise AppError('tags는 문자열 목록이어야 합니다.')
        if not isinstance(raw.get('memo', ''), str): raise AppError('memo는 문자열이어야 합니다.')
        return cls(raw['id'], raw['type'], valid_date(raw['date']), positive(raw['amount']),
                   raw['category'], raw.get('memo', ''), tuple(t.strip() for t in tags if t.strip()))

    def record(self) -> dict[str, Any]:
        return asdict(self)
