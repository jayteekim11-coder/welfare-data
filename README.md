# welfare-data

정부·지자체 혜택 정보를 매일 자동으로 받아 `data/benefits.json` 하나로 정리하는 저장소예요.
안드로이드 앱은 이 파일만 내려받아서, 폰 안에서 지역·나이·성별로 걸러 보여줘요.

- 데이터 출처: [행정안전부_대한민국 공공서비스(혜택) 정보](https://www.data.go.kr/data/15113968/openapi.do) (공공데이터포털)
- 갱신: 매일 한국시간 새벽 3시 37분 자동 실행
- 인증키는 코드에 없고 GitHub Secret(`DATA_GO_KR_KEY`)에만 보관해요.

## 처음 설정하는 방법

1. GitHub에서 새 저장소 만들기 — 이름 `welfare-data`, **Public** 선택
2. 이 폴더 안의 내용(`.github`, `scripts`, `README.md`)을 저장소에 올리기
3. 저장소 **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `DATA_GO_KR_KEY`
   - Secret: 공공데이터포털 마이페이지의 **일반 인증키(Decoding)**
4. **Actions** 탭 → `혜택 데이터 갱신` → **Run workflow** 로 첫 실행
5. 몇 분 뒤 `data/benefits.json` 파일이 생기면 성공

## 파일 구조

| 항목 | 뜻 |
| --- | --- |
| `name`, `summary` | 서비스 이름, 한 줄 요약 |
| `target`, `criteria` | 지원 대상, 선정 기준 |
| `content` | 지원 내용 |
| `howToApply`, `deadline`, `receiver`, `phone`, `url` | 신청 방법, 기한, 접수기관, 문의처, 상세 링크 |
| `sido`, `sigungu` | 지자체 서비스의 지역 (없으면 전국 대상) |
| `gender` | `M`/`F` (없으면 성별 제한 없음) |
| `ageMin`, `ageMax` | 대상 나이 (없으면 제한 없음) |

※ 소득·재산·가구 조건은 반영되지 않아 "받을 가능성이 있는 혜택" 목록이에요. 최종 자격은 정부24·복지로에서 확인해야 해요.
