"""
정부 혜택(보조금24) 데이터를 받아서 앱이 쓰기 좋은 파일로 정리하는 프로그램.

- 데이터 출처: 행정안전부_대한민국 공공서비스(혜택) 정보 (공공데이터포털 15113968)
  serviceList(목록) + serviceDetail(구비서류·온라인신청) + supportConditions(지원조건)
- 인증키는 코드에 적지 않고, 환경변수 DATA_GO_KR_KEY 에서 읽어요.
- 결과는 public/ 폴더에 만들어지고, GitHub Pages 로 배포돼요.
    public/index.json            : 갱신 시각, 지역 목록, 파일 목록(+변경 확인용 해시)
    public/data/national.json    : 전국 대상 혜택
    public/data/r/<번호>.json     : 시·도별 혜택 (내 지역 파일만 받으면 돼요)
    public/search_dict.json      : 서술형 검색 사전 (search/ 폴더에서 복사)
    public/privacy.html 등       : site/ 폴더의 페이지 (개인정보처리방침)

파이썬 기본 기능만 사용하므로 따로 설치할 것이 없어요.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone, timedelta
import re
import hashlib
import shutil

BASE_URL = "https://api.odcloud.kr/api/gov24/v3"
PER_PAGE = 1000          # 한 번에 받을 개수 (최대치)
MIN_EXPECTED = 3000      # 이보다 적게 받으면 뭔가 잘못된 것으로 보고 저장하지 않음
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT_DIR = os.path.join(ROOT, "public")


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


# 지역 판별
# 정부 데이터의 '소관기관유형' 값: 시군구 / 광역시도 / 중앙행정기관 / 공공기관 /
#   지방공기업 / 지방출자_출연기관 / 교육청
# - 시군구: '서울특별시 강남구' → (서울특별시, 강남구)
# - 광역시도: '경기도' → (경기도, 없음)
# - 중앙행정기관·공공기관: 전국 대상
# - 지방공기업·출연기관·교육청: 이름에서 지역을 찾아요 (예: '용산구시설관리공단' → 서울 용산구)
#   지역을 못 찾으면 엉뚱한 지역에 보이지 않도록 목록에서 빼요.
LOCAL_BODIES = ("지방공기업", "지방출자_출연기관", "교육청")

def build_region_index(services):
    """데이터 안의 지자체 이름으로 지역 사전을 만들어요 (시·도 이름이 바뀌어도 자동 대응)."""
    sidos, sigungus = set(), {}
    for s in services:
        t, org = (s.get("소관기관유형") or "").strip(), (s.get("소관기관명") or "").strip()
        parts = org.split()
        if t == "광역시도" and parts:
            sidos.add(parts[0])
        elif t == "시군구" and len(parts) >= 2:
            sidos.add(parts[0]); sigungus.setdefault(parts[0], set()).add(parts[1])
    alias = {}
    for sd in sidos:
        names = {sd, sd[0] + sd[2] if sd[:2] in ("충청", "경상", "전라") else sd[:2]}
        if "광주" in sd: names.add("광주")
        for n in names: alias[n] = sd
    # 시·군·구 짧은 이름(예: '시흥' → 경기도 시흥시). 여러 시·도에 같은 이름이 있으면 '?' 로 표시
    stem = {}
    for sd, gs in sigungus.items():
        for g in gs:
            for key in {g, g[:-1] if len(g) >= 3 else g}:
                stem[key] = (sd, g) if key not in stem or stem[key] == (sd, g) else "?"
    return alias, sigungus, stem

def parse_region(org_name, org_type, idx):
    alias, sigungus, stem = idx
    name = (org_name or "").strip()
    t = (org_type or "").strip()
    parts = name.split()
    if t == "광역시도" and parts:
        return parts[0], None, True
    if t == "시군구" and len(parts) >= 2:
        return parts[0], parts[1], True
    if t not in LOCAL_BODIES:
        return None, None, True                      # 중앙부처·공공기관 = 전국
    flat = name.replace("(재)", "").replace("재단법인", "").replace(" ", "")
    sido = next((alias[a] for a in sorted(alias, key=len, reverse=True) if flat.startswith(a)), None)
    rest = flat
    if sido:
        a = next(a for a in sorted(alias, key=len, reverse=True) if flat.startswith(a))
        rest = flat[len(sido):] if flat.startswith(sido) else flat[len(a):]
    gu = None
    for key in sorted(stem, key=len, reverse=True):
        if len(key) >= 2 and rest.startswith(key):
            v = stem[key]
            if sido and key in {g for g in sigungus.get(sido, ())} | {g[:-1] for g in sigungus.get(sido, ()) if len(g) >= 3}:
                gu = next(g for g in sigungus[sido] if g == key or g[:-1] == key); break
            if not sido and v != "?":
                sido, gu = v; break
    if sido:
        return sido, gu, True
    return None, None, False                          # 지역을 알 수 없는 지방기관 → 제외


# ---------------------------------------------------------------- 지원조건 코드
# 출처: 보조금24 supportConditions. 그룹 안은 '하나라도', 그룹끼리는 '모두' 만족해야 해요.
INCOME_CODES = ["JA0201", "JA0202", "JA0203", "JA0204", "JA0205"]      # 중위소득 ~50 / ~75 / ~100 / ~200 / 200초과
LIFE_CODES = ["JA0301", "JA0302", "JA0303", "JA0313", "JA0314", "JA0315", "JA0316", "JA0317",
              "JA0318", "JA0319", "JA0320", "JA0326", "JA0327", "JA0328", "JA0329", "JA0330"]
LIFE_NONE = "JA0322"        # '해당사항없음' 이 켜져 있으면 해당 상황이 없는 사람도 대상
HOUSE_CODES = ["JA0401", "JA0402", "JA0403", "JA0404", "JA0411", "JA0412", "JA0413", "JA0414"]
HOUSE_NONE = "JA0410"


def _on(cond, code):
    return str(cond.get(code) or "").strip().upper() == "Y"


def parse_conditions(cond):
    """지원조건 → (성별, 최소나이, 최대나이, 소득구간[], 생애상황[], 가구상황[])
    목록이 비어 있으면 그 항목은 제한이 없다는 뜻이에요."""
    if not cond:
        return None, None, None, [], [], []
    male, female = _on(cond, "JA0101"), _on(cond, "JA0102")
    gender = "M" if male and not female else "F" if female and not male else None
    age_min, age_max = to_int(cond.get("JA0110")), to_int(cond.get("JA0111"))
    if age_min is not None and age_min <= 0:
        age_min = None
    if age_max is not None and age_max >= 100:
        age_max = None
    inc = [c for c in INCOME_CODES if _on(cond, c)]
    if len(inc) == len(INCOME_CODES):
        inc = []                                  # 모든 구간이면 제한 없음
    life = [] if _on(cond, LIFE_NONE) else [c for c in LIFE_CODES if _on(cond, c)]
    house = [] if _on(cond, HOUSE_NONE) else [c for c in HOUSE_CODES if _on(cond, c)]
    return gender, age_min, age_max, inc, life, house


def short(code):
    return code[2:]   # 'JA0302' → '0302' (파일 크기 절약)


# ---------------------------------------------------------------- 신청 마감일
# 연·월·일이 모두 있는 날짜: 2026.04.06 / 2026-4-6 / 2026. 4. 6. / 2026년 4월 6일 / '26.4.6
_FULL = re.compile(
    r"(?<![\d.])(20\d{2}|'\d{2}|\d{2}(?=\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2}))\s*[.\-/년]\s*"
    r"(\d{1,2})\s*[.\-/월]\s*(\d{1,2})(?!\d)(?!\s*일?\s*기준)"
)
# 연도 없는 월·일: 12.31 / 4월 24일
_MD = re.compile(r"(?<![\d.])(\d{1,2})\s*[.월]\s*(\d{1,2})(?![\d:])")


def _year(y):
    y = int(y.lstrip("'"))
    return y + 2000 if y < 100 else y


def _full_dates(text):
    out = []
    for y, m, d in _FULL.findall(text):
        try:
            out.append(date(_year(y), int(m), int(d)))
        except ValueError:
            pass
    return out


def deadline_end(text):
    """
    신청기한 문장에서 '마감일'을 찾아 YYYY-MM-DD 로 돌려줘요.
    마감일을 확실히 알 수 없으면 None (= 마감 여부 판단하지 않고 계속 보여줌).
      '2026.03.04 ~ 2026.04.06'   → 2026-04-06
      "'26.7.1.~12.31."           → 2026-12-31 (끝 날짜에 연도가 없으면 앞 날짜의 연도 사용)
      '2026.3.3.~ 자금 소진 시'     → None (끝이 정해지지 않음)
      '2026.5.31.까지'             → 2026-05-31
      '상시신청', '매년 3월'        → None
    """
    if not text:
        return None
    t = text.replace("～", "~").replace("〜", "~")
    # '하반기 미정', '추후 공고', '매년' 처럼 다음 모집이 남아 있을 수 있으면 마감으로 보지 않아요
    if re.search(r"미정|추후|예정|별도\s*공고|매년|매월|연중|상시|수시", t):
        return None

    if "~" in t:
        head, tail = t.rsplit("~", 1)
        tail_full = _full_dates(tail)
        if tail_full:
            return max(tail_full).isoformat()
        md = _MD.search(tail)
        head_full = _full_dates(head)
        if md and head_full:
            start = max(head_full)
            try:
                end = date(start.year, int(md.group(1)), int(md.group(2)))
            except ValueError:
                return None
            if end < start:
                end = date(start.year + 1, end.month, end.day)
            return end.isoformat()
        return None  # '~' 뒤에 날짜가 없으면 끝이 열려 있는 것

    if "까지" in t:
        found = _full_dates(t.split("까지")[0])
        return max(found).isoformat() if found else None

    found = _full_dates(t)
    if len(found) == 1 and len(t.strip()) <= 20:   # 날짜 하나만 달랑 적힌 경우 = 마감일
        return found[0].isoformat()
    return None


# ---------------------------------------------------------------- 지원 금액
_UNIT = {"억원": 100_000_000, "억": 100_000_000, "천만원": 10_000_000, "백만원": 1_000_000, "만원": 10_000, "천원": 1_000, "원": 1}
_AMT = re.compile(r"(최대|월|연|1인당|1회|가구당|인당|1가구당|매월|연간)?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(억\s*원|억|천\s*만\s*원|백\s*만\s*원|만\s*원|천\s*원|원)(?![가-힣]{0,1}%)")

def amount(*texts):
    """지원 내용 문장에서 '가장 큰 지원 금액'을 찾아 (원 단위 숫자, 보기 좋은 글) 로 돌려줘요."""
    best = None
    for text in texts:
        if not text:
            continue
        for pre, num, unit in _AMT.findall(text):
            try:
                v = float(num.replace(",", "")) * _UNIT[unit.replace(" ", "")]
            except ValueError:
                continue
            if v < 10_000 or v > 5_000_000_000:      # 1만원 미만·50억 초과는 금액으로 보지 않아요
                continue
            if best is None or v > best[0]:
                best = (v, pre, num, unit)
    if not best:
        return None, None
    v, pre, num, unit = best
    v = int(v)
    if v >= 100_000_000:
        txt = f"{v / 100_000_000:g}억원"
    elif v >= 10_000:
        txt = f"{v // 10_000:,}만원"
    else:
        txt = f"{v:,}원"
    lead = {"매월": "월", "연간": "연", "인당": "1인당", "1가구당": "가구당"}.get(pre, pre)
    return v, (f"{lead} {txt}" if lead else txt)


# ---------------------------------------------------------------- 메인
CUTOFF = (datetime.now(timezone(timedelta(hours=9))).date() - timedelta(days=30)).isoformat()


def build(services, conditions, details=()):
    cond_by_id = {c.get("서비스ID"): c for c in conditions if c.get("서비스ID")}
    det_by_id = {d.get("서비스ID"): d for d in details if d.get("서비스ID")}
    region_index = build_region_index(services)
    result = []
    for s in services:
        sid = clean(s.get("서비스ID"))
        if not sid:
            continue
        sido, sigungu, known = parse_region(s.get("소관기관명"), s.get("소관기관유형"), region_index)
        if not known:
            continue
        d = det_by_id.get(sid, {})
        gender, age_min, age_max, inc, life, house = parse_conditions(cond_by_id.get(sid))
        content = clean(d.get("지원내용")) or clean(s.get("지원내용"))
        summary = clean(s.get("서비스목적요약"))
        amt, amt_label = amount(content, summary)
        online = clean(d.get("온라인신청사이트URL"))
        if online and not re.match(r"^https?://", online):
            online = None
        item = {
            "id": sid,
            "name": clean(s.get("서비스명")),
            "summary": summary,
            "field": clean(s.get("서비스분야")),
            "supportType": clean(s.get("지원유형")),
            "target": clean(d.get("지원대상")) or clean(s.get("지원대상")),
            "criteria": clean(d.get("선정기준")) or clean(s.get("선정기준")),
            "content": content,
            "howToApply": clean(d.get("신청방법")) or clean(s.get("신청방법")),
            "deadline": clean(d.get("신청기한")) or clean(s.get("신청기한")),
            "endDate": deadline_end(clean(d.get("신청기한")) or s.get("신청기한")),
            "receiver": clean(d.get("접수기관명")) or clean(s.get("접수기관")),
            "phone": clean(d.get("문의처")) or clean(s.get("전화문의")),
            "docs": clean(d.get("구비서류")),
            "docsOfficial": clean(d.get("공무원확인구비서류")),
            "docsSelf": clean(d.get("본인확인필요구비서류")),
            "onlineUrl": online,
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
            "inc": [short(c) for c in inc] or None,
            "life": [short(c) for c in life] or None,
            "house": [short(c) for c in house] or None,
            "amount": amt,
            "amountLabel": amt_label,
        }
        # 마감된 지 30일이 넘은 혜택은 빼요 (최근 마감은 앱이 오늘 날짜로 다시 판단)
        if item["endDate"] and item["endDate"] < CUTOFF:
            continue
        result.append({k: v for k, v in item.items() if v is not None})
    return result


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(path, "wb") as f:
        f.write(raw)
    return hashlib.sha256(raw).hexdigest()[:16], len(raw)


def publish(benefits, updated_at):
    """시·도별로 나눠서 public/ 폴더에 저장해요."""
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    national = [b for b in benefits if "sido" not in b]
    by_sido = {}
    for b in benefits:
        if "sido" in b:
            by_sido.setdefault(b["sido"], []).append(b)
    files, regions = {}, {}
    h, size = write_json(os.path.join(OUT_DIR, "data", "national.json"), {"items": national})
    files["전국"] = {"path": "data/national.json", "hash": h, "count": len(national), "bytes": size}
    for n, sido in enumerate(sorted(by_sido), start=1):
        items = sorted(by_sido[sido], key=lambda b: b["id"])
        h, size = write_json(os.path.join(OUT_DIR, "data", "r", f"{n}.json"), {"items": items})
        files[sido] = {"path": f"data/r/{n}.json", "hash": h, "count": len(items), "bytes": size}
        regions[sido] = sorted({b["sigungu"] for b in items if "sigungu" in b})
    # 서술형 검색 사전 (있으면 같이 배포 — 앱 업데이트 없이 사전을 고칠 수 있어요)
    dict_src = os.path.join(ROOT, "search", "search_dict.json")
    dict_info = None
    if os.path.exists(dict_src):
        with open(dict_src, encoding="utf-8") as f:
            d = json.load(f)
        h, size = write_json(os.path.join(OUT_DIR, "search_dict.json"), d)
        dict_info = {"path": "search_dict.json", "hash": h, "version": d.get("version", 1)}
    # 안내 페이지 (개인정보처리방침 등)
    site_src = os.path.join(ROOT, "site")
    if os.path.isdir(site_src):
        for name in os.listdir(site_src):
            shutil.copy(os.path.join(site_src, name), os.path.join(OUT_DIR, name))
    index = {
        "schema": 2,
        "updatedAt": updated_at,
        "source": "행정안전부_대한민국 공공서비스(혜택) 정보 (공공데이터포털)",
        "sourceUrl": "https://www.data.go.kr/data/15113968/openapi.do",
        "count": len(benefits),
        "regions": regions,
        "files": files,
        "dict": dict_info,
    }
    write_json(os.path.join(OUT_DIR, "index.json"), index)
    # 아무 폴더에서나 정적 파일이 그대로 보이도록
    open(os.path.join(OUT_DIR, ".nojekyll"), "w").close()
    return files


def main():
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        sys.exit("인증키가 없어요. 환경변수 DATA_GO_KR_KEY 를 설정해 주세요.")

    print("1) 서비스 목록 받는 중...")
    services = fetch_all("serviceList", key)
    print("2) 지원조건 받는 중...")
    conditions = fetch_all("supportConditions", key)
    print("3) 상세정보(구비서류·온라인신청) 받는 중...")
    try:
        details = fetch_all("serviceDetail", key)
    except Exception as e:   # 상세정보가 실패해도 목록만으로 계속 진행
        print("  상세정보 실패, 목록 정보만 사용:", e)
        details = []

    benefits = build(services, conditions, details)
    print(f"4) 정리 완료: {len(benefits)}건")
    if len(benefits) < MIN_EXPECTED:
        sys.exit(f"받은 데이터가 {len(benefits)}건밖에 안 돼서 배포하지 않았어요. 인증키나 API 상태를 확인해 주세요.")

    kst = timezone(timedelta(hours=9))
    files = publish(benefits, datetime.now(kst).strftime("%Y-%m-%d %H:%M"))
    for name, f in files.items():
        print(f"   {name}: {f['count']}건 {f['bytes'] / 1024:.0f}KB")
    print("5) public/ 폴더에 저장 완료")


if __name__ == "__main__":
    main()
