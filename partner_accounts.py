# -*- coding: utf-8 -*-
"""협력사 포털 계정 일괄 발급 — 실테스트에 부를 업체들이 실제로 '수락'을 누를 수 있게.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

■ 왜 필요한가
  출동 수배는 인근 업체 20곳에 동시 알림을 보낸다. 그런데 실데이터에서
  **활성 협력사 399곳 중 포털 계정이 있는 곳은 1곳**이었다.
  계정이 없으면 알림함에 쌓여도 눌러 줄 사람이 없다 — 운영자는 20곳이 대기 중이라
  믿고 기다리는데, 현실에서는 아무도 오지 않는다.
  실테스트 전에 **부를 업체들에게 먼저 계정을 만들어 두어야 한다.**

■ 무엇을 하는가
  고른 업체에 로그인 아이디와 임시 비밀번호를 만들고, **전달용 표**를 뽑는다.
  아이디는 사업자번호 뒷자리로 만들어 겹치지 않게 한다.

■ 안전 원칙
  · 이미 계정이 있는 업체는 **건너뛴다**(비밀번호를 갈아엎지 않는다).
  · 활성 업체만. 경고·퇴출 상태에는 만들지 않는다.
  · 임시 비밀번호는 **첫 로그인에 반드시 바꾸게** 한다(must_change_pw=1).
  · 화면에 한 번 찍고 저장하지 않는다 — 파일로 남기려면 `--out` 을 직접 지정한다.

■ 쓰는 법
    python partner_accounts.py --dry --region 서울 --major 가드레일
    python partner_accounts.py --region 서울 --limit 10 --out 계정.csv
    python partner_accounts.py --ids 12,34,56
"""
import os
import re
import sys
import csv
import sqlite3
import secrets
import argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "partner_accounts.log"))
import db as DB

#  혼동하기 쉬운 글자(0/O, 1/l/I)는 뺀다 — 전화로 불러 주는 일이 실제로 생긴다
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
RESERVED = {"partner", "p2", "p3", "admin", "staff"}


def gen_pw(n=12):
    #  ⚠⚠ [라운드418] 형제(app.py:_gen_temp_pw, manage.py:gen_password)는 이미
    #    "대문자·소문자·숫자 각 1개 이상"을 재시도로 보장하는데 여기만 없었다
    #    — 몬테카를로 20만회 실측 약 16% 확률로 숫자가 하나도 없는 순문자
    #    비밀번호가 나와, 이 앱 자신의 password_policy_error() 기준(두 종류
    #    이상 조합) 위반 상태로 발급될 수 있었다. 같은 재시도 패턴을 이식한다.
    while True:
        pw = "".join(secrets.choice(ALPHABET) for _ in range(n))
        if (any(c.isupper() for c in pw) and any(c.islower() for c in pw)
                and any(c.isdigit() for c in pw)):
            return pw


def _csv_safe(v):
    """엑셀 수식 인젝션 방지 — app.py 의 동명 헬퍼(_csv_safe·_xl_safe)와 같은 규칙.

    업체명 등은 업체가 스스로 입력한 자유 텍스트라, `=`로 시작하면
    이 CSV 를 엑셀로 열 때 수식으로 실행된다.

    ⚠⚠ [라운드578] "app.py 의 동명 헬퍼와 같은 규칙"이라는 이 함수 자신의 위 설명과
      달리, 트리거 판정에 탭(\t)이 빠져 있었다 — app.py 의 두 형제(_csv_safe·
      _xl_safe)는 이미 [라운드423]에서 "\t=1+1"처럼 **탭으로 시작하는** 값도
      트리거로 잡게 고쳐졌는데(제어문자 필터가 탭을 보존하면서도 트리거 집합에는
      반영이 안 됐던 결함), 그 수정이 app.py 안의 두 곳에만 적용되고 세 번째
      형제인 이 파일은 빠졌다(실측: 이 저장소 전체에서 v[:1] in ("=","+","-","@"…)
      패턴은 정확히 이 세 곳뿐). 업체명·지역·공종도 app.py 의 note 필드와 똑같이
      "업체가 스스로 입력한 자유 텍스트"이므로 같은 우회가 그대로 열려 있었다.
    """
    v = str(v)
    v = "".join(ch for ch in v if ch == "\t" or ch >= " ")
    return ("'" + v) if v[:1] in ("=", "+", "-", "@", "\t") else v


def _taken_anywhere(conn, cand):
    """이 아이디가 **어느 표에서든** 쓰이고 있는가.

    ⚠ 예전엔 `partners` 한 표만 봤다. 그런데 로그인은 partners → insurers →
      portal_users 순으로 훑기 때문에, 표별 UNIQUE 만으로는 서로 다른 표의
      계정끼리 아이디가 겹칠 수 있다. 어드민 화면 쪽(`issue_partner_login`)은
      네 표를 보는데 여기만 한 표를 봐서 **같은 일을 하는 두 경로의 규칙이
      갈려 있었다.**
    """
    for sql in ("SELECT 1 FROM partners WHERE LOWER(login_id)=LOWER(?)",
                "SELECT 1 FROM insurers WHERE LOWER(login_id)=LOWER(?)",
                "SELECT 1 FROM portal_users WHERE LOWER(login_id)=LOWER(?)",
                "SELECT 1 FROM admins WHERE LOWER(username)=LOWER(?)"):
        try:
            if conn.execute(sql, (cand,)).fetchone():
                return True
        except sqlite3.Error:
            pass          # 표가 없는 구버전 DB — 없는 표에는 충돌도 없다
    return False


def make_login_id(conn, row, taken):
    """업체마다 겹치지 않는 아이디. 사업자번호 뒷자리를 쓰고, 없으면 업체 번호로.

    사람이 불러 주기 쉬워야 하므로 짧고 규칙이 보이게 만든다.

    ⚠⚠ [라운드618] 형제(app.py:_auto_login_id, 8352행)는 이미 [^0-9]로 숫자만
      뽑는데 이 파일만 \\D(=\\d의 여집합)를 썼다 — round497이 밝힌 것과 같은
      결함: 파이썬의 \\d는 유니코드 전각숫자(１２３ 등, U+FF10~19)도 "숫자"로
      쳐서 \\D가 지우지 않는다. biz_no에 전각숫자가 섞여 있으면(round497 수정
      이전에 등록됐거나, valid_biz_no()를 안 거치는 경로로 들어온 값) 그대로
      살아남아 login_id 끝자리에 전각 문자가 박힌다 — 이 함수 자신이 위에서
      "사람이 불러 주기 쉬워야 한다"고 명시한 목적(혼동하기 쉬운 0/O·1/l/I를
      알파벳에서 이미 뺀 것과 같은 이유)에 정면으로 어긋나고, issue_partner_login
      의 수동경로가 요구하는 [a-z0-9_-] 형식과도 어긋나 업체가 발급받은 아이디를
      타이핑도 못 하는 상황이 생길 수 있다.
    """
    biz = re.sub(r"[^0-9]", "", row["biz_no"] or "")
    base = f"p{biz[-6:]}" if len(biz) >= 6 else f"p{row['id']:05d}"
    cand, n = base, 1
    while cand in taken or cand in RESERVED or _taken_anywhere(conn, cand):
        n += 1
        cand = f"{base}{n}"
        if n > 200:
            raise RuntimeError(f"아이디 후보를 찾지 못했습니다: {base}")
    taken.add(cand)
    return cand


def pick(conn, region, major, ids, limit, need_phone, ptype=""):
    """계정을 줄 협력사를 고른다.

    ⚠ **시행사/시공사를 가려야 한다.** 통값 입찰은 시행사만 할 수 있는데
      (app.py: "통값 입찰은 시행사만 참여할 수 있습니다"), 이 도구는 구분 없이
      rating 순으로 집었다. 시공사만 뽑히면 경매를 열어도 **투찰 자격자가 0곳**이라
      공고가 그대로 유찰된다 — 첫 주에 아무도 원인을 모른 채 멈춘다.
      기본값은 시행사다. 시공사 계정이 필요하면 --type 시공사 로 명시한다.
    """
    _cols = "id,name,biz_no,phone,region,major,login_id,partner_type"
    if ids:
        #  ⚠ 아래 조건 분기(--region·--major)에는 status='활성' 이 있는데 여기만
        #    없었다 — 위 "안전 원칙"이 약속한 "활성 업체만"을 --ids 로 부르면
        #    건너뛴다. 퇴출·경고 업체에도 그대로 포털 계정이 발급됐다.
        q = (f"SELECT {_cols} FROM partners "
             f" WHERE id IN ({','.join('?' * len(ids))}) AND status='활성'")
        return conn.execute(q, ids).fetchall()
    where = ["status='활성'", "COALESCE(login_id,'')=''"]
    p = []
    if ptype:
        where.append("COALESCE(partner_type,'') = ?")
        p.append(ptype)
    if region:
        where.append("(COALESCE(region,'') LIKE ? OR COALESCE(address,'') LIKE ?)")
        p += [f"%{region}%", f"%{region}%"]
    if major:
        where.append("(COALESCE(major,'') LIKE ? OR COALESCE(category,'') LIKE ?)")
        p += [f"%{major}%", f"%{major}%"]
    if need_phone:
        #  임시 비밀번호를 문자로 보내려면 휴대전화가 있어야 한다
        where.append("COALESCE(phone,'') LIKE '01%'")
    p.append(limit)
    return conn.execute(
        f"""SELECT {_cols} FROM partners
             WHERE {' AND '.join(where)}
             ORDER BY rating DESC, jobs_done DESC, id LIMIT ?""", p).fetchall()


def main():
    ap = argparse.ArgumentParser(description="협력사 포털 계정 일괄 발급")
    ap.add_argument("--region", default="", help="지역으로 좁히기 (예: 서울)")
    ap.add_argument("--major", default="", help="공종으로 좁히기 (예: 가드레일)")
    ap.add_argument("--type", dest="ptype", default="시행사",
                    choices=["시행사", "시공사", "전체"],
                    help="시행사(기본)/시공사/전체 — **통값 입찰은 시행사만 가능하다**")
    ap.add_argument("--ids", default="", help="업체 번호 직접 지정 (쉼표)")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--need-phone", action="store_true",
                    help="휴대전화가 있는 곳만 (임시 비밀번호를 문자로 보낼 수 있게)")
    ap.add_argument("--out", default="", help="전달용 CSV 경로 (지정할 때만 저장)")
    ap.add_argument("--dry", action="store_true", help="누가 대상인지만 보고 만들지 않음")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()

    if a.self_check:
        return demo()

    ids = [int(x) for x in re.findall(r"\d+", a.ids)]
    conn = DB.get_db()
    rows = pick(conn, a.region, a.major, ids, a.limit, a.need_phone,
                "" if a.ptype == "전체" else a.ptype)
    print("=" * 72)
    print("  협력사 포털 계정 발급" + ("  (미리보기 — 만들지 않음)" if a.dry else ""))
    print("=" * 72)
    if not rows:
        print("  대상이 없습니다. 조건을 넓혀 보세요.")
        conn.close(); return 0

    #  ⚠⚠ [라운드300] CSV 저장과 감사로그(DB.log)가 전부 **루프가 끝까지 다
    #    돈 뒤** 한 번만 실행됐다 — 그런데 각 업체의 UPDATE 는 SAVEPOINT 를
    #    감싸는 바깥 BEGIN 이 없어(SQLite 특성상) RELEASE 순간 이미 개별
    #    커밋된다. 그 사이에 이 루프가 죽으면(운영자가 급해서 Ctrl+C — 이
    #    파일 위 "안전 원칙"이 이미 실제로 일어나는 일로 인정하는 행동, 또는
    #    200번 충돌로 인한 RuntimeError, 라운드270 주석) 이미 발급된 앞쪽
    #    업체들은 DB 엔 login_id·password_hash 가 실제로 박혀 있는데 그
    #    비밀번호가 찍힌 화면·CSV·감사로그 어디에도 안 남는다 — password_hash
    #    는 단방향이라 나중에 조회해도 복구가 안 되고, 그 업체는 로그인
    #    자체가 불가능한 죽은 계정이 된다(실측: 3번째에서 강제로 죽이면
    #    앞의 2곳이 정확히 이 상태로 남는 것을 격리 DB로 확인). 화면 출력
    #    (print)은 이미 매 업체마다 즉시 나가고 있으니, CSV·감사로그도
    #    같은 자리(업체 하나 처리 직후)로 옮겨 셋의 시점을 맞춘다.
    csv_writer, csv_fh = None, None
    if a.out and not a.dry:
        csv_fh = open(a.out, "w", encoding="utf-8-sig", newline="")
        csv_writer = csv.DictWriter(csv_fh, fieldnames=[
            "업체번호", "업체명", "구분", "지역", "공종", "연락처", "아이디", "임시비밀번호"])
        csv_writer.writeheader()
        csv_fh.flush()

    taken, made, failed = set(), [], 0
    for r in rows:
        if (r["login_id"] or "").strip():
            print(f"  · {r['name'][:20]:20} 이미 계정 있음({r['login_id']}) — 건너뜀")
            continue
        lid = make_login_id(conn, r, taken)
        pw = gen_pw()
        if not a.dry:
            #  ⚠⚠ [라운드270] 예전엔 WHERE id=? 뿐이라, 이 스크립트를 두 번
            #    동시에 돌리면(응답 지연을 오인해 재실행 등) 나중에 커밋한 쪽이
            #    먼저 커밋한 쪽 비밀번호를 에러 없이 조용히 덮어썼다(실측:
            #    화면에 이미 찍어 전화로 불러줬을 비밀번호가 그 순간 무효가 됨).
            #    형제(app.py api_partner_bulk_credentials, 라운드199)처럼 이미
            #    값이 있으면 재확인하고, SAVEPOINT 로 이 업체 몫만 격리한다 —
            #    한 업체의 UNIQUE 충돌 등이 이미 화면에 찍은 나머지 업체까지
            #    되돌리면 안 된다(형제도 이 이유로 SAVEPOINT 를 쓴다).
            conn.execute("SAVEPOINT partner_acct")
            try:
                cur = conn.execute(
                    "UPDATE partners SET login_id=?, password_hash=?, must_change_pw=1 "
                    " WHERE id=? AND COALESCE(login_id,'')=''",
                    (lid, DB.hash_pw(pw), r["id"]))
                if not cur.rowcount:
                    conn.execute("ROLLBACK TO SAVEPOINT partner_acct")
                    print(f"  ⚠ {r['name'][:20]:20} 방금 다른 실행이 먼저 발급함 — 건너뜀")
                    continue
            except Exception as ex:
                conn.execute("ROLLBACK TO SAVEPOINT partner_acct")
                failed += 1
                print(f"  ⚠ {r['name'][:20]:20} 발급 실패({type(ex).__name__}) — 건너뜀")
                continue
            conn.execute("RELEASE SAVEPOINT partner_acct")
            #  ⚠⚠ [라운드300] UPDATE 와 같은 자리에서 즉시 남기고 즉시 커밋한다
            #    (위 300라운드 주석 참조) — 이 업체 몫까지만 확실히 남겨야
            #    루프가 다음 업체에서 죽어도 지금까지 발급분은 추적 가능하다.
            DB.log(conn, "정비도구", "협력사 계정 발급", f"{r['name']} ({lid})")
            conn.commit()
        _pt = (r["partner_type"] if "partner_type" in r.keys() else "") or "미분류"
        row_out = {"업체번호": r["id"], "업체명": _csv_safe(r["name"]), "구분": _csv_safe(_pt),
                   "지역": _csv_safe(r["region"] or ""),
                   "공종": _csv_safe(r["major"] or ""), "연락처": _csv_safe(r["phone"] or ""),
                   "아이디": lid, "임시비밀번호": pw}
        made.append(row_out)
        if csv_writer:
            csv_writer.writerow(row_out)
            csv_fh.flush()
        #  ★ 구분을 함께 찍는다. 안 찍으면 시공사만 발급된 것을 아무도 눈치채지 못한다.
        print(f"  ✔ {r['name'][:20]:20} [{_pt:<4}] {lid:12} {pw}   {(r['phone'] or '')[:14]}")

    if csv_fh:
        csv_fh.close()
    conn.close()

    print(f"\n  → {'만들 예정' if a.dry else '발급'} {len(made)}곳"
          + (f" · 실패 {failed}곳(로그 확인 후 재실행하면 다시 대상이 됩니다)" if failed else ""))
    print("  ※ 임시 비밀번호는 **첫 로그인 때 반드시 변경**하게 되어 있습니다.")
    print("  ※ 이 화면은 다시 볼 수 없습니다 — 필요하면 --out 으로 저장하세요"
          " (전달 후 파일은 지우십시오).")
    if a.out and not a.dry:
        print(f"  저장: {a.out} ({len(made)}행 — 업체마다 처리 즉시 기록됨)")
    return 0


def demo():
    """python partner_accounts.py --self-check"""
    class FakeConn:
        def execute(self, *a):
            class R:
                def fetchone(self_inner): return None
            return R()
    c = FakeConn()
    taken = set()
    r1 = {"id": 7, "biz_no": "123-45-67890"}
    r2 = {"id": 8, "biz_no": "999-99-67890"}      # 뒷자리가 같다
    a1 = make_login_id(c, r1, taken)
    a2 = make_login_id(c, r2, taken)
    assert a1 == "p567890", a1
    assert a2 != a1, "뒷자리가 같아도 아이디가 겹치면 안 된다"
    r3 = {"id": 12, "biz_no": ""}
    assert make_login_id(c, r3, taken) == "p00012"
    pw = gen_pw()
    assert len(pw) == 12
    assert not set(pw) & set("0O1lI"), "헷갈리는 글자는 빼야 한다(전화로 불러 준다)"
    #  ⚠⚠ [라운드418] 이 점검이 길이·혼동글자만 보고 문자종 구성은 안 봐서,
    #    숫자 없는 비밀번호가 나와도 "정상"이라고 오판했다 — 형제 점검(app.py
    #    _gen_temp_pw 는 함수 자체가 재시도로 보장)과 같은 기준을 명시적으로 본다.
    assert (any(c.isupper() for c in pw) and any(c.islower() for c in pw)
            and any(c.isdigit() for c in pw)), \
        "대문자·소문자·숫자를 각 1개 이상 포함해야 한다(password_policy_error 기준)"
    #  ⚠⚠ [라운드578] 이 점검이 여태 _csv_safe() 를 아예 안 보고 있었다 — app.py
    #    형제(round423)가 이미 잡은 "탭으로 시작하는 값" 우회를 이 함수가 다시
    #    막게 됐는지 여기서 직접 확인한다.
    assert _csv_safe("\t=1+1")[:1] == "'", \
        "탭으로 시작하는 수식주입 값도 막아야 한다(app.py _csv_safe·_xl_safe 와 같은 규칙)"
    assert _csv_safe("=1+1") == "'=1+1", "대조군 — 기존 방어(=로 시작)는 그대로"
    assert _csv_safe("정상업체명") == "정상업체명", "대조군 — 평범한 값은 안 바뀐다"
    print("자체 점검 통과 — 아이디 중복 회피 · 비밀번호 규칙 · CSV 수식주입 방어 정상")
    return 0


if __name__ == "__main__":
    sys.exit(main())
