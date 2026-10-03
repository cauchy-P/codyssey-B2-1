# 검증 결과

2026-10-03 실행: `python3 -m unittest discover -s tests -v`

결과: **8개 테스트 모두 통과**. 임시 저장 폴더를 사용하며 실제 사용자 데이터는 변경하지 않습니다.

| 테스트 | 확인한 동작 |
|---|---|
| interactive_add_and_restart | 대화형 add, UUID 출력, 별도 프로세스 list, category/budget 영구 저장, 파일 3개, 예산 150%/초과 경고 |
| order_filters_limit_generators | 날짜 내림차순, 날짜/카테고리/type/메모/태그 복합 검색, limit, 실제 generator 반환 |
| update_delete_atomic_failures | 필드 변경과 비우기, 없는 id/0원 오류, 원본 보존, os.replace 실패 주입, 임시 파일 정리, 삭제 |
| category_protection | 사용 중인 카테고리 삭제 차단, 대화형 추가, 미사용 카테고리 삭제 |
| csv_roundtrip_and_rollback | UTF-8 헤더/컬럼, 쉼표/줄바꿈/태그 왕복, 기간 export, 일부 오류 행 import 전체 취소 및 행 번호 |
| income_summary_and_date_reordering | 수입/지출/잔액/TOP 집계, 날짜 수정 후 재정렬, 저장 파일 export 덮어쓰기 차단 |
| errors_and_help | 잘못된 개수/기간/type/월, 파일 없음, 조건 없는 export, 수정 옵션 없음, 손상 JSONL, 모든 상위 명령 help, 오류 종료 코드/힌트/스택트레이스 없음 |
| invalid_csv_encoding_and_header | 잘못된 헤더, 비 UTF-8, 컬럼 부족, 닫히지 않은 인용부호, 전체 취소 |

실제 10만 건 성능 측정, 정전 복구, 동시 쓰기, 외부 정적 타입 검사기 검증은 수행하지 않았습니다. 해당 한계와 개선 방향은 DESIGN.md에 설명했습니다.
