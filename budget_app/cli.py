import argparse
import csv
import sys
from functools import wraps
from itertools import islice
from pathlib import Path
from .models import AppError, positive
from .storage import JsonlRepository
from .service import BudgetService


def handle_errors(function):
    """공통 예외 표시와 종료 코드 변환."""
    # wrapper에서도 원래 함수의 이름·설명·타입 주석을 유지한다.
    @wraps(function)
    def wrapper(*args, **kwargs):
        try:
            function(*args, **kwargs)
            return 0
        except (AppError, OSError, UnicodeError, csv.Error, ValueError, KeyError, TypeError, EOFError) as error:
            print(f'[오류] {error}\n[힌트] 입력 형식, 파일 권한/UTF-8, --help를 확인하고 다시 실행하세요.', file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print('[오류] 입력 취소. [힌트] 명령을 다시 실행하세요.', file=sys.stderr)
            return 130
    return wrapper


# argparse의 입력 검증·도움말 생성을 사용하고 오류 표시 형식만 통일한다.
class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, f'[오류] {message}\n[힌트] --help로 사용법을 확인하세요.\n')


def parser() -> argparse.ArgumentParser:
    # 각 명령과 옵션의 입력 규칙을 등록한다.
    root = Parser(description='나만의 용돈 기입장')
    root.add_argument('--data-dir', default='data', help='저장 폴더 (기본 ./data)')
    # 선택한 하위 명령 이름을 args.command에 저장한다.
    commands = root.add_subparsers(dest='command', required=True)
    for name in ('add', 'list', 'search', 'summary', 'update', 'delete', 'export', 'import', 'category', 'budget'):
        p = commands.add_parser(name)
        p.add_argument('--data-dir', default=argparse.SUPPRESS, help='저장 폴더')
        if name in ('list', 'search'): p.add_argument('--limit', type=positive, default=20 if name == 'list' else None)
        if name in ('search', 'export'):
            p.add_argument('--from', dest='start')
            p.add_argument('--to', dest='end')
        if name == 'search':
            p.add_argument('--category')
            p.add_argument('--type', dest='kind', choices=['income', 'expense'])
            p.add_argument('--q')
            p.add_argument('--tag')
        if name == 'summary':
            p.add_argument('--month', required=True)
            p.add_argument('--top', type=positive, default=3)
        if name in ('update', 'delete'): p.add_argument('--id', required=True)
        if name == 'update':
            for field in ('date', 'type', 'category', 'amount', 'memo', 'tags'): p.add_argument('--' + field)
        if name == 'export':
            p.add_argument('--out', required=True)
            p.add_argument('--month')
        if name == 'import': p.add_argument('--from', dest='source', required=True)
        if name == 'category':
            subs = p.add_subparsers(dest='action', required=True)
            for action in ('add', 'list', 'remove'):
                sub = subs.add_parser(action)
                if action != 'list': sub.add_argument('--name')
        if name == 'budget':
            subs = p.add_subparsers(dest='action', required=True)
            setting = subs.add_parser('set')
            setting.add_argument('--month', required=True)
            setting.add_argument('--amount', required=True)
            subs.add_parser('list')
    return root


@handle_errors
def main(argv=None) -> None:
    # 입력을 속성으로 변환한다. argv=None이면 실제 명령줄 인자를 읽는다.
    args = parser().parse_args(argv)
    service = BudgetService(JsonlRepository(Path(args.data_dir)))
    command = args.command
    if command == 'add':
        print('등록 카테고리: ' + ', '.join(sorted(service.categories())))
        raw = {field: input(label).strip() for field, label in (
            ('date', '날짜(YYYY-MM-DD): '), ('type', '타입(income/expense): '),
            ('category', '카테고리: '), ('amount', '금액(양수 정수): '),
            ('memo', '메모(선택): '), ('tags', '태그(쉼표 구분, 선택): '))}
        print('[저장 완료] id=' + service.add(raw).id)
    elif command in ('list', 'search'):
        # getattr로 검색 옵션을 모은다. list는 조건 없이 같은 검색 처리를 사용한다.
        filters = {key: getattr(args, key) for key in ('start', 'end', 'category', 'kind', 'q', 'tag')} if command == 'search' else {}
        found = False
        # **filters를 키워드 인자로 펼치고 최대 limit개만 꺼낸다(None이면 끝까지).
        for tx in islice(service.search(**filters), args.limit):
            found = True
            print(f'{tx.id} | {tx.date} | {tx.type} | {tx.category} | {tx.amount} | {tx.memo} | {",".join(tx.tags)}')
        if not found: print('데이터 없음')
    elif command == 'summary': service.summary(args.month, args.top)
    elif command == 'category':
        # action에 따라 목록 조회와 추가·삭제를 구분한다.
        if args.action == 'list':
            for name in sorted(service.categories()): print('- ' + name)
        else:
            # --name이 없으면 이름을 입력받고, remove일 때만 삭제 플래그를 전달한다.
            name = args.name if args.name is not None else input('카테고리명: ')
            service.category_change(name, args.action == 'remove')
            print('[완료] 카테고리 ' + args.action)
    elif command == 'budget':
        if args.action == 'set':
            service.set_budget(args.month, args.amount)
            print('[저장 완료] 월 예산')
        else:
            for month, amount in sorted(service.budgets().items()): print(f'{month}: {amount}원')
    elif command == 'update':
        service.update(args.id, {f: getattr(args, f) for f in ('date', 'type', 'category', 'amount', 'memo', 'tags') if getattr(args, f) is not None})
        print('[수정 완료] id=' + args.id)
    elif command == 'delete':
        service.delete(args.id)
        print('[삭제 완료] id=' + args.id)
    elif command == 'import': print(f'[완료] imported={service.import_csv(Path(args.source))}, skipped=0')
    elif command == 'export':
        if not args.month and not (args.start and args.end): raise AppError('--month 또는 --from과 --to를 함께 지정하세요.')
        if args.month and (args.start or args.end): raise AppError('--month와 기간 조건 중 하나만 사용하세요.')
        count = service.export_csv(Path(args.out), start=args.start, end=args.end, month=args.month)
        print(f'[완료] {args.out} ({count} records)')
