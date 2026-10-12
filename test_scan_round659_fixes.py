# -*- coding: utf-8 -*-
"""스캔 659라운드 회귀 — 보험사 사건 등록 공용 헬퍼 _create_case() 의 "정상 접수"
   경로(사진있음)가 협력사·보험사 본인에게는 실시간 알림을 보내면서 **운영팀에게는
   알림을 전혀 안 보내던** 결함.

   조사 배경 — 실사용자 보고(관리자 콘솔·보험사 어드민·시공사 어드민 사이 "동기화가
   안 된다") 를 직접 조사(하위위임 없음) — _create_case() 를 전체 Read 로 대조한
   결과, 사진없는 접수(no_photo) 경로엔 "수배필요"→admin 알림이, 매칭 시행사 0곳
   예외 경로엔 "참여업체없음"→admin 알림이 이미 있었지만, 가장 흔한 정상 경로
   (사진있음·공고 오픈)엔 협력사 전체(공고오픈)·보험사 본인(사건접수) 두 알림만
   있고 **운영팀 알림 자체가 없었다.** api_cases() 목록 자체는 필터 없이 항상
   보이므로 "사건이 안 보인다"는 아니지만, 운영팀이 매번 목록을 직접 열어보지
   않는 한 새 접수가 있었다는 사실을 알 방법이 없었다.

   (같은 조사에서 함께 확인한 별개 사실 — 운영 DB 실측: 활성 시행사 90곳 중
   로그인 계정이 있는 곳은 2곳뿐이고, 문자·알림톡 실발송 스위치(BOKGUON_
   NOTIFY_ENABLED)가 .env 에서 꺼져 있다. 둘 다 코드 결함이 아니라 운영/계정
   설정 문제라 이번 라운드에서 손대지 않았다 — 사용자 확인 후 범위에서 제외.)

   고침 — 형제 두 알림(수배필요·참여업체없음)과 같은 자리·같은 패턴으로,
   정상 접수 경로에도 "사건접수"→admin 알림을 추가(app.py, _create_case() 안
   한 곳). 대상 협력사 전체·보험사 본인 알림 로직은 전혀 안 건드림(무변경).

   [1] 소스 확인 — 새 notify() 호출이 _create_case() 안에, no_photo 이른-반환
       **뒤**(정상 경로)에 있고, audience_type="admin" 인지 확인.
   [2] 실행 — 실제 Flask+DB. POST /api/v1/cases 로 정상 접수(사진있음) 2건
       (매칭 0곳 1건 + 매칭 1곳 1건)을 만들어 운영팀 알림이 정확히 뜨는지,
       매칭수 문구가 맞는지, 기존 두 알림(공고오픈·사건접수→보험사)·형제
       예외경로(수배필요)는 전혀 회귀 없이 그대로인지 확인.
   [3] 되돌리기 — 새 알림 블록만 인메모리로 제거한 사본(dict(vars(A)) 네임스페이스,
       실제 파일은 안 건드림)으로 같은 시나리오를 돌리면 운영팀 알림이 실제로
       빠지는지 확인 — 이 테스트가 실제로 회귀를 잡아낼 능력이 있음을 증명.

       python test_scan_round659_fixes.py
"""
import io
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 659라운드 회귀 — _create_case() 정상접수 경로에 운영팀 알림 누락 결함")
print("=" * 72)

print("\n[1] 소스 확인")
cc_body_raw = _py_fn_body(APP_SRC, "_create_case")
#  ⚠ _py_fn_body() 는 다음 "\ndef " 만 경계로 보므로, 그 사이에 낀 다음 함수의
#    데코레이터(@app.post(...)·@require_insurer)까지 그대로 딸려 들어온다 —
#    단순 "in" 문자열검사([1]절)엔 무해하지만 [3]절처럼 이 몸통을 그대로
#    exec() 하려면 데코레이터가 def 없이 홀로 남아 SyntaxError 가 난다.
#    이 함수의 실제 마지막 문장(정상경로 return)까지만 정확히 자른다.
_END_MARK = '"categories": cats, "category": category}'
cc_body = cc_body_raw[:cc_body_raw.rindex(_END_MARK) + len(_END_MARK)] + "\n"
_no_photo_end = cc_body.index('"categories": cats, "category": category}')
_normal_part = cc_body[_no_photo_end:]
NEW_CALL = 'notify(conn, "사건접수", "웹", "운영팀",'
chk(NEW_CALL in _normal_part,
    "★★★★★ 새 admin 알림 notify() 호출이 정상경로(no_photo 이른-반환 뒤)에 있다")
chk('audience_type="admin", case_id=cid)' in _normal_part,
    "★★★★★ 새 호출의 audience_type 이 admin 이고 case_id 를 담아 상세로 딥링크된다")
chk(NEW_CALL not in cc_body[:_no_photo_end],
    "STEP 새 호출이 no_photo(사진없음) 이른-반환 앞쪽엔 없다(그 경로는 형제 "
    "'수배필요' 알림을 그대로 쓴다 — 중복 아님)")
chk('notify(conn, "참여업체없음"' in _normal_part,
    "STEP 형제(매칭 0곳) 알림 로직은 그대로 남아 있다(무변경)")

print("\n[2] 실행 — 실서버 경로(Flask test_client + 임시 DB)로 실제 재현")
_tmpdir = tempfile.mkdtemp(prefix="round659_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ["BOKGUON_OTP_POLICY"] = "off"
sys.path.insert(0, HERE)

RAW_KEY = "bok_live_r659testkey"
client = None
A = None
DBm = None

try:
    import db as DBm
    DBm.init_db()
    import app as A

    conn = DBm.get_db()
    conn.execute(
        "INSERT INTO insurers(id,name,status,api_key_hash,api_key_prefix,api_enabled) "
        "VALUES(1,'R659보험',?,?,?,1)",
        ("활성", A._hash_api_key(RAW_KEY), RAW_KEY[:16]))
    conn.commit()
    conn.close()

    client = A.app.test_client()
    HDR = {"X-API-Key": RAW_KEY}

    chk(True, "STEP 스크래치 DB·app 모듈 로드 성공 — API 연동 보험사 1건 준비",
        os.environ["BOKGUON_DB_PATH"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 실행 준비(DB.init_db·app import)", f"{type(e).__name__} {e}")


def admin_notifs(case_id):
    c = DBm.get_db()
    out = [dict(r) for r in c.execute(
        "SELECT ntype, message FROM notifications WHERE audience_type='admin' AND case_id=?",
        (case_id,))]
    c.close()
    return out


if client is not None:
    # [2-a] 매칭 시행사 0곳(스크래치 DB엔 partners 가 아직 없다) — 정상 접수(사진있음).
    try:
        r = client.post("/api/v1/cases", headers=HDR, json={
            "category": "누수·배관·설비", "region": "서울", "est_price": 500000,
        })
        chk(r.status_code == 201, "STEP 정상 접수(매칭 0곳) 201", r.status_code)
        cid1 = (r.get_json() or {}).get("id")
        ns1 = admin_notifs(cid1)
        found1 = [n for n in ns1 if n["ntype"] == "사건접수"]
        chk(len(found1) == 1,
            "★★★★★ 운영팀 앞 '사건접수' 알림이 정확히 1건 생성된다(고치기 전엔 0건)",
            ns1)
        chk(bool(found1) and "매칭 시행사 0곳" in found1[0]["message"],
            "★★★ 알림 문구에 매칭 시행사 수(0곳)가 정확히 들어간다",
            found1[0]["message"] if found1 else None)
        found_zero = [n for n in ns1 if n["ntype"] == "참여업체없음"]
        chk(len(found_zero) == 1,
            "STEP 형제 알림(참여업체없음)도 무회귀로 그대로 함께 뜬다(매칭 0곳이므로)",
            ns1)
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★★★ [2-a] 매칭 0곳 정상접수 실행", f"{type(e).__name__} {e}")

    # [2-b] 매칭 시행사 1곳 — 활성·로그인계정 보유 협력사를 하나 심고 재확인.
    try:
        c2 = DBm.get_db()
        c2.execute(
            "INSERT INTO partners(id,name,partner_type,status,login_id,password_hash) "
            "VALUES(1,'R659협력사','시행사','활성','r659_partner','x')")
        c2.commit(); c2.close()

        r2 = client.post("/api/v1/cases", headers=HDR, json={
            "category": "누수·배관·설비", "region": "서울", "est_price": 500000,
        })
        chk(r2.status_code == 201, "STEP 정상 접수(매칭 1곳) 201", r2.status_code)
        cid2 = (r2.get_json() or {}).get("id")
        ns2 = admin_notifs(cid2)
        found2 = [n for n in ns2 if n["ntype"] == "사건접수"]
        chk(bool(found2) and "매칭 시행사 1곳" in found2[0]["message"],
            "★★★★★ 매칭 협력사가 1곳이면 알림 문구도 '매칭 시행사 1곳'으로 정확히 반영된다",
            found2[0]["message"] if found2 else None)
        chk(not any(n["ntype"] == "참여업체없음" for n in ns2),
            "STEP 매칭 1곳이면 '참여업체없음' 경고는 안 뜬다(과잉 알림 아님)", ns2)
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★★ [2-b] 매칭 1곳 정상접수 실행", f"{type(e).__name__} {e}")

    # [2-c] 무회귀 — 사진없는 접수(no_photo)는 형제 '수배필요' 알림이 여전히 그대로.
    try:
        r3 = client.post("/api/v1/cases", headers=HDR, json={
            "category": "누수·배관·설비", "region": "서울", "no_photo": True,
        })
        chk(r3.status_code == 201, "STEP 사진없는 접수 201", r3.status_code)
        cid3 = (r3.get_json() or {}).get("id")
        ns3 = admin_notifs(cid3)
        chk(any(n["ntype"] == "수배필요" for n in ns3),
            "★★★ 사진없는 접수는 형제 '수배필요' 알림이 무회귀로 여전히 뜬다", ns3)
        chk(not any(n["ntype"] == "사건접수" for n in ns3),
            "STEP 사진없는 접수엔 새 '사건접수'(정상경로 전용) 알림이 안 겹쳐 뜬다"
            "(두 경로가 서로 배타적으로 남는다)", ns3)
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★ [2-c] 사진없는 접수 무회귀 실행", f"{type(e).__name__} {e}")

print("\n[3] 되돌리기 — 새 알림 블록만 인메모리로 뺀 사본으로 같은 시나리오를 돌리면"
      " 실제로 빠지는가")
if A is not None:
    try:
        _pre_src = cc_body.replace(
            '    #  ⚠⚠ [라운드659] 이 정상접수 경로(사진있음·매칭업체 1곳 이상)는 협력사·보험사\n'
            '    #    본인에게는 알림이 갔지만 **운영팀에게는 알림이 전혀 없었다** — 아래 사진없는\n'
            '    #    접수(수배필요)·매칭 0곳(참여업체없음) 두 예외 경로에만 운영팀 알림이 있고,\n'
            '    #    가장 흔한 정상 경로만 빠져 있었다. 콘솔 목록(api_cases)은 필터 없이 항상\n'
            '    #    보이므로 "사건이 아예 안 보인다"는 아니었지만, 운영팀이 매번 목록을 직접\n'
            '    #    열어 확인하지 않는 한 새 접수를 알 방법이 없었다 — 실사용자 보고로 발견.\n'
            '    notify(conn, "사건접수", "웹", "운영팀",\n'
            '           f"[{case_no}] {(d.get(\'region\') or \'\')} {category} 사건이 접수되어'
            ' 공고가 열렸습니다. "\n'
            '           f"(매칭 시행사 {n_match}곳)",\n'
            '           audience_type="admin", case_id=cid)\n',
            "")
        chk(_pre_src != cc_body,
            "STEP 되돌린 사본이 실제로 지금 소스와 다르다(치환이 실제로 일어났다)")
        chk(NEW_CALL not in _pre_src,
            "STEP 되돌린 사본엔 새 admin notify() 호출 자체가 없다")

        ns_reverted = dict(vars(A))
        exec(compile(_pre_src, "<round659_pre__create_case>", "exec"), ns_reverted)  # noqa: S102

        conn_r = DBm.get_db()
        conn_r.execute("BEGIN IMMEDIATE")
        res_r = ns_reverted["_create_case"](
            conn_r, 1, "R659보험",
            {"category": "누수·배관·설비", "region": "서울", "est_price": 500000},
            "포털")
        conn_r.commit()
        cid_r = res_r["id"]
        ns_r = admin_notifs(cid_r)
        chk(not any(n["ntype"] == "사건접수" and "공고가 열렸습니다" in n["message"]
                    for n in ns_r),
            "★★★★★★ 되돌린(고치기 전) 버전은 정상접수인데도 운영팀 '사건접수' 알림이 "
            "실제로 안 생긴다 — 이 테스트가 실제로 회귀를 잡아낸다는 증거", ns_r)
        conn_r.close()

        # 지금(수정 후) 실제 A._create_case 는 같은 입력에서 여전히 정상 생성한다.
        conn_c = DBm.get_db()
        conn_c.execute("BEGIN IMMEDIATE")
        res_c = A._create_case(
            conn_c, 1, "R659보험",
            {"category": "누수·배관·설비", "region": "서울", "est_price": 500000},
            "포털")
        conn_c.commit()
        ns_c = admin_notifs(res_c["id"])
        chk(any(n["ntype"] == "사건접수" for n in ns_c),
            "★★★★★ 지금(수정 후) 실제 A._create_case 는 같은 입력에서 여전히 "
            "운영팀 알림을 만든다(인과관계 직접증명)", ns_c)
        conn_c.close()
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★★★ [3] 되돌림-증명 실행", f"{type(e).__name__} {e}")
else:
    chk(False, "★★★★★ [3] 되돌림-증명 — app 모듈 로드 실패로 건너뜀")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
