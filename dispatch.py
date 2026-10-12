# -*- coding: utf-8 -*-
"""현장 출동 수배 — 사진 없는 접수 건을 경매로 보낼 수 있게 만드는 앞단.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

■ 왜 필요한가
  사고 접수의 상당수가 **사진 없이** 들어온다(현장 실태 조사에서 확인).
  사진이 없으면 파손 규모를 알 수 없고, 파손 규모를 모르면 **입찰 상한을 정할 수 없어
  경매 자체를 열 수 없다.** 그래서 사진을 먼저 확보하는 단계가 필요하다.

■ 왜 '선착순 출동'인가
  사진을 찍어 올 주체 후보는 여럿이다(피해자·배달 인력·긴급출동·사설 출동).
  그러나 **사진을 찍는 주체를 믿을 수 없으면 그 사진으로 낸 견적도 믿을 수 없다.**
  반면 시공업체는 자기가 시공할 현장을 보러 가는 것이므로
  ① 사진을 제대로 찍을 동기가 있고 ② 그 자리에서 실견적까지 낼 수 있다.
  그래서 현장 인근 업체에게 **동시에 알리고, 30분 내 갈 수 있는 곳을 선착순으로 한 곳만** 잡는다.
  먼저 간 업체에게는 '1차 합의가 되면 그대로 시공'이라는 보상을 준다(출동 유인).

■ 두 갈래 (2트랙)
  · 사진 있음 → 곧바로 경매
  · 사진 없음 → 이 모듈(수배 → 출동 → 사진·실견적) → 1차 합의 성사 시 그 업체가 시공,
                결렬 시 **그 사진으로** 2차 경매

■ 반드시 지키는 것
  · **선착순은 동시성 문제다.** 두 업체가 같은 순간 수락하면 둘 다 출동해 헛걸음이 생긴다.
    그래서 claim 은 `BEGIN IMMEDIATE` + 조건부 UPDATE 의 rowcount 로만 판정한다.
  · 시각은 전부 한국시간(`datetime('now','+9 hours')`).
  · **자동화가 낙찰을 정하지 않는다.** 이 모듈은 '누가 현장에 가는가'까지만 정하고,
    시공을 누가 얼마에 하는지는 1차 합의(보험사 승인) 또는 경매가 정한다.
  · 복구온은 손해사정을 하지 않는다. 출동 업체의 실견적은 **시공 도급 견적**이지
    손해액 사정이 아니다.
"""
import re
import logging
import sqlite3

import db as DB
import geo as GEO

#  수배 알림 실패는 반드시 남긴다 — 조용히 삼키면 '아무도 안 왔다'의 원인을 못 찾는다.
_log = logging.getLogger("bokguon.dispatch")

# 수배 상태
ST_OPEN = "모집중"        # 알림을 뿌리고 수락을 기다리는 중
ST_CLAIMED = "수배됨"      # 한 곳이 잡았고 출동 중
ST_ARRIVED = "도착"        # 도착 + 사진 확보
ST_FAILED = "실패"         # 제한시간 초과 등
ST_CANCELED = "취소"

# 사건의 수배 상태(cases.dispatch_status)
CS_SEEKING = "수배중"
CS_MOVING = "출동중"
CS_PHOTO = "사진확보"
CS_FAILED = "수배실패"

SWEEP_LEASE_SEC = 120
SWEEP_LIMIT = 50

# 제한시간이 지난 수배를 고르는 조건.
#  ⚠ 문자열 비교가 아니라 datetime() 으로 정규화해 비교한다.
#    'T' 구분자나 다른 표기가 섞이면 문자열 비교에서 영원히 참이 되지 않아
#    **아무 일도 일어나지 않는 방식으로** 고장난다(발견이 늦다).
DISPATCH_OVERDUE_SQL = (
    "due_at IS NOT NULL AND datetime(due_at) <= datetime('now','+9 hours')"
)

#  ⚠ 위 조건은 **수락한 뒤**에만 성립한다(due_at 은 수락 시점에 채워진다).
#    그래서 '아무도 수락하지 않은' 수배는 어떤 점검에도 안 걸려 그대로 굳었다 —
#    운영 DB 에 3일째 '모집중'인 건이 실제로 있었다. 보험사 화면에는 계속
#    '출동 수배중'만 뜨고, 재수배도 중단 처리도 일어나지 않는다.
#    제한시간(분)이 지난 모집중 건도 같은 흐름으로 흘려보낸다.
DISPATCH_UNCLAIMED_SQL = (
    "due_at IS NULL AND datetime(created_at, '+' || ? || ' minutes') "
    "  <= datetime('now','+9 hours')"
)


def _setting_int(conn, key, default, lo, hi):
    """settings 정수값 읽기 — 빈값·손상값·범위 밖은 전부 기본값으로 되돌린다.

    ⚠⚠ app.py 의 동명 함수(4112행)와 반드시 같은 규칙을 유지한다(이 모듈은
      순환 임포트를 피하려 app.py 를 안 불러오므로 _like_escape()·_norm_dot()
      와 같은 이유로 각자 둔다) — 그런데 이 함수만 그 관례를 놓쳤었다.
      예전엔 범위 밖 값을 max(lo, min(hi, v))로 **경계값에 밀어 넣었다**
      (clamp). app.py 판은 범위를 벗어나면 조용히 default 로 되돌린다 —
      "설정이 깨져도 업무를 세우지 않는다"는 같은 목적이지만, clamp 는
      아무도 설정한 적 없는 경계값(dispatch_minutes 라면 240분)을 실제
      운영값으로 굳혀 문제를 숨기고, default 복귀는 원래 설계된 안전값으로
      돌아가 무엇이 잘못됐는지 감사로그·화면에서 더 잘 드러난다. 지금
      유일한 저장 경로(api_settings_set 의 RANGES 검증)가 저장 시점에
      이미 이 폭을 강제해 당장 재현되진 않지만, 그 검증을 거치지 않는
      경로(수기 DB 수정 등)로 값이 깨지면 이 함수 혼자 형제와 다른 결과를
      냈다. 파싱도 app.py 판처럼 int(float(x))로 맞춘다("30.0"류 저장값도
      허용 — 예전엔 int(str(x))라 그런 값이 오면 ValueError 로 조용히
      default 로 떨어졌다).
    """
    try:
        r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if r and str(r[0]).strip():
            v = int(float(r[0]))
            if lo <= v <= hi:
                return v
    except (sqlite3.Error, ValueError, TypeError, OverflowError):
        pass
    return default


def dispatch_minutes(conn):
    """출동 제한시간(분). 기본 30분."""
    return _setting_int(conn, "dispatch_minutes", 30, 5, 240)


def dispatch_fanout(conn):
    """한 회차에 동시에 부를 업체 수 상한."""
    return _setting_int(conn, "dispatch_fanout", 20, 1, 200)


def dispatch_max_round(conn):
    """재수배 최대 회차."""
    return _setting_int(conn, "dispatch_max_round", 3, 1, 10)


def _region_key(region, address):
    """지역 비교용 열쇠 — '서울특별시 송파구' → '송파'처럼 앞부분만 쓴다.

    좌표가 없어 정밀 거리 계산을 못 하므로, 지금은 **행정구역 문자열**로 좁힌다.
    (좌표 기반 반경 검색은 주소 좌표화가 붙은 뒤에 교체한다 — 그 전까지
     '가까운 순'이 아니라 '같은 지역'이라는 점을 화면에도 그대로 적는다.)
    """
    src = (region or "") or (address or "")
    src = src.strip()
    if not src:
        return ""
    #  ⚠⚠ [라운드622] 2022년부터 수원·고양·용인·창원 4개 시가 '특례시'라는
    #    공식 행정 명칭을 쓴다(예: '용인특례시') — geo.py 는 이미 라운드316에서
    #    이 표기를 정확히 같은 방식(먼저 '시'로 치환)으로 막아 뒀는데(실측 근거도
    #    같은 자리 — 운영DB 협력사 #211 하우건설(주)의 실주소가 '용인특례시'),
    #    dispatch.py 의 이 독자 재구현은 그 교훈을 못 물려받았다. 아래
    #    구/시/군 접미어 판정이 "특례시"의 마지막 글자 '시'만 보고 앞 3글자를
    #    통째로 도시명으로 착각해, "용인특례시 기흥구"의 rkey 가 "용인"이
    #    아니라 "용인특례"가 된다(실측: _region_key("경기도 용인특례시 기흥구","")
    #    == "용인특례", 정상표기 "용인시 기흥구"는 "용인"). candidates() 가 이
    #    값을 그대로 LIKE 패턴("%용인특례%")에 써서, 이 사건은 "용인시"로만
    #    등록된 실제 같은 지역 협력사와 전혀 매칭되지 않는다(대구 사례와 같은
    #    클래스지만 원인은 다르다 — 우연한 접미어가 아니라 아예 다른 접미어를
    #    셋이나 더 가진 신설 행정명칭). geo.py 와 같은 치환을 이 파일에도 적용.
    src = src.replace("특례시", "시")
    # 시·도 접두어를 떼고 시군구 단위를 뽑는다
    parts = src.replace("특별시", " ").replace("광역시", " ").replace("특별자치시", " ") \
               .replace("특별자치도", " ").replace("자치시", " ").split()
    for p in parts:
        #  ⚠⚠ [라운드511] '대구'는 시/도 이름 자체가 우연히 '구'로 끝난다
        #    (마지막 글자가 '구') — 아래 구/시/군 접미어 판정이 이 토큰을
        #    '어느 구'로 오판해, 뒤에 오는 진짜 구 단위 토큰('동구'·'수성구' 등)에
        #    닿기도 전에 도시명을 "대" 한 글자로 잘라 버렸다(실측:
        #    _region_key("대구광역시 동구","") == "대", 정상값은 "동"이어야 함).
        #    그 결과 candidates() 의 rkey_like 가 "%대%"가 되어, 활성 협력사
        #    400곳 중 88곳이 매칭되는데 그중 실제 '대구'가 들어간 곳은 32곳뿐 —
        #    나머지 56곳(대전·포항 등 주소에 우연히 '대'가 들어간 전국 업체)이
        #    "같은 지역"으로 뒤섞였다(실측, 운영 DB 읽기전용 조회).
        #    db.SIDO(시/도 약칭 17개, 이 파일이 이미 DB 로 참조한다)에 있는
        #    토큰은 시/군/구 판정 대상에서 제외한다 — '대구' 외 16개는 전부
        #    구/시/군으로 끝나지 않아 이 검사가 없어도 원래 안전했으므로
        #    회귀 없이 '대구' 한 곳만 고쳐진다.
        if p in DB.SIDO:
            continue
        if p.endswith(("구", "시", "군")):
            return p[:-1] if len(p) > 1 else p
    #  ⚠⚠ [라운드547] 구/시/군 접미어가 있는 토큰이 하나도 없으면 그냥 parts[0]
    #    (대개 시/도 자체, 위 루프가 건너뛴 그 토큰)을 돌려줬다 — '인천 남동'·
    #    '서울 강서'처럼 접미어를 뗀 흔한 구어체 표기가 전부 여기로 떨어져
    #    시/도 수준으로 뭉개졌다. 실측(운영 DB, 읽기전용 SELECT): region 이
    #    있는 사건 96건 중 28건이 이 모양이었다('서울 강서'→'서울', '경기
    #    용인'→'경기' 등) — 게다가 사건등록 화면 자신의 안내문구
    #    (templates/insurer_portal.html #c_region, placeholder="예: 인천 남동")가
    #    바로 이 표기를 예시로 든다. candidates() 의 1·2순위("같은 지역")가
    #    이 뭉개진 시/도 열쇠로 LIKE 검색을 해 '남동구'가 아니라 인천 전체를
    #    "같은 지역"으로 넓혀 버린다(예: 인천 강화군 업체까지 "같은 지역"으로
    #    잘못 우선 호출될 수 있다). 시/도 토큰(위 루프가 이미 건너뛴)이 아닌
    #    마지막 토큰이 있으면 그것이 사용자가 실제로 적은 세부지역이므로
    #    그대로 쓴다 — 시/도만 적었을 때(예: '대구' 단독)는 non_sido 가 비어
    #    기존과 동일하게 parts[0]로 폴백한다(회귀 없음, 라운드511 사례 포함).
    non_sido = [p for p in parts if p not in DB.SIDO]
    if non_sido:
        return non_sido[-1]
    return parts[0] if parts else ""


def _like_escape(s):
    """LIKE 패턴의 %·_·\\ 를 리터럴로 이스케이프한다(ESCAPE '\\' 와 짝).

    ⚠⚠ app.py 의 동명 함수와 반드시 같은 규칙을 유지한다(이 모듈은 순환
      임포트를 피하려 app.py 를 안 불러오므로 각자 둔다). 여기서 이스케이프
      하는 region/category 는 전부 보험사가 사건 접수 시 자유텍스트로 보낸
      값이다 — '%' 하나만 보내도 candidates() 의 지역·공종 필터가 전체매칭
      으로 무력화되어 무관한 업체 전원에게 출동 알림이 나간다(실측: 라운드130,
      category='%' 하나로 활성 파트너 전원이 매칭됨).
    """
    return (s or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _norm_dot(s):
    """가운뎃점 표기 흔들림을 하나로 모은다(검색 비교용).
       'ㆍ'(U+318D 아래아)·'･'(U+FF65 반각)를 우리가 쓰는 '·'(U+00B7)로 본다.

    ⚠⚠ [라운드499] app.py 의 동명 함수(라운드186)와 반드시 같은 규칙을
      유지한다(이 모듈은 순환 임포트를 피하려 app.py 를 안 불러오므로
      _like_escape() 와 같은 이유로 각자 둔다). 정부 공식 업종 표기
      ('ㆍ' U+318D, 예: "금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업")를 쓰는 협력사가
      실제로 10곳(id 305~314, 라운드186 실측) 있는데, candidates() 의 공종
      매칭이 이 정규화 없이 정본 '·'로만 비교하면 그 업체들이 트레이드
      일치 순위(1·3순위)에서 빠진다.
    """
    return (s or "").replace("ㆍ", "·").replace("･", "·")


def _case_trades(conn, cid, category=None):
    """이 사건의 공종 목록 — work_lots 에서 읽는다.

      ⚠⚠ **app.py 의 `case_trades()` 와 반드시 같은 규칙을 유지한다** — 한쪽만
        고치면 이 결함이 그대로 재발한다. 복합 사건의 `cases.category` 는
        `복합(A · B)` 라는 **표시용 문자열**이라 그대로 LIKE 하면 실제 공종
        어디에도 안 붙는다. 실측(2026-08-19): 자동 출동 수배가 이 문자열
        그대로 매칭해 복합 사건의 후보가 **0곳**이었다(work_lots 로 쪼개면
        72곳). app.py 쪽(업체 직접검색 화면)은 이미 case_trades() 로 고쳐져
        있었는데, 실제 자동 수배 경로인 이 파일만 안 고쳐져 있었다.
      ⚠ 문자열을 구분자로 쪼개지 않는다 — 구분자 ' · ' 가 공종 이름 안의
        '·'(유리·샷시·자동문)와 헷갈려 언젠가 잘못 쪼갠다."""
    lots = [r["category"] for r in conn.execute(
        "SELECT category FROM work_lots WHERE case_id=? ORDER BY id", (cid,)).fetchall()
        if r["category"]]
    if lots:
        return lots
    cat = (category or "").strip()
    return [cat] if cat and "복합(" not in cat else []


def candidates(conn, case_id, limit=None, exclude_ids=()):
    """이 사건에 부를 만한 업체 목록. 같은 지역·같은 공종을 우선하되,
    **각 순위 안에서는 현장에서 가까운 업체부터** 부른다(가까울수록 30분 도착 가능성↑).

    반환은 (partner_id, name, region, category, why, dist_km) 목록.
    dist_km 는 좌표가 없으면 None (그 경우 평점순으로 밀린다).
    """
    c = conn.execute(
        "SELECT id, category, region, address, lat, lng FROM cases WHERE id=?",
        (case_id,)).fetchone()
    if not c:
        return []
    cat = (c["category"] or "").strip()
    #  ⚠⚠ 공종 매칭은 `cat`(표시용 문자열) 이 아니라 `trades`(개별 공종 목록)로
    #    한다 — 복합 사건은 cat 그대로 LIKE 하면 0곳이 나온다(_case_trades 참조).
    trades = _case_trades(conn, case_id, cat)
    #  ⚠⚠ [라운드499] 형제(app.py:_kw_like_clause, 라운드186)는 이미 가운뎃점
    #    표기(ㆍ·･ vs 정본 ·)를 정규화하는데 이 자리는 안 거쳤다 — _norm_dot()
    #    독스트링 참조.
    _trade_where = " OR ".join(
        "REPLACE(REPLACE(COALESCE(category,''),'ㆍ','·'),'･','·') LIKE ? ESCAPE '\\'"
        " OR REPLACE(REPLACE(COALESCE(major,''),'ㆍ','·'),'･','·') LIKE ? ESCAPE '\\'"
        for _ in trades)
    _trade_params = [v for _t in trades for v in
                     (f"%{_like_escape(_norm_dot(_t))}%", f"%{_like_escape(_norm_dot(_t))}%")]
    rkey = _region_key(c["region"], c["address"])
    rkey_like = f"%{_like_escape(rkey)}%"
    lim = limit or 20
    # 현장 좌표(수동 우선, 없으면 지역중심) — 후보 거리 계산의 기준점
    try:
        clat, clng, _ = GEO.case_coords(c)
    except Exception:
        clat = clng = None

    ex = set(int(x) for x in (exclude_ids or ()) if x)
    out, seen = [], set()

    def _reachable(r):
        """이 업체가 **실제로 수락할 수 있는가.**

        둘 중 하나는 있어야 한다 — 포털 계정(화면에서 '수락'을 누른다) 또는
        휴대전화(문자·알림톡이 나간다). 유선번호로는 문자가 못 나간다.
        둘 다 없으면 목록에만 있고 현실에서는 오지 않는다 —
        실데이터에서 활성 399곳 중 계정 1곳·휴대전화 68곳뿐이었다.
        30분 선착순인데 못 받는 곳이 앞자리를 차지하면 그만큼 늦어진다.
        ⚠ **빼는 것이 아니라 뒤로 미는 것**이다(부를 곳이 없으면 그들도 부른다).
        """
        try:
            if (r["login_id"] or "").strip():
                return True
            d = re.sub(r"\D", "", r["phone"] or "")
            return d.startswith("01") and len(d) in (10, 11)
        except (KeyError, IndexError, TypeError):
            return False

    def _dist(r):
        if clat is None:
            return None
        try:
            plat, plng, _ = GEO.partner_coords(r)
        except Exception:
            return None
        return GEO.haversine_km(clat, clng, plat, plng)

    def _add(rs, why):
        # 이 순위에서 새로 담을 후보들을 거리순(가까운 순)으로 정렬해 붙인다.
        batch = []
        for r in rs:
            pid = r["id"]
            if pid in seen or pid in ex:
                continue
            seen.add(pid)
            dkm = _dist(r)
            batch.append({"id": pid, "name": r["name"], "region": r["region"],
                          "category": r["category"], "why": why, "dist_km": dkm,
                          "reachable": _reachable(r)})
        # ① 수락할 수단이 있는 곳 먼저 → ② 좌표 없는 업체는 뒤로 → ③ 가까운 순.
        #   못 받는 업체를 가깝다는 이유로 앞에 부르면 30분이 그냥 흘러간다.
        batch.sort(key=lambda x: (not x["reachable"],
                                  x["dist_km"] is None,
                                  x["dist_km"] if x["dist_km"] is not None else 9e9))
        out.extend(batch)

    #  ★ **자르기 전에 다 데려온다.** 종전에는 `평점 내림차순 LIMIT 30` 으로 먼저
    #    잘라 놓고 파이썬에서 거리 정렬을 했다 — 이미 버려진 업체 위에서 도는 정렬이라
    #    **가장 가까운 곳이 후보에 들어오지도 못했다**(경기 활성 87곳 중 27곳이 탈락).
    #    게다가 평점은 이제 대부분 NULL 이다(근거 없는 난수를 지웠다) — 즉 임의 컷이었다.
    #    지역·공종으로 이미 좁혀진 모집단이라 수십~수백 행이고, 한 번에 읽어도 싸다.
    #    자르는 것은 파이썬이 '연락 가능 → 가까운 순' 으로 정렬한 **뒤**에 한다.
    fetch = max(lim * 20, 500)
    # 1순위 — 같은 지역 + 공종이 맞는 업체
    if rkey and trades:
        _add(conn.execute(
            """SELECT id, name, region, address, category, lat, lng, login_id, phone FROM partners
                WHERE status='활성'
                  AND COALESCE(license_status,'미확인') <> '무등록'
                  AND (COALESCE(region,'') LIKE ? ESCAPE '\\' OR COALESCE(address,'') LIKE ? ESCAPE '\\')
                  AND (""" + _trade_where + """)
                ORDER BY (COALESCE(login_id,'') <> ''           OR COALESCE(phone,'') LIKE '01%') DESC, id LIMIT ?""",
            [rkey_like, rkey_like] + _trade_params + [fetch]).fetchall(),
            "같은 지역 · 공종 일치")
    # 2순위 — 같은 지역(공종 무관)
    #  ⚠⚠ [329라운드] len(out) 로 재면 "부를 만한 곳이 이미 충분하다"가 아니라
    #    "찾은 곳이 이미 충분하다"가 된다 — 1순위가 500건까지 끌어오는데 그중
    #    도달 가능(_reachable)은 실측 17%뿐이라, 흔한 공종·인구밀집 지역에서는
    #    1순위 자체가 lim 을 채워버려(대부분 도달불가인 채로) 2·3순위가 아예
    #    안 열린다 — 정작 부를 수 있는 곳은 더 넓혀야 나오는데. "빼는 게 아니라
    #    뒤로 미는 것"이라는 이 함수 자신의 설계원칙(_reachable 독스트링)이
    #    적용되려면, "충분한가" 판단도 도달 가능한 수로 해야 한다.
    if rkey and sum(1 for x in out if x["reachable"]) < lim:
        _add(conn.execute(
            """SELECT id, name, region, address, category, lat, lng, login_id, phone FROM partners
                WHERE status='활성'
                  AND COALESCE(license_status,'미확인') <> '무등록'
                  AND (COALESCE(region,'') LIKE ? ESCAPE '\\' OR COALESCE(address,'') LIKE ? ESCAPE '\\')
                ORDER BY (COALESCE(login_id,'') <> ''           OR COALESCE(phone,'') LIKE '01%') DESC, id LIMIT ?""",
            (rkey_like, rkey_like, fetch)).fetchall(),
            "같은 지역")
    # 3순위 — 공종이 맞는 업체(지역 무관). 지방·야간이라 인근에 아무도 없을 때의 폴백.
    #   여기서 거리 정렬이 진짜 힘을 쓴다 — 전국에서 '평점 높은' 곳이 아니라 '가장 가까운' 곳을 부른다.
    if trades and sum(1 for x in out if x["reachable"]) < lim:
        _add(conn.execute(
            """SELECT id, name, region, address, category, lat, lng, login_id, phone FROM partners
                WHERE status='활성'
                  AND COALESCE(license_status,'미확인') <> '무등록'
                  AND (""" + _trade_where + """)
                ORDER BY (COALESCE(login_id,'') <> ''           OR COALESCE(phone,'') LIKE '01%') DESC, id LIMIT ?""",
            _trade_params + [fetch]).fetchall(),
            "공종 일치(지역 밖)")
    #  ⚠ 순위(같은 지역·공종 → 같은 지역 → 공종)를 넘어 **응답 가능한 곳을 앞으로** 올린다.
    #    순위 안에서만 정렬하면, '같은 구인데 문자도 앱도 안 닿는 곳'이 '옆 구인데
    #    바로 수락할 수 있는 곳'보다 먼저 불린다 — 30분이 그냥 흘러간다.
    #    파이썬 정렬은 안정적이라 **순위·거리 순서는 그대로 보존**된다.
    out.sort(key=lambda x: not x.get("reachable"))
    return out[:lim]


def open_dispatch(conn, case_id, round_no=None, notify=None, include_tried=False):
    """수배를 연다 — 인근 업체들에게 동시에 알린다.

    반환 (dispatch_id, 부른 업체 수, **실제 알림이 나간 수**).
      ⚠ 뒤의 둘은 다를 수 있다. '불렀다'와 '닿았다'를 구분하지 않으면
        아무에게도 안 갔는데 수배가 열린 것처럼 보인다.

    ⚠ 같은 사건에 살아있는 수배가 이미 있으면 새로 열지 않는다(중복 출동 방지).

    include_tried=True 면 **이전 회차에 불렀던 업체도 다시 부른다.**
      기본값(False)은 헛걸음을 줄이지만, 회차를 다 소진해 '수배실패'가 된 사건은
      후보가 구조적으로 항상 0이 되어 다시 열 수가 없다. 그 회복 경로에서 쓴다.
      (거절 의사를 밝힌 곳은 그래도 제외한다 — 다시 부르면 신뢰를 잃는다)
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        live = conn.execute(
            "SELECT id FROM dispatches WHERE case_id=? AND status IN (?,?)",
            (case_id, ST_OPEN, ST_CLAIMED)).fetchone()
        if live:
            conn.rollback()
            return live[0], 0, 0

        #  ⚠ 끝난 사건은 다시 부르지 않는다.
        #    발주처가 취소했는데도 자동 재수배가 다음 회차를 열어, 협력사가 없어진
        #    현장으로 계속 불려 갔다(도착해도 합의가 안 열려 헛걸음만 남는다).
        #    수배는 '접수' 상태에서 배정 전인 사건에만 의미가 있다.
        #  ⚠⚠ [라운드95] case_no 도 함께 끌어온다 — 이 함수의 DB.log 세 곳이 전부
        #    detail 에 사건을 "사건 {case_id}"(숫자 PK)로 남기는데, 사건 이력
        #    리포트·정산 상세의 감사로그 타임라인은 case_no 문자열로 LIKE 검색한다
        #    (94라운드에서 settle_agreement 의 같은 결함을 먼저 고쳤다 — 형제
        #    함수들도 전부 같은 모양이라 이번에 마저 맞춘다).
        #  ⚠⚠ [라운드152] 이미 어떤 업체가 도착해 사진을 확보한 사건(dispatch_status=
        #    CS_PHOTO)도 이 조건만으로는 안 막힌다 — status='접수'·partner_id NULL
        #    그대로인 채로 1차 합의 검토가 진행 중이거나(open_agreement), 방금
        #    부동의로 끝나 2차 경매를 열기 전인 좁은 틈이 있다. 그 틈에 새 수배가
        #    열려 다른 업체가 claim+arrive 하면 cases.first_partner_id·first_photo_at
        #    ("최초 출동업체 — 1차 합의 상대이자 결렬 시에도 사진 제공자로 남는
        #    기록", arrive() 자신의 주석)이 조용히 나중 업체로 덮어써진다. 이미
        #    검토 중이거나 방금 확보된 사진이 있으면 새 수배를 막는다.
        cs = conn.execute("SELECT status, partner_id, case_no, dispatch_status FROM cases WHERE id=?",
                          (case_id,)).fetchone()
        if not cs or cs[0] != "접수" or cs[1] is not None or cs[3] == CS_PHOTO:
            conn.rollback()
            return 0, 0, 0

        # 회차 계산 — 이전 회차에서 이미 부른 업체는 다시 부르지 않는다
        prev = conn.execute(
            "SELECT COALESCE(MAX(round),0) FROM dispatches WHERE case_id=?", (case_id,)).fetchone()[0]
        rn = int(round_no or (prev + 1))
        if include_tried:
            # 회복 수배 — 거절한 곳만 뺀다(무응답은 다시 부를 수 있다)
            tried = [r[0] for r in conn.execute(
                """SELECT DISTINCT dc.partner_id FROM dispatch_calls dc
                     JOIN dispatches d ON d.id = dc.dispatch_id
                    WHERE d.case_id=? AND dc.response='거절'""", (case_id,)).fetchall()]
        else:
            tried = [r[0] for r in conn.execute(
                """SELECT DISTINCT dc.partner_id FROM dispatch_calls dc
                     JOIN dispatches d ON d.id = dc.dispatch_id
                    WHERE d.case_id=?""", (case_id,)).fetchall()]

        cands = candidates(conn, case_id, limit=dispatch_fanout(conn), exclude_ids=tried)
        if not cands:
            # 부를 업체가 없다 — 실패로 남겨 사람이 개입하게 한다.
            #  (조용히 아무 일도 안 하면 사건이 영원히 멈춘다)
            cur = conn.execute(
                #  ⚠ 데모 표식은 **사건에서 물려받는다**(아래 두 자리도 같다).
                #    운영 KPI 리포트·수배 관제 화면이 `dispatches.is_demo` 로 거르는데
                #    채우는 코드가 없어, 실측에서 그 지표가 100% 데모였다.
                """INSERT INTO dispatches(case_id, round, status, fail_reason, created_at, is_demo)
                   VALUES(?,?,?,?,?,
                          COALESCE((SELECT is_demo FROM cases WHERE id=?),0))""",
                (case_id, rn, ST_FAILED, "부를 수 있는 업체가 없음", DB.now(), case_id))
            did = cur.lastrowid
            conn.execute("UPDATE cases SET dispatch_status=? WHERE id=?", (CS_FAILED, case_id))
            DB.log(conn, "시스템", "출동수배 실패", f"{cs[2]} · {rn}회차 · 대상 업체 없음")
            conn.commit()
            return did, 0, 0

        cur = conn.execute(
            """INSERT INTO dispatches(case_id, round, status, created_at, is_demo)
               VALUES(?,?,?,?,COALESCE((SELECT is_demo FROM cases WHERE id=?),0))""",
            (case_id, rn, ST_OPEN, DB.now(), case_id))
        did = cur.lastrowid
        for i, p in enumerate(cands, start=1):
            dkm = p.get("dist_km")
            conn.execute(
                """INSERT OR IGNORE INTO dispatch_calls
                       (dispatch_id, partner_id, partner_name, dist_km, call_order,
                        notified_at, created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (did, p["id"], p["name"],
                 round(dkm, 1) if dkm is not None else None, i,
                 DB.now(), DB.now()))
        conn.execute("UPDATE cases SET dispatch_status=?, intake_type='사진없음' WHERE id=?",
                     (CS_SEEKING, case_id))
        DB.log(conn, "시스템", "출동수배 개시",
               f"{cs[2]} · {rn}회차 · {len(cands)}개사 동시 알림")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    # 알림은 트랜잭션 밖에서(외부 발송이 실패해도 수배는 이미 열려 있어야 한다)
    #
    # ⚠ 예전에는 여기서 예외를 통째로 삼켰다(로그도 없이). 그래서 협력사에게
    #   콜이 **0건** 나갔는데도 감사로그에는 "N개사 동시 알림", 화면에는 called=N 이
    #   찍혔다. 아무도 안 오는데 운영자는 수배가 열린 줄 알고 기다린다 — 사건이 조용히 멈춘다.
    #   실패는 삼키되(수배 자체는 이미 열렸으니 되돌리면 안 된다) **세고 남긴다.**
    sent = 0
    if notify:
        for p in cands:
            try:
                notify(p["id"], did, case_id)
                sent += 1
            except Exception:
                _log.exception("수배 알림 실패 dispatch=%s partner=%s", did, p.get("id"))
        # ★ notify() 의 INSERT 가 새 암시적 트랜잭션을 연다. 여기서 닫지 않으면
        #   다음 스윕의 BEGIN IMMEDIATE 가 "cannot start a transaction within a
        #   transaction" 으로 터진다.
        #  ⚠⚠ [라운드411] 이 마무리기록(DB.log)·commit() 만 이 파일의 다른 모든
        #    트랜잭션 블록과 달리 무방비였다 — 락 경합 등으로 실패하면 예외가
        #    이 함수 밖으로 그대로 터져나가고, 커밋 안 된 암시적 트랜잭션이 이
        #    커넥션에 남는다. sweep_dispatches() 의 호출부(825행 except)는
        #    rollback 없이 다음 대상으로 넘어가므로, 그 대상의 BEGIN IMMEDIATE
        #    (775행)가 "cannot start a transaction within a transaction" 으로
        #    또 죽어 남은 대상 전부의 재수배를 통째로 멈춘다 — 실측: manage.py
        #    cmd_sweep() 은 스윕들을 하나의 try 로 묶어서 이게 sweep_send_
        #    notifications·sweep_webhook_retries 까지 그 회차 통째로 건너뛰게
        #    만들고, 성공한 재수배 자체(협력사 알림 0건)도 조용히 묻힌다. 이
        #    파일의 다른 모든 자리처럼 try/except 로 막는다.
        try:
            if sent < len(cands):
                DB.log(conn, "시스템", "출동수배 알림 실패",
                       f"수배 {did} · {cs[2]} · {len(cands)}개사 중 {sent}건만 발송"
                       + (" — 아무에게도 못 갔습니다. 직접 배정이 필요합니다."
                          if not sent else ""))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return did, len(cands), sent


def assign_dispatch(conn, case_id, partner_id, reason, by="", supersede=False, on_supersede=None):
    """운영자가 **업체를 직접 지정해** 출동을 배정한다. 반환 (성공여부, 메시지, dispatch_id).

    ⚠ 왜 필요한가 — 회차를 다 소진해 '수배실패'가 된 사건은 선착순으로는 회복되지 않는다
      (부를 후보가 비거나, 아무도 안 잡는 야간·지방 건). 그때 사람이 전화로 잡고
      그 사실을 시스템에 남기는 경로가 없으면 사건이 조용히 늙는다.
      배정 사유를 **필수**로 받아 '왜 선착순을 건너뛰었는지'가 기록에 남게 한다.

    ⚠ supersede 로 밀려나는 수배가 ST_CLAIMED(이미 수락)면 그 협력사는 현장으로
      오고 있을 수 있다 — on_supersede(partner_id, partner_name, old_dispatch_id,
      case_id) 를 받으면 커밋 뒤에 부른다(같은 일을 하는 close_live_dispatches·
      open_dispatch 와 같은 원칙: 밀려난 쪽에도 알린다, 통지는 트랜잭션 밖에서).
    """
    reason = (reason or "").strip()
    if len(reason) < 2:
        return False, "배정 사유를 남겨 주세요(선착순을 건너뛴 이유).", None
    conn.execute("BEGIN IMMEDIATE")
    try:
        live = conn.execute(
            "SELECT id, status, claimed_partner_id, claimed_name FROM dispatches "
            " WHERE case_id=? AND status IN (?,?)",
            (case_id, ST_OPEN, ST_CLAIMED)).fetchone()
        if live and not supersede:
            #  ⚠ **여기서 그냥 막으면 운영자가 갇힌다.**
            #    첫 주에는 포털 계정도 문자도 없어 수락이 구조적으로 0이다.
            #    그동안 운영자가 전화로 업체를 구해도 배정이 안 되고, 이 수배를
            #    멈추는 경로도 없어서 회차가 다 소진될 때까지 기다려야 했다.
            #    되돌릴 수 없는 일이 아니므로 **막지 말고 되묻는다**(supersede).
            conn.rollback()
            return False, "이 사건에는 이미 진행 중인 수배가 있습니다.", live[0]
        if live:
            #  진행 중이던 수배를 접고 넘어간다 — 왜 접었는지 남긴다.
            #  ('실패'가 아니라 '취소' 다. 업체가 늦은 게 아니라 우리가 거둔 것이다)
            conn.execute(
                "UPDATE dispatches SET status=?, fail_reason=? WHERE id=? AND status IN (?,?)",
                (ST_CANCELED, f"운영자 직접 배정으로 종료 — {reason[:80]}",
                 live[0], ST_OPEN, ST_CLAIMED))
        #  ⚠ 자동 수배(open_dispatch)·수락(claim)에는 있는 가드가 **직접 배정에만**
        #    빠져 있었다. 1차 합의나 2차 낙찰이 끝난 사건의 옛 수배는 '도착'이라
        #    위의 live 검사(모집중·수배됨)에 걸리지 않는다. 그래서 이미 시공 중인
        #    사건에 제3업체를 붙일 수 있었고, 그 업체는 사건 소유자로 인정돼
        #    **영수증(낙찰가)까지 열람**하고(철칙 4) 사진을 올려 검수를 막았다.
        cs = conn.execute("SELECT status, partner_id, case_no, dispatch_status FROM cases WHERE id=?",
                          (case_id,)).fetchone()
        if not cs or cs[0] != "접수" or cs[1] is not None:
            conn.rollback()
            return False, (f"이 사건은 배정할 수 있는 상태가 아닙니다"
                           f"(현재 '{cs[0] if cs else '없음'}')."), None
        #  ⚠⚠ [라운드189] open_dispatch(313행)가 152라운드에 받은 가드가 직접배정에는
        #    빠져 있었다 — 이미 한 업체가 도착해 사진을 확보한 사건(dispatch_status=
        #    CS_PHOTO)도 cases.status·partner_id 는 1차 합의 승인 전까지 그대로라
        #    위 검사만으로는 안 잡힌다. arrive() 는 first_partner_id 를 조건 없이
        #    덮어쓰므로 나중에 배정된 업체가 먼저 도착한 업체를 밀어내고, dispatch_id
        #    없이 여는 1차 합의(open_agreement)는 가장 최근 도착 수배를 자동 선택하므로
        #    나중 업체의 견적이 보험사 승인 대상이 된다 — "선착순 한 곳만"이 이
        #    경로에서만 뒤집힌다. open_dispatch 와 같은 원칙으로 supersede 로도 못
        #    넘게 막는다(이미 확보된 사진·업체를 되돌릴 방법이 없다).
        if cs[3] == CS_PHOTO:
            conn.rollback()
            return False, "이미 다른 업체가 현장에 도착해 사진을 확보한 사건입니다. 1차 합의를 확인하세요.", None
        p = conn.execute("SELECT id, name, status, license_status FROM partners WHERE id=?",
                         (partner_id,)).fetchone()
        if not p:
            conn.rollback()
            return False, "없는 업체입니다.", None
        if p["status"] != "활성":
            conn.rollback()
            return False, f"활성 상태가 아닌 업체입니다({p['status']}).", None
        #  ⚠ 무등록 배제도 자동 수배 후보 쿼리에만 있었다. 출동은 1차 합의(직접 도급)로
        #    이어지므로 여기서 새면 무등록 업체가 실제 시공 배정을 받는다(건산법 §25②).
        if (p["license_status"] or "미확인") == "무등록":
            conn.rollback()
            return False, ("건설업 등록이 확인되지 않은 업체입니다. "
                           "도급 건에는 배정할 수 없습니다."), None
        prev = conn.execute(
            "SELECT COALESCE(MAX(round),0) FROM dispatches WHERE case_id=?", (case_id,)).fetchone()[0]
        mins = dispatch_minutes(conn)
        cur = conn.execute(
            """INSERT INTO dispatches(case_id, round, status, claimed_partner_id, claimed_name,
                                      claimed_at, due_at, created_at, fail_reason, is_demo)
               VALUES(?,?,?,?,?,datetime('now','+9 hours'),
                      datetime('now','+9 hours', ?), datetime('now','+9 hours'), ?,
                      COALESCE((SELECT is_demo FROM cases WHERE id=?),0))""",
            (case_id, prev + 1, ST_CLAIMED, partner_id, p["name"],
             f"+{mins} minutes", None, case_id))
        did = cur.lastrowid
        # 호출 기록도 남긴다 — '누구에게 갔는가'가 없으면 나중에 소명이 안 된다
        conn.execute(
            """INSERT OR IGNORE INTO dispatch_calls
                   (dispatch_id, partner_id, partner_name, call_order, response,
                    notified_at, responded_at, created_at)
               VALUES(?,?,?,?,?,datetime('now','+9 hours'),
                      datetime('now','+9 hours'), datetime('now','+9 hours'))""",
            (did, partner_id, p["name"], 1, "직접배정"))
        conn.execute("UPDATE cases SET dispatch_status=? WHERE id=?", (CS_MOVING, case_id))
        DB.log(conn, by or "운영자", "출동 직접배정",
               f"{cs[2]} · {p['name']} · {prev + 1}회차 · 사유: {reason[:80]}")
        conn.commit()
        #  밀려난 협력사가 있으면 배정이 끝난 뒤(트랜잭션 밖에서) 알린다 —
        #  ST_CLAIMED 였다면 이미 현장으로 오고 있을 수 있다(open_dispatch 와 같은 원칙).
        if live and live["claimed_partner_id"] and on_supersede:
            try:
                on_supersede(live["claimed_partner_id"], live["claimed_name"], live["id"], case_id)
            except Exception:
                _log.exception("밀려난 협력사 통지 실패 case=%s partner=%s",
                                case_id, live["claimed_partner_id"])
        return True, f"{p['name']}에 직접 배정했습니다. 도착 기한 {mins}분.", did
    except Exception:
        conn.rollback()
        raise


def claim(conn, dispatch_id, partner_id, partner_name=None):
    """선착순으로 출동을 잡는다. 반환 (성공여부, 메시지, 도착기한).

    ⚠ 이 함수가 이 모듈의 심장이다. 두 업체가 같은 순간 눌러도
      **정확히 한 곳만** 성공해야 한다. 조건부 UPDATE 의 rowcount 로만 판정한다.
    """
    mins = dispatch_minutes(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        d = conn.execute(
            "SELECT id, case_id, status, claimed_partner_id, is_demo FROM dispatches WHERE id=?",
            (dispatch_id,)).fetchone()
        if not d or int(d["is_demo"] or 0):
            conn.rollback()
            return False, "없는 수배입니다", None
        # 알림을 받은 업체만 잡을 수 있다(아무나 가로채지 못하게)
        called = conn.execute(
            "SELECT id FROM dispatch_calls WHERE dispatch_id=? AND partner_id=?",
            (dispatch_id, partner_id)).fetchone()
        if not called:
            conn.rollback()
            return False, "이 수배의 대상이 아닙니다", None

        #  ⚠ 사건이 살아 있는지 **여기서** 본다. 종전에는 cases 를 조회조차 하지 않아
        #    취소된 사건의 수배도 수락이 그대로 성공했다 — 업체는 출발하고, 도착해서야
        #    합의가 안 열린다는 걸 알게 된다.
        cs = conn.execute("SELECT status, partner_id, case_no FROM cases WHERE id=?",
                          (d["case_id"],)).fetchone()
        if not cs or cs[0] != "접수" or cs[1] is not None:
            conn.execute("UPDATE dispatches SET status=?, fail_reason=? "
                         " WHERE id=? AND status=?",
                         (ST_CANCELED, f"사건 종료({cs[0]})", dispatch_id, ST_OPEN))
            conn.commit()
            return False, "이 건은 종료돼 출동이 필요 없습니다. 현장으로 가지 마세요.", None

        # ★ 핵심 — '모집중'일 때만 성공. 이미 누가 잡았으면 rowcount 가 0 이다.
        cur = conn.execute(
            f"""UPDATE dispatches
                   SET status=?, claimed_partner_id=?, claimed_name=?,
                       claimed_at=datetime('now','+9 hours'),
                       due_at=datetime('now','+9 hours', '+{mins} minutes')
                 WHERE id=? AND status=? AND claimed_partner_id IS NULL""",
            (ST_CLAIMED, partner_id, partner_name or "", dispatch_id, ST_OPEN))
        if not cur.rowcount:
            conn.rollback()
            #  ⚠⚠ [라운드541] rowcount=0 은 "'모집중'이 아니다"는 뜻일 뿐인데, 이 함수는
            #    원인을 묻지 않고 늘 "이미 다른 업체가 출동을 맡았습니다"로만 답해 왔다.
            #    d["status"](BEGIN IMMEDIATE 뒤에 읽어 이 트랜잭션 동안은 바뀔 수 없다)가
            #    ST_FAILED(스윕이 제한시간 초과로 이미 마감, sweep_dispatches)이거나
            #    ST_CANCELED(운영자 직접배정이 이 수배를 걷어감, assign_dispatch)일 때도
            #    똑같이 "남이 맡았다"고 답하면, 실제로는 아무도 못 간 건인데 기사는
            #    "이미 딴 데서 갔다"고 오인해 현장에 안 간다 — 위 사건종료 분기(607행
            #    부근)가 이미 쓰는 원칙("진짜 이유를 그대로 말한다")을 여기도 적용한다.
            #    ST_ARRIVED·ST_CLAIMED(다른 업체)는 "남이 맡았다"가 사실 그대로이므로
            #    손대지 않는다.
            if d["status"] == ST_FAILED:
                return False, "이 수배는 응답 시간이 지나 이미 마감되었습니다.", None
            if d["status"] == ST_CANCELED:
                return False, "이 수배는 취소되었습니다. 현장으로 가지 마세요.", None
            return False, "이미 다른 업체가 출동을 맡았습니다", None

        conn.execute(
            """UPDATE dispatch_calls SET response='수락',
                      responded_at=datetime('now','+9 hours')
                WHERE dispatch_id=? AND partner_id=?""", (dispatch_id, partner_id))
        # 나머지는 '마감'으로 닫아, 눌러도 안 되는 이유가 화면에 남게 한다
        conn.execute(
            """UPDATE dispatch_calls SET response='마감'
                WHERE dispatch_id=? AND partner_id<>? AND response IS NULL""",
            (dispatch_id, partner_id))
        conn.execute("UPDATE cases SET dispatch_status=? WHERE id=?", (CS_MOVING, d["case_id"]))
        due = conn.execute("SELECT due_at FROM dispatches WHERE id=?", (dispatch_id,)).fetchone()[0]
        DB.log(conn, partner_name or f"협력사{partner_id}", "출동 수락",
               f"수배 {dispatch_id} · {cs[2]} · 기한 {due}")
        conn.commit()
        return True, f"출동을 맡았습니다. {mins}분 안에 현장 사진을 올려주세요.", due
    except Exception:
        conn.rollback()
        raise


def decline(conn, dispatch_id, partner_id):
    """거절 — 통계·재수배 판단에 쓴다.

    [E2E 결함 수정] 대상이 아닌 수배·이미 응답한 수배·없는 수배에 200 을 돌려주면
    호출자가 '거절이 기록됐다'고 오인한다. 갱신된 행이 없으면 False 를 돌려준다.

    ⚠⚠ [라운드279] 이 함수만 감사로그(DB.log)가 없었다 — 같은 파일의 형제
      (claim·arrive·close_no_repair 등)는 상태를 바꾸는 자리마다 전부 남긴다.
      그 결과 사건 상세의 감사이력(activity_log.detail LIKE '%사건번호%' —
      라운드94·117·190 이 지켜 온 바로 그 조회)·관리자 감사로그 화면·운영
      대시보드 최근활동 어디에도 "누가 언제 거절했는지"가 안 남았다 —
      dispatch_calls.response='거절' 자체는 남지만 사건번호로는 못 찾는다.
      재수배가 몇 회차나 걸렸는지 분쟁 시 소명하려 해도 거절 흔적만 빠진다.
      형제와 같은 자리(성공 시, commit 직전)에 남긴다.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        dm = conn.execute("SELECT case_id, is_demo FROM dispatches WHERE id=?",
                           (dispatch_id,)).fetchone()
        if not dm or int(dm["is_demo"] or 0):
            conn.rollback()
            return False
        cur = conn.execute(
            """UPDATE dispatch_calls SET response='거절',
                      responded_at=datetime('now','+9 hours')
                WHERE dispatch_id=? AND partner_id=? AND response IS NULL""",
            (dispatch_id, partner_id))
        if not cur.rowcount:
            conn.rollback()
            return False
        cs = conn.execute("SELECT case_no FROM cases WHERE id=?", (dm["case_id"],)).fetchone()
        DB.log(conn, f"협력사{partner_id}", "출동 거절",
               f"수배 {dispatch_id}" + (f" · {cs['case_no']}" if cs else ""))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise


def arrive(conn, dispatch_id, partner_id, photo_count, field_estimate=0):
    """도착 보고 — 현장 사진을 올렸다는 뜻. 반환 (성공여부, 메시지).

    ⚠ 사진이 0장이면 도착으로 인정하지 않는다. 사진을 받으려고 부른 것이기 때문이다.
    """
    if int(photo_count or 0) <= 0:
        return False, "현장 사진을 1장 이상 올려야 도착으로 인정됩니다"
    conn.execute("BEGIN IMMEDIATE")
    try:
        # 맡은 업체만, '수배됨' 상태일 때만 도착 처리
        cur = conn.execute(
            """UPDATE dispatches
                  SET status=?, outcome=?, arrived_at=datetime('now','+9 hours'),
                      photo_count=?, field_estimate=?
                WHERE id=? AND status=? AND claimed_partner_id=?
                  AND COALESCE(is_demo,0)=0""",
            (ST_ARRIVED, OUT_REPAIR, int(photo_count), int(field_estimate or 0),
             dispatch_id, ST_CLAIMED, partner_id))
        if not cur.rowcount:
            conn.rollback()
            return False, "출동을 맡은 상태가 아닙니다(기한이 지났을 수 있습니다)"
        d = conn.execute("SELECT case_id FROM dispatches WHERE id=?", (dispatch_id,)).fetchone()
        #  ★ **사건이 이미 다른 길로 갔으면 사건 쪽을 되돌리지 않는다.**
        #    claim() 에는 이 확인이 있는데(수락 직전 cases 재조회) arrive() 에만 없었다.
        #    2차 경매(입찰중)·낙찰(시공중)로 넘어간 뒤 도착 보고가 들어오면
        #    dispatch_status 가 '사진확보' 로 되돌아가 운영 목록·집계가 어긋나고,
        #    발주처에는 오지 않을 "곧 승인 요청이 올라갑니다" 알림이 또 나간다.
        #    ⚠ 수배 행은 이미 '도착' 으로 기록했다 — 기사는 실제로 갔고, 잘못이 없다.
        _cs = conn.execute("SELECT status, partner_id, case_no FROM cases WHERE id=?",
                           (d["case_id"],)).fetchone()
        if not _cs or _cs["status"] != "접수" or _cs["partner_id"] is not None:
            DB.log(conn, f"협력사{partner_id}", "현장 도착(사건은 이미 진행)",
                   f"수배 {dispatch_id}"
                   + (f" · {_cs['case_no']}" if _cs else "")
                   + f" · 사건 상태 '{_cs['status'] if _cs else '없음'}'")
            conn.commit()
            return True, ("도착 보고는 기록했습니다. 다만 이 사건은 이미 다른 절차로 "
                          "넘어가 있어 현장 진행은 운영팀 확인이 필요합니다.")
        # 사건에 '사진 확보'와 '최초 출동업체'를 남긴다.
        #  최초 출동업체는 뒤에 1차 합의 상대이자, 결렬 시에도 사진 제공자로 기록에 남는다.
        conn.execute(
            """UPDATE cases SET dispatch_status=?, first_partner_id=?,
                      first_photo_at=datetime('now','+9 hours')
                WHERE id=?""", (CS_PHOTO, partner_id, d["case_id"]))
        DB.log(conn, f"협력사{partner_id}", "현장 도착·사진 등록",
               f"수배 {dispatch_id} · {_cs['case_no']} · 사진 {photo_count}장 · "
               f"실견적 {int(field_estimate or 0):,}원")
        conn.commit()
        return True, "도착 보고가 접수됐습니다"
    except Exception:
        conn.rollback()
        raise


# ── 제한시간 초과 정리 ────────────────────────────────────────────
def _claim_lease(conn):
    #  ⚠⚠ [라운드482] 이 파일의 다른 BEGIN IMMEDIATE 10곳은 전부 try/except로
    #    감싸는데 여기만 없었다 — 호출부(sweep_dispatches, 766행)도 이 호출을
    #    자기 자신의 try 블록(770행) 밖에서 하므로, UPDATE가 예외를 던지면
    #    (락 경합으로 busy-timeout 초과, 디스크 오류 등 — 이 리스 자체가
    #    "겹친 예약실행을 막는" 용도라 락 경합이 바로 이 자리에서 가장
    #    일어나기 쉽다) sweep_dispatches() 밖까지 그대로 터져 manage.py
    #    cmd_sweep()의 유일한 try(1001행)에도 except가 없어 그 회차의
    #    sweep_send_notifications·sweep_webhook_retries·생존신호(job_locks
    #    cli_sweep)까지 통째로 건너뛴다. 형제 _release_lease()(바로 아래)와
    #    같은 원칙 — 리스 확보 실패는 5분 뒤 다음 예약실행이 다시 시도하면
    #    회복되는 문제라, 예외를 삼키고 "다른 워커가 이미 리스를 쥐고 있다"는
    #    호출부의 기존 정상 경로(claimed=False)로 합류시킨다. rollback은
    #    이 함수만의 고유 필요(BEGIN IMMEDIATE를 직접 여는 유일한 자리라
    #    커밋 안 된 트랜잭션을 반드시 닫아야 다음 BEGIN IMMEDIATE가
    #    "cannot start a transaction" 으로 안 터진다 — 411라운드가 이미
    #    겪은 것과 같은 클래스).
    #  ⚠⚠ [라운드524] 482라운드가 try/except를 씌우면서 정작 "가장 일어나기
    #    쉽다"고 스스로 적어 둔 그 자리 — BEGIN IMMEDIATE 문 자체 — 를 try
    #    **밖**에 남겨 뒀다. 락 경합으로 busy-timeout(db.py PRAGMA
    #    busy_timeout)이 넘으면 UPDATE가 아니라 이 BEGIN IMMEDIATE 문에서
    #    먼저 sqlite3.OperationalError("database is locked")가 나는데, 그건
    #    여전히 무방비였다(round482의 자체 회귀 테스트도 job_locks 테이블을
    #    지워 UPDATE만 실패시켰지 BEGIN IMMEDIATE 자체를 실패시키진 않아
    #    이 구멍을 못 잡았다). 형제 app.py _sweep_claim()(round523)은 처음부터
    #    BEGIN IMMEDIATE를 try 안에 넣어 이 구멍이 없다 — 그 모양대로 맞춘다.
    #    rollback도 형제처럼 자체 try/except로 감싼다: BEGIN IMMEDIATE 자체가
    #    실패했을 때는 열린 트랜잭션이 없어 rollback이 무의미(경우에 따라
    #    추가 예외)할 수 있기 때문.
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE job_locks SET lease_until = datetime('now','+9 hours', ?) "
            " WHERE name='dispatch_sweep' AND lease_until <= datetime('now','+9 hours')",
            (f"+{SWEEP_LEASE_SEC} seconds",))
        if not cur.rowcount:
            conn.rollback()
            return False
        conn.commit()
        return True
    except sqlite3.Error:
        _log.exception("dispatch_sweep 리스 확보 실패 — 이번 회차는 건너뛰고 다음 예약실행이 재시도함")
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        return False


def _release_lease(conn, note):
    #  ⚠⚠ [라운드279] 형제 셋(위 세 곳)은 실패를 전부 _log.exception 으로 남기는데
    #    여기만 완전 침묵했다 — 리스 해제 실패 자체는 120초 뒤 자연만료로 회복되니
    #    급하지 않지만, 침묵이면 반복 실패해도 아무도 모른다.
    try:
        conn.execute(
            "UPDATE job_locks SET lease_until='1970-01-01 00:00:00', "
            "       last_run_at = datetime('now','+9 hours'), last_note=? "
            " WHERE name='dispatch_sweep'", (str(note)[:200],))
        conn.commit()
    except sqlite3.Error:
        _log.exception("dispatch_sweep 리스 해제 실패 — 120초 뒤 자연만료로 복구됨")


def sweep_dispatches(conn, limit=SWEEP_LIMIT, dry_run=False, force=False, notify=None):
    """제한시간이 지난 수배를 실패 처리하고, 다음 회차를 자동으로 연다.

    이것이 없으면 한 업체가 수락만 하고 안 가는 순간 **사건이 영원히 멈춘다.**
    """
    res = {"claimed": True, "expired": 0, "reopened": 0, "gaveup": 0, "dry_run": bool(dry_run)}

    mins = dispatch_minutes(conn)
    #  ⚠⚠ [라운드257] claim()·decline()·arrive()·close_no_repair() 는 전부
    #    COALESCE(is_demo,0)=0 을 CAS 조건에 걸어 데모 수배를 거부하는데, 이
    #    자동순회의 유일한 진입점인 스윕 자신만 그 필터가 없었다 — 개발 DB엔
    #    데모 수배가 늘 몇 건 존재하는 게 정상 상태인데(코드 자신의 주석이
    #    실측치를 남겨 둠), 데모 수배는 claim() 이 항상 거부하므로 시간초과
    #    (여기)로만 끝난다. 그 결과 이 스윕이 매 회차 open_dispatch() 를 다시
    #    불러 그 지역·공종의 **실제 활성 협력사**에게 실제 문자/알림톡을
    #    보내고(회차 상한까지 반복), 감사로그에도 실활동과 구분 안 되는
    #    "출동 실패" 기록을 남겼다 — 형제 스윕(sweep_auctions, 254라운드)과
    #    같은 유형의 데모오염을 표식을 만드는 자리에서 막는다.
    #  ⚠ AND 가 OR 보다 결합력이 세다 — 괄호 없이 이어 붙이면 is_demo 조건이
    #    OR 의 오른쪽 가지에만 걸려 나머지 절반(제한시간 초과)은 여전히
    #    새어 나간다. 전체 OR 식을 한 번 더 괄호로 묶어야 둘 다 걸린다.
    n = conn.execute(
        f"""SELECT COUNT(*) FROM dispatches
             WHERE ((status=? AND {DISPATCH_OVERDUE_SQL})
                OR (status=? AND {DISPATCH_UNCLAIMED_SQL}))
               AND COALESCE(is_demo,0)=0""",
        (ST_CLAIMED, ST_OPEN, mins)).fetchone()[0]
    if not n:
        # 대상이 0건이어도 '점검이 돌았다'는 사실은 남긴다(생존 신호).
        if not dry_run:
            _release_lease(conn, "대상 없음")
        return res
    if not (dry_run or force or _claim_lease(conn)):
        res["claimed"] = False
        return res

    try:
        #  ⚠⚠ [라운드95] case_no 를 스칼라 서브쿼리로 함께 끌어온다(JOIN 대신 —
        #    dispatches·cases 둘 다 status/created_at 이 있어 JOIN 은 위 SQL
        #    상수들의 별칭 없는 컬럼명과 충돌한다). 아래 두 DB.log 가 detail 에
        #    사건을 "사건 {case_id}"(숫자 PK)로 남기면 사건 이력 리포트·정산 상세의
        #    감사로그 타임라인(둘 다 case_no 문자열로 LIKE 검색)에서 영원히 안 잡힌다.
        targets = conn.execute(
            f"""SELECT id, case_id, round, claimed_partner_id, status,
                       (SELECT case_no FROM cases WHERE id=dispatches.case_id) AS case_no
                  FROM dispatches
                 WHERE ((status=? AND {DISPATCH_OVERDUE_SQL})
                    OR (status=? AND {DISPATCH_UNCLAIMED_SQL}))
                   AND COALESCE(is_demo,0)=0
                 ORDER BY id LIMIT ?""", (ST_CLAIMED, ST_OPEN, mins, limit)).fetchall()
        if dry_run:
            res["expired"] = len(targets)
            return res

        max_round = dispatch_max_round(conn)
        for t in targets:
            conn.execute("BEGIN IMMEDIATE")
            try:
                was_open = (t["status"] == ST_OPEN)
                why = "아무도 수락하지 않음" if was_open else "제한시간 내 미도착"
                cur = conn.execute(
                    "UPDATE dispatches SET status=?, fail_reason=? WHERE id=? AND status=?",
                    (ST_FAILED, why, t["id"], t["status"]))
                if not cur.rowcount:
                    conn.rollback()
                    continue
                # 맡고도 안 간 업체는 기록에 남긴다(반복되면 수배 대상에서 뺄 근거).
                #  아무도 수락 안 한 건은 **부른 업체 전부**가 무응답이다.
                if was_open:
                    conn.execute(
                        """UPDATE dispatch_calls SET response='무응답'
                            WHERE dispatch_id=? AND response IS NULL""", (t["id"],))
                else:
                    conn.execute(
                        """UPDATE dispatch_calls SET response='무응답'
                            WHERE dispatch_id=? AND partner_id=?""",
                        (t["id"], t["claimed_partner_id"]))
                DB.log(conn, "시스템", "출동 실패",
                       f"수배 {t['id']} · {t['case_no']} · {why}")
                conn.commit()
            except Exception:
                #  ⚠⚠ [라운드558] 같은 루프의 형제 셋(여기·922행 회차소진·942행
                #    재수배) 중 942행(라운드182·411)만 "대상 하나의 실패가
                #    나머지 전부의 처리를 막아선 안 된다"는 원칙(이 함수
                #    docstring 이 스스로 못박은 존재 이유)으로 이미 고쳐져
                #    있었는데, 여기는 raise 로 남아 스윕 전체를 끊었다 — 이
                #    루프뿐 아니라 manage.py cmd_sweep()(라운드557이 지적한
                #    바로 그 경로)까지 뚫고 나가, 대상 하나의 일시적 락 경합
                #    때문에 무입찰경보~웹훅재전송·cli_sweep 생존신호까지 이번
                #    회차 전부 건너뛰게 만든다. 바로 세 줄 위(899행) 자신의
                #    CAS-미스 분기와 같은 처방 — rollback 후 continue, 이
                #    대상은 다음 예약실행이 아니라 여전히 조건에 걸리면
                #    **이번 스윕**에서 이미 처리된 나머지 뒤로도 다시 온다.
                conn.rollback()
                _log.exception("출동 실패 처리 실패 dispatch=%s", t["id"])
                continue
            res["expired"] += 1

            # 다음 회차를 연다 — 회차 상한을 넘으면 사람이 개입해야 한다
            if int(t["round"] or 1) >= max_round:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute("UPDATE cases SET dispatch_status=? WHERE id=?",
                                 (CS_FAILED, t["case_id"]))
                    DB.log(conn, "시스템", "출동수배 중단",
                           f"{t['case_no']} · {max_round}회차까지 실패 — 사람 개입 필요")
                    conn.commit()
                    res["gaveup"] += 1
                except Exception:
                    #  ⚠⚠ [라운드558] 형제(942행 재수배 처리기, 라운드182·411)와
                    #    같은 원칙 — 이 대상의 출동 자체는 이미 별도 트랜잭션
                    #    (897행)에서 '실패'로 확정 커밋된 뒤다. 사건 차원의
                    #    CS_FAILED 전환(이 블록)만 실패했다고 raise 로 스윕
                    #    전체(나머지 대상 + manage.py cmd_sweep 의 이후 단계들,
                    #    라운드557)를 끊을 이유가 없다 — res["gaveup"] 도 성공
                    #    시에만 세도록 try 안으로 옮겼다(실패했는데 세면 실제로
                    #    안 바뀐 사건을 '중단 처리됨'으로 잘못 보고한다).
                    conn.rollback()
                    _log.exception("출동수배 중단 처리 실패 case=%s", t["case_id"])
            else:
                try:
                    did, cnt, sent = open_dispatch(conn, t["case_id"], notify=notify)
                    if cnt:
                        res["reopened"] += 1
                    if cnt and not sent:
                        # 다시 열긴 했는데 아무에게도 못 알렸다 — 사람이 봐야 한다
                        res["notify_failed"] = res.get("notify_failed", 0) + 1
                except Exception:
                    #  ⚠⚠ [라운드182] t 는 dict 가 아니라 sqlite3.Row(710행 fetchall,
                    #    conn.row_factory=Row) 다 — .get() 이 없어 여기 도달하면
                    #    AttributeError 로 원래 예외를 덮어쓰고, 이 함수 끝의 바깥
                    #    try(776행)까지 뚫고 나가 **남은 대상 전부**의 재수배를
                    #    통째로 멈춘다(로그하고 다음 건으로 넘어가야 할 자리가
                    #    반대로 전체를 끊는 자리가 된다). 같은 루프의 다른 모든
                    #    접근(725·729·744·753·757 행 등)처럼 대괄호로 맞춘다.
                    #  ⚠⚠ [라운드411] rollback 이 없었다 — open_dispatch() 안에서
                    #    커밋 안 된 암시적 트랜잭션을 남긴 채 예외가 여기로 오면,
                    #    그대로 다음 대상으로 넘어가 그 대상의 BEGIN IMMEDIATE
                    #    (775행)가 "cannot start a transaction within a
                    #    transaction" 으로 죽는다 — 이 except 자신이 막으려던
                    #    바로 그 사고(남은 대상 전부의 재수배 중단)가 rollback
                    #    누락 때문에 뒷문으로 재현됐다. 트랜잭션이 안 열려 있어도
                    #    rollback() 은 그냥 아무 일도 안 한다(무해).
                    conn.rollback()
                    _log.exception("자동 재수배 실패 case=%s", t["case_id"])
        _release_lease(conn, f"만료{res['expired']} 재수배{res['reopened']} 중단{res['gaveup']}")
    except Exception:
        _release_lease(conn, "오류")
        raise
    return res


# ══════════════════════════════════════════════════════════════
#  미수선 종결 — 현장에 가 보니 공사를 하지 않고 끝나는 경우
#
#  왜 필요한가 — 현장에 나가 보면 수선하지 않고 끝나는 건이 실제로 있다.
#  피해자가 원치 않거나, 파손이 경미하거나, 이미 복구됐거나, 자기 부담으로 처리한다.
#  이 결과를 입력할 칸이 없으면 출동 업체는 아무 것도 못 하고,
#  사건은 '출동은 했는데 아무 일도 없는' 상태로 떠 있게 된다.
#  나중에 왜 공사가 없었는지 아무도 설명하지 못한다.
#
#  ⚠ 미수선은 실패가 아니라 **정상 종결의 한 갈래**다. 통계에서도 그렇게 다룬다.
#  ⚠ 복구온은 손해사정을 하지 않는다. 여기서 남기는 것은 '현장에서 공사를 하지 않기로
#    했다'는 사실이지, 보험금을 지급하지 않는다는 판단이 아니다. 그 판단은 보험사 몫이다.
# ══════════════════════════════════════════════════════════════
OUT_REPAIR = "수선진행"
OUT_NO_REPAIR = "미수선종결"

# 현장에서 고르는 사유. 자유 기재만 두면 제각각이라 나중에 집계가 안 된다.
NO_REPAIR_REASONS = [
    "피해자가 수선을 원치 않음",
    "파손이 경미해 수선 불필요",
    "이미 복구됨(타 업체·자체 처리)",
    "피해자 자기부담으로 처리",
    "피해물이 우리 대상이 아님",
    "현장에서 피해 확인 불가",
    "기타",
]


def close_no_repair(conn, dispatch_id, partner_id, reason, note="", by=""):
    """미수선으로 종결한다. 반환 (성공여부, 메시지).

    출동을 맡은 업체가 현장에서 피해자와 이야기한 결과를 그대로 입력한다.
    """
    reason = (reason or "").strip()
    if reason not in NO_REPAIR_REASONS:
        return False, f"사유를 목록에서 골라주세요: {', '.join(NO_REPAIR_REASONS)}"
    if reason == "기타" and not (note or "").strip():
        return False, "'기타'를 고르면 현장 설명을 적어주세요."

    conn.execute("BEGIN IMMEDIATE")
    try:
        # 출동을 맡았거나 이미 도착한 상태에서만 종결할 수 있다.
        #  (도착 전이라도 현장에서 바로 미수선이 확인될 수 있어 '수배됨'도 허용한다)
        # [E2E 결함 수정] 이미 미수선으로 종결된 건의 재호출을 거절한다.
        #  종전에는 '도착' 상태를 허용하는 조건이 종결 후 재호출까지 통과시켜
        #  사유·메모·담당자가 소리 없이 덮어써졌다(감사 기록 훼손).
        cur = conn.execute(
            """UPDATE dispatches
                  SET status=?, outcome=?, no_repair_reason=?, no_repair_note=?,
                      no_repair_by=?, no_repair_at=datetime('now','+9 hours'),
                      arrived_at=COALESCE(arrived_at, datetime('now','+9 hours'))
                WHERE id=? AND claimed_partner_id=? AND status IN (?,?)
                  AND COALESCE(outcome,'') <> ? AND COALESCE(is_demo,0)=0""",
            (ST_ARRIVED, OUT_NO_REPAIR, reason, (note or "")[:500], (by or "")[:60],
             dispatch_id, partner_id, ST_CLAIMED, ST_ARRIVED, OUT_NO_REPAIR))
        if not cur.rowcount:
            conn.rollback()
            return False, "출동을 맡은 상태가 아닙니다(기한이 지났을 수 있습니다)."

        #  ⚠⚠ [라운드95] case_no 도 함께 끌어온다(아래 DB.log 의 사건번호 형식
        #    일치 — 94라운드의 settle_agreement 와 같은 결함).
        d = conn.execute(
            "SELECT dp.case_id, c.case_no FROM dispatches dp JOIN cases c ON c.id = dp.case_id "
            " WHERE dp.id=?", (dispatch_id,)).fetchone()
        # 사건을 종결로 옮긴다. 경매를 열지 않는다.
        #  ★ **아직 아무도 배정되지 않은 사건만** 종결할 수 있다.
        #    예전에는 조건이 없어서, 1차 합의 승인이나 2차 낙찰로 이미 다른 업체가
        #    시공 중인 사건까지 최초 출동업체가 뒤집을 수 있었다. 그러면
        #    완료 보고(시공중/완료보고지연 요구)도 검수 승인(검수대기 요구)도 막혀
        #    **시공한 업체가 대금을 못 받는 영구 교착**이 된다. 이미 만들어진 정산과
        #    사건 상태가 서로 다른 말을 하기도 한다.
        cur2 = conn.execute(
            """UPDATE cases SET status='미수선종결', status_at=datetime('now','+9 hours'), dispatch_status=?,
                      no_repair_reason=?, award_route='미수선'
                WHERE id=? AND status='접수' AND partner_id IS NULL""",
            (CS_PHOTO, reason, d["case_id"]))
        if not cur2.rowcount:
            conn.rollback()
            return False, ("이미 업체가 배정됐거나 진행 중인 사건입니다. "
                           "운영팀에 문의해 주세요.")
        #  ⚠⚠ [라운드190] **검토중인 1차 합의를 여기서 함께 닫는다** — 2차 경매
        #    개시(app.py api_case_open_auction, 15009행 부근)가 이미 같은 이유로
        #    하는 일이다. 안 닫으면 보험사 승인 대기열은 사건이 '접수'가 아닌
        #    동안만 숨을 뿐이고, 되돌리기(undo-no-repair)가 사건을 다시 '접수'로
        #    돌리는 순간 이 낡은 합의가 대기열에 부활한다. 보험사가 그 사이 상황이
        #    바뀐 줄 모르고 승인하면 settle_agreement 의 재확인(사건상태·업체
        #    활성·면허)은 전부 통과해 낡은 견적 그대로 낙찰이 확정된다 — 미수선
        #    종결이 이 정리를 빠뜨리고 있었다.
        _hung = conn.execute(
            """UPDATE field_agreements
                  SET status=?, decided_at=datetime('now','+9 hours'),
                      reject_reason='미수선 종결로 자동 종료'
                WHERE case_id=? AND status=?""",
            (AG_BROKEN, d["case_id"], AG_REVIEW)).rowcount
        if _hung:
            DB.log(conn, "시스템", "1차 합의 자동 종료",
                   f"{d['case_no']} · 미수선 종결로 검토중 {_hung}건 종료")
        #  ⚠⚠ **행위자는 상대방이 정하지 않는다.**
        #    `by` 는 세션이 아니라 요청 본문에서 온다(화면의 prompt 입력값).
        #    그걸 감사로그의 actor 로 그대로 넣으면, 되돌리기 어려운 종결 행위의
        #    기록에 '운영팀 OOO' 같은 아무 문자열이나 남길 수 있다 —
        #    분쟁 때 로그가 근거가 아니라 **반증거**가 된다.
        #    actor 는 시스템이 아는 주체로 고정하고, 사람이 적어 준 이름은
        #    detail 에 **'현장 확인자' 라는 이름표를 붙여** 남긴다(길이도 자른다).
        _who = (by or "").strip()[:60]
        DB.log(conn, f"협력사{partner_id}", "미수선 종결",
               f"수배 {dispatch_id} · {d['case_no']} · 사유: {reason}"
               + (f" · 현장 확인자(자기신고): {_who}" if _who else ""))
        conn.commit()
        return True, "미수선으로 종결됐습니다. 보험사에 결과가 전달됩니다."
    except Exception:
        conn.rollback()
        raise


# ══════════════════════════════════════════════════════════════
#  1차 합의 — 출동 업체의 실견적으로 보험사와 먼저 맞춰본다
#
#  왜 있나 — 소액 공사가 대부분인데 매 건 경매를 돌리면 시간·비용이 더 든다.
#  이미 현장에 다녀온 업체가 낸 견적이 표준단가 구간 안이면, 그대로 시공하는 것이
#  가장 빠르고 싸다. 합의가 안 되면 그때 경매로 간다.
#
#  ⚠ 반드시 지킬 선
#   · 여기서 정하는 것은 **시공 도급 금액**이지 보험금이 아니다.
#     보험금 지급액 확정은 보험사 몫이며, 우리는 '이 공사를 이 금액에 하겠다'를 맞춘다.
#   · **자동으로 합의되지 않는다.** 사람(우리 담당 ↔ 보상 담당)이 결정하고,
#     이 함수는 그 결정을 기록할 뿐이다.
#   · 표준단가 엔진의 개산 구간을 참고로 함께 남겨, 왜 그 금액이 타당한지가 보이게 한다.
# ══════════════════════════════════════════════════════════════
AG_REVIEW = "검토중"
AG_DONE = "합의"
AG_BROKEN = "결렬"


def open_agreement(conn, case_id, dispatch_id=None, engine_low=0, engine_high=0,
                   our_staff="", insurer_staff="", basis=None):
    """도착한 수배의 실견적을 놓고 1차 합의 검토를 연다. 반환 agreement_id.

    basis = {"pattern","inputs","basis","ver"} — **서버가 직접 계산한** 개산 근거.
      호출자가 넘긴 engine_low/high 는 그 계산 결과여야 한다(요청 본문 값을 그대로
      흘려보내면 근거 기록이 위조 가능해진다).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        d = conn.execute(
            """SELECT id, claimed_partner_id, claimed_name, field_estimate, status
                 FROM dispatches
                WHERE case_id=? AND status=? ORDER BY id DESC LIMIT 1""",
            (case_id, ST_ARRIVED)).fetchone() if dispatch_id is None else conn.execute(
            """SELECT id, claimed_partner_id, claimed_name, field_estimate, status
                 FROM dispatches WHERE id=?""", (dispatch_id,)).fetchone()
        if not d or d["status"] != ST_ARRIVED:
            conn.rollback()
            return None
        #  ★ 사건이 이미 다른 경로로 확정됐으면 1차 합의를 다시 열지 않는다.
        #    부동의 → 2차 경매 → 다른 업체 낙찰(시공중) 이 된 뒤에도 수배 화면의
        #    '견적 원문 승인 요청' 버튼이 살아 있어서, 한 번 더 누르면 출동 업체 명의로
        #    승인 요청이 보험사 대기열에 다시 떴다. 보험사가 승인하는 순간
        #    **시공 중인 업체와 낙찰금액이 경고 없이 덮어써지고** 정산까지 엉뚱해진다.
        #    돌이킬 수 없는 덮어쓰기라 여기서 막는다(라우트가 None 을 409 로 돌려준다).
        #  ⚠⚠ [라운드95] case_no 도 함께 끌어온다(아래 DB.log 의 사건번호 형식
        #    일치 — 94라운드의 settle_agreement 와 같은 결함).
        c = conn.execute("SELECT status, partner_id, case_no FROM cases WHERE id=?",
                         (case_id,)).fetchone()
        if not c or c["partner_id"] is not None or c["status"] != "접수":
            conn.rollback()
            return None
        # 이미 검토 중인 합의가 있으면 그것을 쓴다(중복 생성 방지)
        ex = conn.execute(
            "SELECT id FROM field_agreements WHERE case_id=? AND status=?",
            (case_id, AG_REVIEW)).fetchone()
        if ex:
            conn.rollback()
            return ex[0]
        #  ⚠ 부동의(결렬)는 2차 경매로 가는 **한쪽 문**이다(바로 아래 settle_agreement
        #    의 '결렬 — 2차 경매로 간다' 참고, award_route='경매'로 남긴다). 그런데
        #    수배(dispatch)는 여전히 '도착' 상태라 화면의 '발주처에 승인 요청' 버튼이
        #    안 사라진다 — 운영자가 다시 누르면 반려 이력이 안 보이는 채로 같은 사건에
        #    1차 합의가 다시 열려, 2차 경매와 동시에 두 경로가 같은 사건을 놓고 돈다.
        #    위의 사건 상태 가드와 같은 원칙으로, 여기서도 막는다.
        broken = conn.execute(
            "SELECT id FROM field_agreements WHERE case_id=? AND status=?",
            (case_id, AG_BROKEN)).fetchone()
        if broken:
            conn.rollback()
            return None
        b = basis or {}
        cur = conn.execute(
            #  ⚠ 데모 표식을 사건에서 물려받는다. 이 표를 거르는 조건이 발주처
            #    포털 승인 대기 목록에 있는데, 채우는 코드가 없어 **데모 사건의
            #    현장 견적 2건이 실제 발주처 승인 대기에 떠 있었다.**
            """INSERT INTO field_agreements
                   (case_id, dispatch_id, partner_id, partner_name, field_amount,
                    engine_low, engine_high, status, our_staff, insurer_staff, created_at,
                    engine_pattern, engine_inputs, engine_basis, engine_ver, engine_at, is_demo)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                      COALESCE((SELECT is_demo FROM cases WHERE id=?),0))""",
            (case_id, d["id"], d["claimed_partner_id"], d["claimed_name"] or "",
             int(d["field_estimate"] or 0), int(engine_low or 0), int(engine_high or 0),
             AG_REVIEW, our_staff or "", insurer_staff or "", DB.now(),
             b.get("pattern"), b.get("inputs"), b.get("basis"), b.get("ver"),
             DB.now() if b.get("basis") else None, case_id))
        aid = cur.lastrowid
        eng = (f" · 개산 {int(engine_low or 0):,}~{int(engine_high or 0):,}원"
               f"({b.get('pattern')}/{b.get('ver')})") if b.get("basis") else " · 개산근거 없음"
        DB.log(conn, our_staff or "시스템", "1차 합의 개시",
               f"{c['case_no']} · 실견적 {int(d['field_estimate'] or 0):,}원{eng}")
        conn.commit()
        return aid
    except Exception:
        conn.rollback()
        raise


def license_block_reason(conn, partner_id):
    """건설업 무등록 여부만 본다. 막을 이유가 있으면 문자열, 없으면 None.

    ⚠ 무등록 배제는 지금까지 **진입 문**에만 있었다(candidates 후보선정·
      assign_dispatch 직접배정·통값입찰·재경매입찰). 그런데 낙찰이 **확정되는**
      자리(원경매 낙찰 2곳·전체재경매 마감·1차 합의 승인)는 하나도 다시 보지
      않았다 — 선택과 확정 사이(수배 30분, 보험사 승인 대기 수일)에 조사 결과가
      '무등록'으로 확정될 수 있는데, 그 사실이 확정된 뒤에도 도급이 그대로
      내려갔다(건설산업기본법 §25조 제2항). 새 낙찰 경로를 추가하면 반드시
      여기부터 부른다. '미확인'(아직 조사 안 함)은 막지 않는다.
    """
    p = conn.execute("SELECT license_status FROM partners WHERE id=?",
                     (partner_id,)).fetchone()
    if p and (p["license_status"] or "미확인") == "무등록":
        return ("건설업 등록이 확인되지 않은 업체입니다. "
                "도급 건에는 배정할 수 없습니다(건설산업기본법 제25조 제2항).")
    return None


def settle_agreement(conn, agreement_id, agreed, amount=0, note="", actor="",
                     approver=None):
    """1차 합의 결과를 기록한다. 반환 (성공여부, 메시지).

    agreed=True  → 보험사 승인. 사건은 그 업체에게 배정된다(경매 없이).
    agreed=False → 보험사 부동의. 사건은 2차 경매로 넘어갈 수 있는 상태가 된다.

    ★ 법률 철칙 — **금액을 정하는 주체는 보험사다.**
      · approver 없이 호출하면 거부한다(운영자 단독 확정 차단).
      · 금액은 출동 업체가 낸 실견적(field_amount)으로 **고정**한다. 운영자든 누구든
        중간에서 금액을 만들어 넣을 수 없다(그 행위가 손해사정·합의대행에 닿는다).
      approver = {"org_id","user_id","name","role"}  — 로그인 계정에서 채운다.

    ⚠ 이 함수는 낙찰 자체는 만들지 않는다. 사건 배정(시공중 전환)은 호출자(라우트)가
      기존 낙찰 흐름과 같은 방식으로 처리한다.
    """
    if agreed and not (approver and approver.get("org_id")):
        return False, ("합의 확정은 보험사 계정의 승인으로만 가능합니다. "
                       "운영자는 견적 원문을 전달할 수 있을 뿐입니다.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        #  ⚠⚠ [라운드94] case_no 를 함께 끌어온다 — 이 함수의 DB.log 는 detail 에
        #    사건을 "사건 {case_id}"(숫자 PK)로 남겼는데, /report/case/<cid>·
        #    정산 상세의 감사로그 타임라인은 둘 다 detail 을 case_no("26-xxxxx")
        #    문자열로 LIKE 검색한다 — 형식이 아예 안 겹쳐서 이 함수가 남기는
        #    승인/부동의 기록(승인자 이름·직급 포함, 분쟁 시 필요한 바로 그 증거)이
        #    두 화면 모두에서 영원히 안 잡혔다(실측: 승인 기록을 남긴 뒤 리포트를
        #    직접 열어 보면 "남은 감사 기록이 없습니다"만 뜬다). app.py 쪽 DB.log는
        #    전부 case_no 를 쓰는 게 이미 확립된 관례라 그 관례에 맞춘다.
        a = conn.execute(
            "SELECT fa.id, fa.case_id, fa.partner_id, fa.partner_name, fa.status, "
            "       fa.field_amount, c.case_no "
            "  FROM field_agreements fa JOIN cases c ON c.id = fa.case_id WHERE fa.id=?",
            (agreement_id,)).fetchone()
        if not a:
            conn.rollback()
            return False, "없는 합의 건입니다"
        if a["status"] != AG_REVIEW:
            conn.rollback()
            return False, f"이미 처리된 건입니다({a['status']})"
        # 금액은 실견적 고정 — 인자로 온 amount 는 무시한다(위조·임의조정 차단)
        amount = int(a["field_amount"] or 0)
        if agreed and amount <= 0:
            conn.rollback()
            return False, "출동 업체의 실견적이 없어 승인할 수 없습니다"

        ap = approver or {}
        cur = conn.execute(
            """UPDATE field_agreements
                  SET status=?, agreed_amount=?, proposed=?, note=?,
                      decided_at=datetime('now','+9 hours'),
                      approver_org_id=?, approver_user_id=?, approver_name=?, approver_role=?,
                      approved_at=CASE WHEN ?=1 THEN datetime('now','+9 hours') ELSE NULL END,
                      reject_reason=CASE WHEN ?=1 THEN NULL ELSE ? END
                WHERE id=? AND status=?""",
            (AG_DONE if agreed else AG_BROKEN, amount if agreed else 0, amount,
             (note or "")[:500],
             ap.get("org_id"), ap.get("user_id"), ap.get("name"), ap.get("role"),
             1 if agreed else 0, 1 if agreed else 0, (note or "")[:500],
             agreement_id, AG_REVIEW))
        if not cur.rowcount:
            conn.rollback()
            return False, "상태가 바뀌어 처리하지 못했습니다"

        if agreed:
            #  ⚠ **사건이 아직 그 자리에 있는지 먼저 본다.**
            #    보험사가 며칠 응답하지 않는 동안 운영자가 2차 경매를 열어 다른 업체가
            #    낙찰·시공에 들어갈 수 있다. 그 뒤 보험사가 옛 대기열에서 이 건을 승인하면,
            #    아래 UPDATE 가 시공사·낙찰금액을 통째로 덮어써 **한 현장에 두 업체**가 되고,
            #    실제 시공자는 자기 사건을 못 찾아 완료보고·정산이 영영 막힌다.
            #    (같은 파일 claim·sweep·open_dispatch 는 모두 이 방식으로 이미 막고 있다)
            cs = conn.execute(
                "SELECT status, partner_id, partner_name FROM cases WHERE id=?",
                (a["case_id"],)).fetchone()
            if not cs:
                conn.rollback()
                return False, "사건을 찾을 수 없습니다."
            if cs["status"] != "접수" or cs["partner_id"] is not None:
                conn.rollback()
                return False, (
                    f"이 사건은 이미 다른 방식으로 진행됐습니다"
                    f"(현재 상태 '{cs['status']}'"
                    + (f" · 담당 {cs['partner_name']}" if cs["partner_name"] else "")
                    + "). 1차 합의로 되돌릴 수 없으니 운영팀에 문의해 주세요.")

            #  ⚠ 출동 업체의 자격은 **수배를 잡은 그 순간에만** 봤다(claim). 승인은
            #    보험사가 며칠씩 걸려 누르므로, 그 사이 업체가 경고·퇴출되거나
            #    조사로 '무등록'이 확정될 수 있다 — 이 함수가 여기서 다시 보지
            #    않으면 그 사실을 이미 알고도 도급을 내리는 것이 된다.
            pt = conn.execute("SELECT status FROM partners WHERE id=?",
                              (a["partner_id"],)).fetchone()
            if not pt or pt["status"] != "활성":
                conn.rollback()
                return False, (f"출동 업체가 활성 상태가 아닙니다"
                               f"({pt['status'] if pt else '없는 업체'}). "
                               f"운영팀에 문의해 주세요.")
            _lic_blk = license_block_reason(conn, a["partner_id"])
            if _lic_blk:
                conn.rollback()
                return False, _lic_blk

            # 합의 성사 — 이 업체가 시공한다. 경매를 열지 않는다.
            #  award_route 로 '경매 건'과 구분해 통계가 섞이지 않게 한다.
            #  [E2E 확정결함 수정] 종전에는 est_price 백필 가드(est_price=0일 때만)가
            #  award_route 기록까지 함께 막았다 — 가견적이 이미 있는 사건은 합의해도
            #  경로가 NULL 로 남아 경매/합의 구분 통계가 무효였다. UPDATE 를 둘로 나눈다.
            conn.execute("UPDATE cases SET award_route='1차합의' WHERE id=?", (a["case_id"],))
            conn.execute(
                "UPDATE cases SET est_price=? WHERE id=? AND COALESCE(est_price,0)=0",
                (int(amount or 0), a["case_id"]))
            # ⚠ 여기서 **사건 배정까지 닫는다.** 예전에는 award_route 만 남기고 업체·금액·상태를
            #   기록하지 않아, 승인해도 사건이 '시공중'이 되지 않고 담당 업체도 비어 있었다
            #   (경매 낙찰 라우트는 bid 를 요구하므로 이 경로에는 낙찰 수단이 아예 없었다).
            #  위에서 이미 봤지만, 보고-쓰기 사이를 조건으로 한 번 더 닫는다.
            #  (BEGIN IMMEDIATE 안이라 지금은 안전하지만, 이 UPDATE 자체가 조건을 들고 있어야
            #   앞으로 다른 경로가 생겨도 낙찰이 덮어써지지 않는다)
            #  ⚠⚠ [라운드138] dispatch_status 를 안 지웠었다 — 이 경로는 항상
            #    arrive() 가 남긴 '사진확보' 상태에서 들어오는데(open_agreement
            #    가 dispatches.status='도착' 인 행을 요구), 승인 후에도 그 값이
            #    지워지지 않는다. app.py 138라운드가 open-auction 에서 확인한
            #    것과 같은 계열 — 지금 당장은 '사진확보'만 콕 집어 소비하는
            #    화면이 없어 잠재적이지만, "'접수'를 벗어나면 dispatch_status
            #    를 지운다"는 이미 확립된 관례(발주처 취소·수배로 되돌리기·
            #    미수선되돌리기)를 이 경로만 어기고 있었다.
            cur_c = conn.execute(
                """UPDATE cases
                      SET status='시공중', status_at=datetime('now','+9 hours'),
                          partner_id=?, partner_name=?,
                          award_amount=?, awarded_at=datetime('now','+9 hours'),
                          dispatch_status=NULL
                    WHERE id=? AND status='접수' AND partner_id IS NULL""",
                (a["partner_id"], a["partner_name"] or "", int(amount or 0), a["case_id"]))
            if not cur_c.rowcount:
                conn.rollback()
                return False, ("사건이 방금 다른 경로로 진행됐습니다. "
                               "승인이 반영되지 않았으니 운영팀에 문의해 주세요.")
            DB.log(conn, actor or "시스템", "1차 합의 승인(보험사)",
                   f"{a['case_no']} · {a['partner_name']} · {int(amount or 0):,}원"
                   f" · 승인 {ap.get('name') or '-'}({ap.get('role') or '-'})")
            msg = "보험사 승인이 기록됐습니다. 출동 업체가 그대로 시공합니다."
        else:
            # 결렬 — 2차 경매로 간다. 이때 **출동 업체가 올린 사진이 그대로 근거가 된다.**
            #  ⚠⚠ [라운드117] 승인 가지(위 1046행)는 사건이 아직 '접수'·미배정인지
            #    다시 보는데 부동의 가지는 그 재확인이 없었다 — 보험사가 며칠
            #    묵혀 둔 부동의를 뒤늦게 눌러도, 그 사이 사건이 미수선종결·다른
            #    경로로 이미 끝났으면 award_route 만 '경매'로 조용히 덮어썼다
            #    (실측: 종결 후에도 200 으로 통과해 그 값이 바뀌었다).
            cs2 = conn.execute(
                "SELECT status, partner_id FROM cases WHERE id=?", (a["case_id"],)).fetchone()
            if not cs2 or cs2["status"] != "접수" or cs2["partner_id"] is not None:
                conn.rollback()
                return False, (
                    "이 사건은 이미 다른 방식으로 진행됐습니다"
                    + (f"(현재 상태 '{cs2['status']}')" if cs2 else "")
                    + ". 부동의를 반영할 수 없으니 운영팀에 문의해 주세요.")
            cur_d = conn.execute(
                "UPDATE cases SET award_route='경매' WHERE id=? AND status='접수' AND partner_id IS NULL",
                (a["case_id"],))
            if not cur_d.rowcount:
                conn.rollback()
                return False, "사건이 방금 다른 경로로 진행됐습니다. 부동의가 반영되지 않았으니 운영팀에 문의해 주세요."
            DB.log(conn, actor or "시스템", "1차 합의 부동의(보험사)",
                   f"{a['case_no']} · 2차 경매로 진행"
                   + (f" · {ap.get('name')}({ap.get('role') or '-'})" if ap.get("name") else ""))
            msg = "보험사 부동의가 기록됐습니다. 확보한 현장 사진으로 2차 경매를 열 수 있습니다."
        conn.commit()
        return True, msg
    except Exception:
        conn.rollback()
        raise


def agreement_view(conn, case_id):
    """사건의 1차 합의 상태 — 화면·검증용."""
    a = conn.execute(
        """SELECT * FROM field_agreements WHERE case_id=? ORDER BY id DESC LIMIT 1""",
        (case_id,)).fetchone()
    return dict(a) if a else None


def dispatch_view(conn, dispatch_id):
    """수배 한 건의 현재 모습 — 화면·검증용."""
    d = conn.execute(
        """SELECT d.*, c.case_no, c.category, c.region, c.address, c.est_price
             FROM dispatches d LEFT JOIN cases c ON c.id = d.case_id
            WHERE d.id=?""", (dispatch_id,)).fetchone()
    if not d:
        return None
    calls = conn.execute(
        """SELECT partner_id, partner_name, dist_km, call_order,
                  notified_at, responded_at, response
             FROM dispatch_calls WHERE dispatch_id=?
            ORDER BY CASE WHEN call_order IS NULL THEN 1 ELSE 0 END, call_order, id""",
        (dispatch_id,)).fetchall()
    out = dict(d)
    out["calls"] = [dict(c) for c in calls]
    out["minutes"] = dispatch_minutes(conn)
    return out
