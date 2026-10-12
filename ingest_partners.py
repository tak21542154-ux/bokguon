# -*- coding: utf-8 -*-
"""리서치 워크플로 결과(journal.jsonl) → partners_seed.json 병합.
사용: python ingest_partners.py <journal.jsonl 경로>
기존 시드와 중복 제거 후 partner_type/major를 정규화해 병합한다.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, "data", "partners_seed.json")

VALID_MAJORS = [
    "종합시행(종합건설)", "종합 원상복구", "가드레일·방호울타리", "교통안전시설",
    "방음벽·휀스·펜스", "유리·샷시·자동문", "셔터·차단기·게이트", "누수·배관·설비",
    "지붕·판넬·캐노피", "외벽·석재·담장·조적", "도장·방수·미장", "간판·전기·가로등", "조경·수목",
]

MAJOR_KEYS = [
    ("종합시행(종합건설)", ["종합시행", "종합건설"]),
    ("종합 원상복구", ["종합 원상복구", "원상복구", "재해복구", "화재복구", "긴급복구", "리모델링", "인테리어", "시설물유지"]),
    ("가드레일·방호울타리", ["가드레일", "방호울타리", "중앙분리대", "충격흡수", "방호책"]),
    ("교통안전시설", ["교통안전", "표지판", "델리네이터", "시선유도", "차선"]),
    ("방음벽·휀스·펜스", ["방음벽", "휀스", "펜스", "낙석"]),
    ("유리·샷시·자동문", ["유리", "샷시", "창호", "자동문", "강화도어"]),
    ("셔터·차단기·게이트", ["셔터", "샷다", "차단기", "게이트", "주차관제"]),
    ("누수·배관·설비", ["누수", "배관", "설비", "상하수도", "소화전"]),
    ("지붕·판넬·캐노피", ["판넬", "캐노피", "지붕", "차양", "징크"]),
    ("외벽·석재·담장·조적", ["외벽", "석재", "석공", "담장", "조적", "벽돌"]),
    ("도장·방수·미장", ["도장", "방수", "미장", "도색", "우레탄", "타일"]),
    ("간판·전기·가로등", ["간판", "가로등", "전기", "조명", "사인"]),
    ("조경·수목", ["조경", "수목", "가로수", "잔디", "식재"]),
]


def norm_name(n):
    #  ⚠⚠ [라운드300] 전각 괄호(（） U+FF08/09)는 반각(()) 과 다른 코드포인트라
    #    이 정규식이 못 잡았다 — "(주)한빛건설"과 "（주）한빛건설"이 서로 다른
    #    중복판정 키가 돼, 다음 리서치에서 같은 회사가 두 번 들어갈 수 있다
    #    (실측: 실제 398개사 데이터로 새 정규화까지 대조해 새로운 충돌 0건
    #    확인 — 서로 다른 진짜 회사를 합치는 부작용은 없다).
    n = (n or "").translate(str.maketrans("（）", "()"))
    return re.sub(r"\s|\(주\)|㈜|주식회사|\(유\)|유한회사", "", n)


def norm_major(m, cat=""):
    m = (m or "").strip()
    if m in VALID_MAJORS:
        return m
    hay = m + " " + (cat or "")
    for name, keys in MAJOR_KEYS:
        if any(k in hay for k in keys):
            return name
    return "종합 원상복구"


def load_journal(path):
    #  ⚠⚠ [라운드217] 에이전트 CLI 저널의 최종 "result" 는 dict 가 아니라
    #    사람이 읽는 텍스트(그 안에 JSON 이 박혀 있을 수도, 아닐 수도)인 게
    #    보통이다 — 예전엔 `.get()` 을 바로 불러 result 가 문자열이면
    #    AttributeError 로 적재 전체가 죽었고, companies 키가 없는 dict 는
    #    조용히 버렸다(아래 없어진 no-op `pass` 가 그 흔적).
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("type") != "result":
                continue
            res = o.get("result")
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except Exception:
                    print(f"  ▲ result가 JSON이 아닌 텍스트라 건너뜀: {res[:80]!r}")
                    continue
            if not isinstance(res, dict):
                continue
            companies = res.get("companies")
            if not isinstance(companies, list):
                print(f"  ▲ result에 companies 목록이 없어 건너뜀(키: {sorted(res.keys())})")
                continue
            out.extend(companies)
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: python ingest_partners.py <journal.jsonl>")
        return 1
    journal = sys.argv[1]

    with open(SEED, encoding="utf-8") as f:
        existing = json.load(f)
    seen = {norm_name(p.get("name")) for p in existing}
    # 기존 데이터에 partner_type 보정
    for p in existing:
        if not p.get("partner_type"):
            p["partner_type"] = "시행사" if (p.get("major", "") or "").startswith("종합") else "시공사"

    incoming = load_journal(journal)
    added, dup, bad = 0, 0, 0
    for c in incoming:
        #  ⚠⚠ [라운드282] load_journal() 은 companies 가 list 인지만 확인하고
        #    그 원소 하나하나가 dict 인지는 안 봤다 — 리서치 에이전트가 스키마를
        #    완벽히 안 지킨 원소(맨 문자열·None 등) 하나만 섞여도 c.get() 에서
        #    AttributeError 로 여기서 죽는다. 이 함수는 existing 을 메모리에서만
        #    쌓다가 루프가 끝나야 파일에 한 번 쓰므로(136행), 죽는 순간 **이미
        #    검증까지 마친 앞쪽 항목들까지 전부 파일에 안 남고 사라진다**(실측
        #    확인: 크래시 후 파일이 실행 전과 바이트 단위로 동일). 형제(missing
        #    name·missing source_url)와 같은 방식으로 이 원소만 건너뛴다.
        if not isinstance(c, dict):
            bad += 1
            continue
        name = (c.get("name") or "").strip()
        k = norm_name(name)
        if not k:
            bad += 1
            continue
        if k in seen:
            dup += 1
            continue
        # 출처 없는 건 신뢰 불가 → 제외
        if not (c.get("source_url") or "").startswith("http"):
            bad += 1
            continue
        seen.add(k)
        ptype = c.get("partner_type")
        if ptype not in ("시행사", "시공사"):
            ptype = "시공사"
        existing.append({
            "name": name,
            "partner_type": ptype,
            "major": norm_major(c.get("major"), c.get("category")),
            "category": c.get("category", ""),
            "region": c.get("region", ""),
            "address": c.get("address", ""),
            "phone": c.get("phone", ""),
            "website": c.get("website", ""),
            "license": c.get("license", ""),
            "scope": c.get("scope", ""),
            "source_url": c.get("source_url", ""),
            "evidence": c.get("evidence", ""),
        })
        added += 1

    #  ⚠⚠ [라운드300] 그냥 덮어쓰면, 쓰는 도중(디스크 꽉 참·Ctrl+C 등) 끊겨도
    #    파일은 이미 잘려 나간 채로 남는다 — 이 파일은 다음 배포의 유일한
    #    시드 원본(db.py:_partner_seed())인데, db.py 쪽은 json.load() 실패를
    #    빈 목록으로 조용히 삼켜(db.py, 실측: 잘린 파일로 신규 DB를 만들면
    #    협력사 0곳으로 조용히 끝난다) 아무 경고 없이 협력사 전체가 사라진
    #    채 배포될 수 있다. 임시파일에 다 쓴 뒤 원자적으로 바꿔치기해, 쓰다
    #    만 상태가 원본 자리에 절대 안 남게 한다.
    tmp = SEED + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=1)
        os.replace(tmp, SEED)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise

    from collections import Counter
    tc = Counter(p.get("partner_type") for p in existing)
    mc = Counter(p.get("major") for p in existing)
    print(f"수집 {len(incoming)} → 신규 {added} / 중복 {dup} / 제외 {bad}")
    print(f"총 {len(existing)}개사  [시행사 {tc.get('시행사',0)} · 시공사 {tc.get('시공사',0)}]")
    print("공종별:")
    for m in VALID_MAJORS:
        if mc.get(m):
            print(f"  {mc[m]:3d}  {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
