# welfare-data

지원금나침반 앱이 쓰는 정부·지자체 혜택 데이터를 매일 자동으로 만들어 **GitHub Pages**로 배포하는 저장소예요.

- 데이터 출처: [행정안전부_대한민국 공공서비스(혜택) 정보](https://www.data.go.kr/data/15113968/openapi.do) (공공데이터포털)
  - 목록(serviceList) + 상세(serviceDetail: 구비서류·온라인신청) + 지원조건(supportConditions)
- 갱신: 매일 한국시간 새벽 3시 37분 자동 실행 (Actions → 혜택 데이터 갱신 → Run workflow 로 수동 실행도 가능)
- 인증키는 GitHub Secret(`DATA_GO_KR_KEY`)에만 보관해요.

## 배포되는 파일 (https://jayteekim11-coder.github.io/welfare-data/)

| 파일 | 내용 |
| --- | --- |
| `index.json` | 갱신 시각, 지역 목록, 파일 목록과 해시(바뀐 파일만 다시 받기) |
| `data/national.json` | 전국 대상 혜택 |
| `data/r/<번호>.json` | 시·도별 혜택 (index.json 의 files 에 지역 이름과 연결) |
| `search_dict.json` | 서술형 검색 사전 (`search/` 폴더) |
| `privacy.html` | 개인정보처리방침 (`site/` 폴더) |

## 폴더

- `scripts/fetch_benefits.py` : 데이터 수집·정리·분할
- `search/` : 서술형 검색 사전 (`build_dict.py` 실행 → `search_dict.json`). 여기만 고치면 앱 업데이트 없이 사전이 바뀌어요
- `site/` : 개인정보처리방침 등 안내 페이지

## 항목 설명 (혜택 하나)

| 항목 | 뜻 |
| --- | --- |
| `sido`, `sigungu` | 지자체 혜택의 지역 (없으면 전국) |
| `gender`, `ageMin`, `ageMax` | 성별·나이 제한 (없으면 제한 없음) |
| `inc` | 대상 소득 구간 코드 (0201 ~50% · 0202 ~75% · 0203 ~100% · 0204 ~200% · 0205 200%초과) |
| `life` | 대상 생애·직업 상황 코드 (하나라도 해당하면 대상) |
| `house` | 대상 가구 상황 코드 (하나라도 해당하면 대상) |
| `endDate` | 신청 마감일 (확정된 경우만) |
| `amount`, `amountLabel` | 지원 내용에서 찾은 최대 금액 |
| `docs`, `docsOfficial`, `docsSelf`, `onlineUrl` | 구비서류, 온라인 신청 주소 |
