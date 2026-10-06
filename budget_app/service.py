import csv
from pathlib import Path
from typing import Iterator, Any
from uuid import uuid4
from .models import Transaction, AppError, valid_date, valid_month, positive
from .storage import JsonlRepository, atomic_write

FIELDS = ['date', 'type', 'category', 'amount', 'memo', 'tags']


class BudgetService:
    """검증, 검색, 집계, 변경 정책을 담당한다."""
    def __init__(self, repository: JsonlRepository): self.repo = repository

    def categories(self) -> set[str]:
        # 등록된 이름을 목록 조회·거래 검증에 사용할 중복 없는 집합으로 모은다.
        return {row['name'] for row in self.repo.read('categories')}

    def transactions(self) -> Iterator[Transaction]:
        categories = self.categories()
        for row in self.repo.read('transactions'):
            # 다음 값 요청마다 한 건을 검증·변환해 전달하므로 전체 거래를 메모리에 모으지 않는다.
            yield Transaction.create(row, categories)

    def search(self, start=None, end=None, category=None, kind=None, q=None, tag=None, month=None) -> Iterator[Transaction]:
        if start: valid_date(start)
        if end: valid_date(end)
        if month: valid_month(month)
        if start and end and start > end: raise AppError('--from은 --to 이전이어야 합니다.')
        if category and category not in self.categories(): raise AppError('category list로 등록된 이름을 확인하세요.')
        for tx in self.transactions():
            if start and tx.date < start: continue
            if end and tx.date > end: continue
            if month and not tx.date.startswith(month + '-'): continue
            if category and tx.category != category: continue
            if kind and tx.type != kind: continue
            if q and q.casefold() not in tx.memo.casefold(): continue
            if tag and tag not in tx.tags: continue
            # 모든 조건을 통과한 거래만 전달하고, 다음 값 요청까지 실행을 멈춘다.
            yield tx

    def add(self, raw: dict[str, Any]) -> Transaction:
        tx = Transaction.create(dict(raw, id='TX-' + uuid4().hex), self.categories())
        self._insert([tx])
        return tx

    def _insert(self, additions: list[Transaction], remove_id=None) -> None:
        # 내부 공통 저장 처리: 추가분을 합치고 remove_id에 해당하는 기존 거래를 제외한다.
        # 기존 파일이 내림차순이라는 전제에서 날짜·ID 내림차순을 유지한다.
        additions.sort(key=lambda tx: (tx.date, tx.id), reverse=True)
        # 수정은 기존 거래 제외와 변경된 거래 추가로, 삭제는 추가분 없이 처리한다.
        def merged():
            index = 0
            found = False
            for old in self.transactions():
                if old.id == remove_id:
                    found = True
                    continue
                while index < len(additions) and (additions[index].date, additions[index].id) > (old.date, old.id):
                    yield additions[index].record()
                    index += 1
                yield old.record()
            if remove_id and not found: raise AppError('없는 데이터입니다. list/search로 id를 확인하세요.')
            for tx in additions[index:]: yield tx.record()
        self.repo.write('transactions', merged())

    def update(self, identifier: str, changes: dict[str, Any]) -> None:
        if not changes: raise AppError('수정할 옵션을 하나 이상 입력하세요. update --help를 확인하세요.')
        # ID가 일치하는 첫 거래에서 탐색을 멈추고, 없으면 None을 반환한다.
        old = next((tx for tx in self.transactions() if tx.id == identifier), None)
        if old is None: raise AppError('없는 데이터입니다. list/search로 id를 확인하세요.')
        self._insert([Transaction.create(dict(old.record(), **changes), self.categories())], identifier)

    def delete(self, identifier: str) -> None: self._insert([], identifier)

    def category_change(self, name: str, remove=False) -> None:
        # remove=False면 추가, True면 삭제한다. 공백을 제거하고 빈 이름·중복을 검증한다.
        name = name.strip()
        if not name: raise AppError('카테고리 이름을 입력하세요.')
        categories = self.categories()
        if remove:
            if name not in categories: raise AppError('없는 카테고리입니다. category list를 확인하세요.')
            # 사용 중인 거래가 하나라도 있으면 삭제를 막아 거래의 카테고리 참조를 유지한다.
            if any(tx.category == name for tx in self.transactions()):
                raise AppError('사용 중인 카테고리는 삭제할 수 없습니다. 거래를 수정/삭제하세요.')
            categories.remove(name)
        else:
            if name in categories: raise AppError('이미 등록된 카테고리입니다. 다른 이름을 입력하세요.')
            categories.add(name)
        # 변경한 등록 이름을 이름순으로 정렬해 파일에 저장한다.
        self.repo.write('categories', ({'name': c} for c in sorted(categories)))

    def budgets(self) -> dict[str, int]:
        return {valid_month(r['month']): positive(r['amount']) for r in self.repo.read('budgets')}

    def set_budget(self, month: str, amount: str) -> None:
        values = self.budgets()
        values[valid_month(month)] = positive(amount)
        self.repo.write('budgets', ({'month': m, 'amount': a} for m, a in sorted(values.items())))

    def summary(self, month: str, top: int) -> None:
        income = expense = count = 0
        categories: dict[str, int] = {}
        for tx in self.search(month=month):
            count += 1
            if tx.type == 'income': income += tx.amount
            else:
                expense += tx.amount
                categories[tx.category] = categories.get(tx.category, 0) + tx.amount
        if not count: print('데이터 없음')
        print(f'총 수입: {income}원\n총 지출: {expense}원\n잔액: {income-expense}원')
        budget = self.budgets().get(month)
        if budget is not None:
            print(f'예산: {budget}원 (사용률 {expense/budget*100:.1f}%)')
            print('경고: 예산 초과!' if expense > budget else '예산 초과 없음')
        print(f'지출 TOP {top}')
        for index, (category, amount) in enumerate(sorted(categories.items(), key=lambda x: (-x[1], x[0]))[:top], 1):
            print(f'{index}) {category} {amount}원')

    def import_csv(self, path: Path) -> int:
        additions = []
        errors = []
        categories = self.categories()
        with path.open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream, strict=True)
            if reader.fieldnames != FIELDS:
                raise AppError('CSV 헤더는 date,type,category,amount,memo,tags 순서로 작성하세요.')
            for row in reader:
                try:
                    if None in row or any(v is None for v in row.values()):
                        raise AppError('컬럼 수가 다릅니다. 쉼표 포함 필드는 큰따옴표로 감싸세요.')
                    additions.append(Transaction.create(dict(row, id='TX-' + uuid4().hex), categories))
                except AppError as error: errors.append(f'CSV {reader.line_num}행: {error}')
        if errors:
            raise AppError('가져오기 전체 취소; 저장된 거래는 변경되지 않았습니다.\n' + '\n'.join(errors))
        self._insert(additions)
        return len(additions)

    def export_csv(self, path: Path, **filters) -> int:
        if path.resolve() in {self.repo.path(n).resolve() for n in ('transactions', 'categories', 'budgets')}:
            raise AppError('저장 파일에 내보낼 수 없습니다. 다른 CSV 경로를 지정하세요.')
        count = 0
        def write(stream):
            nonlocal count
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for tx in self.search(**filters):
                row = tx.record()
                row.pop('id')
                row['tags'] = ','.join(tx.tags)
                writer.writerow(row)
                count += 1
        atomic_write(path, write)
        return count
