import csv
import inspect
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from budget_app.models import AppError
from budget_app.service import BudgetService, FIELDS
from budget_app.storage import JsonlRepository

ROOT = Path(__file__).resolve().parents[1]

class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.data = self.folder / 'data'
        self.service = BudgetService(JsonlRepository(self.data))

    def run_cli(self, *args, input=None, ok=True):
        result = subprocess.run([sys.executable, '-m', 'budget_app', '--data-dir', str(self.data), *args], input=input, text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        if not ok: self.assertIn('[힌트]', result.stderr)
        return result

    def add(self, date='2026-10-03', amount=100, **changes):
        return self.service.add(dict(date=date, type='expense', category='food', amount=amount, memo='점심', tags='meal,work', **changes))

    def csv_file(self, rows):
        path = self.folder / 'input.csv'
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(FIELDS)
            writer.writerows(rows)
        return path

    def test_interactive_add_and_restart(self):
        added = self.run_cli('add', input='2026-10-03\nexpense\nfood\n15000\n점심\nmeal,work\n')
        self.assertIn('id=TX-', added.stdout)
        self.assertIn('15000', self.run_cli('list').stdout)
        self.run_cli('category', 'add', '--name', 'books')
        self.run_cli('budget', 'set', '--month', '2026-10', '--amount', '10000')
        self.assertIn('books', self.run_cli('category', 'list').stdout)
        summary = self.run_cli('summary', '--month', '2026-10').stdout
        self.assertIn('150.0%', summary)
        self.assertIn('예산 초과!', summary)
        self.assertEqual(len(list(self.data.glob('*.jsonl'))), 3)

    def test_order_filters_limit_generators(self):
        self.add('2026-10-01')
        newest = self.add('2026-10-05')
        self.add('2026-10-03')
        self.assertTrue(inspect.isgenerator(self.service.transactions()))
        self.assertTrue(inspect.isgenerator(self.service.search()))
        self.assertEqual(next(self.service.search()).id, newest.id)
        result = self.run_cli('search', '--from', '2026-10-02', '--to', '2026-10-04', '--category', 'food', '--type', 'expense', '--q', '점', '--tag', 'work')
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertEqual(len(self.run_cli('list', '--limit', '1').stdout.splitlines()), 1)

    def test_update_delete_atomic_failures(self):
        old = self.add()
        self.run_cli('update', '--id', old.id, '--date', '2026-11-01', '--amount', '200', '--memo', '', '--tags', '')
        tx = next(self.service.transactions())
        self.assertEqual((tx.date, tx.amount, tx.tags, tx.memo), ('2026-11-01', 200, (), ''))
        before = self.service.repo.path('transactions').read_bytes()
        self.run_cli('delete', '--id', 'missing', ok=False)
        self.run_cli('update', '--id', old.id, '--amount', '0', ok=False)
        self.assertEqual(before, self.service.repo.path('transactions').read_bytes())
        with patch('budget_app.storage.os.replace', side_effect=OSError('교체 실패')):
            with self.assertRaises(OSError): self.service.delete(old.id)
        self.assertEqual(before, self.service.repo.path('transactions').read_bytes())
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), ['budgets.jsonl', 'categories.jsonl', 'transactions.jsonl'])
        self.run_cli('delete', '--id', old.id)
        self.assertEqual(list(self.service.transactions()), [])

    def test_category_protection(self):
        self.add()
        self.run_cli('category', 'remove', '--name', 'food', ok=False)
        self.run_cli('category', 'add', input='books\n')
        self.run_cli('category', 'remove', '--name', 'books')
        self.assertNotIn('books', self.service.categories())

    def test_csv_roundtrip_and_rollback(self):
        source = self.csv_file([['2026-10-03', 'expense', 'food', '123', '점심, 식사\n후식', 'meal,work']])
        self.run_cli('import', '--from', str(source))
        target = self.folder / 'output.csv'
        self.run_cli('export', '--out', str(target), '--month', '2026-10')
        with target.open(encoding='utf-8', newline='') as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[0], FIELDS)
        self.assertEqual(rows[1][4:], ['점심, 식사\n후식', 'meal,work'])
        before = self.service.repo.path('transactions').read_bytes()
        source = self.csv_file([['2026-10-04', 'expense', 'food', '100', '', ''], ['2026-13-03', 'expense', 'food', '0', '', '']])
        result = self.run_cli('import', '--from', str(source), ok=False)
        self.assertIn('3행', result.stderr)
        self.assertEqual(before, self.service.repo.path('transactions').read_bytes())
        self.run_cli('export', '--out', str(target), '--from', '2026-10-01', '--to', '2026-10-31')

    def test_income_summary_and_date_reordering(self):
        older = self.add('2026-10-01', 150)
        self.add('2026-10-05', 50)
        self.service.add(dict(date='2026-10-02', type='income', category='salary', amount=1000))
        result = self.run_cli('summary', '--month', '2026-10', '--top', '1').stdout
        for text in ('총 수입: 1000원', '총 지출: 200원', '잔액: 800원', '1) food 200원'):
            self.assertIn(text, result)
        self.run_cli('update', '--id', older.id, '--date', '2026-10-10')
        self.assertEqual(next(self.service.transactions()).id, older.id)
        self.run_cli('export', '--out', str(self.service.repo.path('transactions')), '--month', '2026-10', ok=False)

    def test_errors_and_help(self):
        for args in [('list', '--limit', '0'), ('search', '--from', '2026-11-01', '--to', '2026-10-01'), ('import', '--from', str(self.folder/'missing.csv')), ('export', '--out', str(self.folder/'out.csv')), ('budget', 'set', '--month', 'bad', '--amount', '10'), ('update', '--id', 'missing'), ('search', '--type', 'invalid')]:
            with self.subTest(args=args): self.run_cli(*args, ok=False)
        for command in ('add', 'list', 'search', 'summary', 'update', 'delete', 'export', 'import', 'category', 'budget'):
            self.run_cli(command, '--help')
        self.assertIn('데이터 없음', self.run_cli('summary', '--month', '2026-09').stdout)
        self.service.repo.path('transactions').write_text('{broken\n', encoding='utf-8')
        self.run_cli('list', ok=False)

    def test_invalid_csv_encoding_and_header(self):
        source = self.folder/'invalid.csv'
        for content in (b'bad,header\n', b'\xff', b'date,type,category,amount,memo,tags\n2026-10-03,expense,food,100\n', b'date,type,category,amount,memo,tags\n"unterminated'):
            source.write_bytes(content)
            self.run_cli('import', '--from', str(source), ok=False)
        self.assertEqual(list(self.service.transactions()), [])

if __name__ == '__main__': unittest.main()
