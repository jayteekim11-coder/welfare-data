"""
정부 혜택(보조금24) 데이터를 받아서 앱이 쓰기 좋은 파일 하나로 정리하는 프로그램.

- 데이터 출처: 행정안전부_대한민국 공공서비스(혜택) 정보 (공공데이터포털 15113968)
- 인증키는 코드에 적지 않고, 환경변수 DATA_GO_KR_KEY 에서 읽어요.
  (GitHub 에서는 Settings > Secrets 에 넣은 값이 자동으로 들어와요)
- 결과 파일: data/benefits.json  (앱이 이 파일 하나만 내려받아요)

파이썬 기본 기능만 사용하므로 따로 설치할 것이 없어요.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

BASE_URL = "https://api.odcloud.kr/api/gov24/v3"
PER_PAGE = 1000          # 한 번에 받을 개수 (최대치)
MIN_EXPECTED = 3000      # 이보다 적게 받으면 뭔가 잘못된 것으로 보고 저장하지 않음
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "benefits.json")


# ---------------------------------------------------------------- API 호출
def call_api(endpoint, key, page):
    query = urllib.parse.urlencode({
        "page": page,
        "perPage": PER_PAGE,
        "returnType": "JSON",
        "serviceKey": key,
    })
    url = f"{BASE_URL}/{endpoint}?{query}"
    last_error = None
    for attempt in range(4):  # 실패하면 최대 4번까지 다시 시도
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # 네트워크 오류, 일시적 서버 오류 등
            last_error = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{endpoint} {page}페이지 호출 실패: {last_error}")


def fetch_all(endpoint, key):
    items, page = [], 1
    while True:
        body = call_api(endpoint, key, page)
        data = body.get("data") or []
        items.extend(data)
        total = body.get("totalCount") or body.get("matchCount") or 0
        print(f"  {endpoint}: {len(items)}/{total}")
        if not data or len(items) >= total:
            break
        page += 1
        time.sleep(0.5)  # 너무 빠르게 부르면 초당 제한에 걸려서 잠깐 쉼
    return items


# ---------------------------------------------------------------- 정리 도우미
def clean(text):
    """앞뒤 공백 제거, 빈 값은 None 으로."""
    if text is None:
        return None
    text = str(text).strip()
    return text or None


def to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_region(org_name, org_type):
    """
    소관기관명에서 지역을 뽑아요.
    예) '서울특별시 강남구' -> ('서울특별시', '강남구')
        '경기도'           -> ('경기도', None)
        '보건복지부'        -> (None, None)  = 전국 대상
    지자체가 아닌 기관(중앙부처·공공기관·교육청)은 전국 대상으로 봐요.
    """
    name = clean(org_name)
    if not name or not (org_type and "지방자치단체" in org_type):
        return None, None
    parts = name.split()
    sido = parts[0]
    sigungu = None
    if len(parts) >= 2 and parts[1][-1:] in ("시", "군", "구"):
        sigungu = parts[1]
        # '수원시 장안구' 처럼 구가 한 번 더 있으면 '수원시'로 묶음
    return sido, sigungu


def parse_conditions(cond):
    """지원조건에서 성별·나이 범위를 뽑아요. 정보가 없으면 '제한 없음'으로 처리."""
    if not cond:
        return None, None, None
    male = cond.get("JA0101") == "Y"
    female = cond.get("JA0102") == "Y"
    if male and not female:
        gender = "M"
    elif female and not male:
        gender = "F"
    else:
        gender = None  # 둘 다 Y 이거나 둘 다 비어있으면 성별 제한 없음

    age_min = to_int(cond.get("JA0110"))
    age_max = to_int(cond.get("JA0111"))
    if age_min is not None and age_min <= 0:
        age_min = None
    if age_max is not None and age_max >= 100:  # 120, 200 같은 값은 '상한 없음'
        age_max = None
    return gender, age_min, age_max


# ---------------------------------------------------------------- 메인
def build(services, conditions):
    cond_by_id = {c.get("서비스ID"): c for c in conditions if c.get("서비스ID")}
    result = []
    for s in services:
        sid = clean(s.get("서비스ID"))
        if not sid:
            continue
        sido, sigungu = parse_region(s.get("소관기관명"), s.get("소관기관유형"))
        gender, age_min, age_max = parse_conditions(cond_by_id.get(sid))
        item = {
            "id": sid,
            "name": clean(s.get("서비스명")),
            "summary": clean(s.get("서비스목적요약")),
            "field": clean(s.get("서비스분야")),
            "supportType": clean(s.get("지원유형")),
            "target": clean(s.get("지원대상")),
            "criteria": clean(s.get("선정기준")),
            "content": clean(s.get("지원내용")),
            "howToApply": clean(s.get("신청방법")),
            "deadline": clean(s.get("신청기한")),
            "receiver": clean(s.get("접수기관")),
            "phone": clean(s.get("전화문의")),
            "org": clean(s.get("소관기관명")),
            "orgType": clean(s.get("소관기관유형")),
            "userType": clean(s.get("사용자구분")),
            "url": clean(s.get("상세조회URL")),
            "updatedAt": clean(s.get("수정일시")),
            "sido": sido,
            "sigungu": sigungu,
            "gender": gender,
            "ageMin": age_min,
            "ageMax": age_max,
        }
        # 빈 값은 빼서 파일 크기를 줄임
        result.append({k: v for k, v in item.items() if v is not None})
    return result


def main():
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        sys.exit("인증키가 없어요. 환경변수 DATA_GO_KR_KEY 를 설정해 주세요.")

    print("1) 서비스 목록 받는 중...")
    services = fetch_all("serviceList", key)
    print("2) 지원조건 받는 중...")
    conditions = fetch_all("supportConditions", key)

    benefits = build(services, conditions)
    print(f"3) 정리 완료: {len(benefits)}건")

    if len(benefits) < MIN_EXPECTED:
        sys.exit(f"받은 데이터가 {len(benefits)}건밖에 안 돼서 저장하지 않았어요 "
                 f"(기존 파일 유지). 인증키나 API 상태를 확인해 주세요.")

    kst = timezone(timedelta(hours=9))
    output = {
        "updatedAt": datetime.now(kst).strftime("%Y-%m-%d %H:%M"),
        "source": "행정안전부_대한민국 공공서비스(혜택) 정보 (공공데이터포털)",
        "sourceUrl": "https://www.data.go.kr/data/15113968/openapi.do",
        "count": len(benefits),
        "items": sorted(benefits, key=lambda b: b["id"]),
    }
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))
    size_mb = os.path.getsize(OUTPUT_PATH) / 1024 / 1024
    print(f"4) 저장 완료: data/benefits.json ({size_mb:.1f}MB)")


if __name__ == "__main__":
    main()
