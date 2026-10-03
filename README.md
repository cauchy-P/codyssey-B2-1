# 나만의 용돈 기입장

Python 3.10 이상, 표준 라이브러리만 사용하는 콘솔 프로그램입니다. 설치할 패키지가 없습니다.

## 실행

이 README가 있는 폴더에서 실행합니다. 시스템에 따라 `python3` 대신 `python`을 사용하세요.

```sh
python3 -m budget_app --help
python3 -m budget_app add
python3 -m budget_app list --limit 10
python3 -m budget_app search --from 2026-10-01 --to 2026-10-31 --category food --type expense --q 점심 --tag meal
python3 -m budget_app summary --month 2026-10 --top 3
python3 -m budget_app budget set --month 2026-10 --amount 10000
python3 -m budget_app budget list
python3 -m budget_app category add
python3 -m budget_app category list
python3 -m budget_app category remove --name books
python3 -m budget_app update --id TX_대신_실제_id --amount 20000 --memo "저녁" --tags "meal,school"
python3 -m budget_app delete --id TX_대신_실제_id
python3 -m budget_app import --from examples/import.csv
python3 -m budget_app export --out october.csv --month 2026-10
python3 -m budget_app export --out period.csv --from 2026-10-01 --to 2026-10-31
```

`add`는 날짜, 타입, 카테고리, 금액, 메모, 태그를 순서대로 대화형 입력합니다. 잘못된 입력은 원인과 힌트를 출력하고 종료하므로 다시 실행하세요. `category add/remove`도 이름을 입력하지 않으면 대화형입니다. 자동 실행 시에는 `--name books`로 지정할 수 있습니다. `update`는 **옵션 방식으로 고정**하며, 지정한 필드만 변경합니다. `--memo "" --tags ""`는 해당 필드를 비웁니다. `id`는 추가 후 표시된 실제 값을 사용하세요.

모든 명령 및 하위 명령에서 `--help`를 사용할 수 있습니다. 옵션은 `--` 표기를 사용합니다. 검색 조건은 AND로 결합하며 날짜 양끝을 포함합니다. `--q`는 메모의 대소문자를 무시하는 부분 문자열 검색, `--tag`는 태그 전체 일치입니다. list는 기본 20건, search는 기본 전체 결과이며 둘 다 `--limit`을 지원합니다.

최신순은 **거래 날짜 내림차순**입니다. 날짜가 같으면 id 내림차순으로 순서를 고정합니다. 같은 날짜 안에서 입력 시각순을 보장하지 않습니다.

## 저장 파일

기본 폴더는 실행 위치의 `./data`입니다. 첫 실행에 다음 세 파일을 생성하며 이후 실행에 재사용합니다.

- `transactions.jsonl`: id/type/date/amount/category/memo/tags를 가진 거래 객체, 날짜 내림차순. 태그는 JSON 배열.
- `categories.jsonl`: `{"name":"food"}` 형태의 카테고리 객체.
- `budgets.jsonl`: `{"month":"2026-10","amount":10000}` 형태의 월 예산 객체.

모두 UTF-8 JSONL이며 한 줄에 객체 하나를 저장합니다. 카테고리 파일이 **없을 때** food, transport, rent, etc, salary를 생성합니다. 이미 존재하지만 비어 있으면 기본값을 다시 넣지 않고 `category add`로 직접 등록합니다. 사용 중인 카테고리는 삭제를 차단합니다. 예산은 양수 정수이며 같은 달에 다시 설정하면 덮어씁니다.

저장 경로 변경:

```sh
python3 -m budget_app --data-dir ./my-data list
python3 -m budget_app list --data-dir ./my-data
```

중첩 명령에서는 `--data-dir`을 `budget/category` 앞 또는 바로 뒤에 둡니다. 저장 파일을 직접 수정하면 정렬/참조 관계를 깨뜨릴 수 있으므로 명령으로 관리하세요. 동일 폴더에 여러 프로세스가 동시에 쓰는 방식은 지원하지 않습니다.

## CSV 교환 스키마

UTF-8, 헤더 필수. 헤더는 다음 **6개 컬럼과 순서**로 고정합니다. 선택 필드도 헤더는 필요하고 값만 비워 둡니다. UTF-8 BOM은 사용하지 않습니다.

| 컬럼 | 값 필수 | 형식 |
|---|---|---|
| date | Y | 실제 날짜 YYYY-MM-DD |
| type | Y | income 또는 expense |
| category | Y | 등록된 카테고리 이름 |
| amount | Y | 양수 정수, 소수/천 단위 쉼표 금지 |
| memo | N | 문자열, 빈 값 허용 |
| tags | N | 쉼표로 구분한 태그, 빈 값 허용 |

```csv
date,type,category,amount,memo,tags
2026-10-03,expense,food,15000,"점심, 후식","meal,school"
```

쉼표·줄바꿈·큰따옴표를 포함한 필드는 CSV 규칙대로 인용합니다. 내보내기는 표준 `csv` 모듈이 이를 처리합니다. 태그 내부의 쉼표는 태그 구분자로 해석합니다. CSV에는 id가 없으므로 가져올 때 새 UUID id를 부여합니다. 같은 CSV를 반복 가져오면 거래가 중복 추가됩니다.

export는 `--month` 또는 `--from`과 `--to`를 함께 받으며 두 방식의 혼용을 막습니다. 대상 CSV가 있으면 원자적으로 덮어씁니다. 저장용 세 파일을 대상으로 지정하면 오류를 냅니다.

import는 **전부 성공 또는 전체 취소** 정책입니다. 모든 행을 검증한 뒤 반영하며, 유효하지 않은 행이 하나라도 있으면 행 번호/원인을 표시하고 거래 파일을 변경하지 않습니다. CSV 구조/인코딩 오류도 전체 취소합니다. 행 번호는 줄바꿈을 포함한 CSV 레코드의 마지막 물리적 줄 번호입니다. 성공 시 imported=N, skipped=0을 출력합니다.

## 오류와 종료 코드

예상 가능한 입력/파일 오류는 스택트레이스 없이 stderr에 `[오류]`와 `[힌트]`를 출력합니다. 성공 0, 입력/저장 오류 1, 명령 구문 오류 2, 사용자 중단 130입니다.

```sh
python3 -m budget_app delete --id missing
echo $?
```

위 명령은 오류 메시지 뒤에 `1`을 표시합니다. 도움말 종료 코드는 0입니다. 버그까지 숨기기 위해 모든 Exception을 일괄 삼키지는 않습니다.

## 검증

```sh
python3 -m unittest discover -s tests -v
```

테스트는 임시 폴더에서 실행하며 실제 data를 변경하지 않습니다. 자세한 설계 설명과 평가 대응은 `DESIGN.md`, 검증 결과는 `VERIFICATION.md`에 있습니다.
