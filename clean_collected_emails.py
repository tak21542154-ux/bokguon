# -*- coding: utf-8 -*-
"""수집한 이메일 중 '업체 주소가 아닌 것'을 걸러 비운다.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

홈페이지 자동 수집은 아무 주소나 집어올 수 있다. 실제로 이런 것들이 섞였다.
  · 홈페이지 칸에 당근마켓 링크가 든 업체 → 당근 광고문의 주소(ad@daangn.com)
  · 홈페이지 제작 도구 기본 템플릿  → info@mysite.com
  · 사이트 오류수집 도구            → …@sentry.wixpress.com
이런 주소로 제안을 보내면 엉뚱한 회사에 가고, 우리 쪽 신용만 깎인다.

수집분(email_source='수집(홈페이지)')만 손댄다. 사람이 직접 넣었거나
입점 신청으로 받은 주소는 건드리지 않는다.

실행:
    python clean_collected_emails.py --dry   지울 대상만 확인
    python clean_collected_emails.py         실제로 비움
"""
import io
import sys
import argparse

import db as DB
from collect_emails import BAD_DOMAIN, BAD_LOCAL, PLATFORM_HOSTS, _bad_local_word_in

#  ⚠ 윈도 기본 콘솔은 cp949 라 '—' 같은 문자를 print 하면 UnicodeEncodeError 로
#    죽는다(아래 main() 의 "수집분 검사 — …건"·"삭제 실패(…) — 건너뜀" 줄).
#    형제 점검 도구(check_tx_paths.py 등)가 이미 쓰는 방어를 그대로
#    옮긴다(round519).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def is_junk(email, website):
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return "형식 오류"
    local, _, dom = e.partition("@")
    if any(dom.endswith(b) or dom == b for b in BAD_DOMAIN):
        return f"플랫폼·템플릿 주소({dom})"
    #  ⚠⚠ [라운드299] collect_emails.py 와 판정기준을 공유한다 — `in` 부분열
    #    검사였을 땐 local part 가 흔한 실제 단어(latest·contest 등)이기만
    #    해도 그 안에 test 가 부분열로 들어 있어 사람이 직접 검증한 정상
    #    주소까지 지웠다(실측: '사람 주소 아님(latest)' 로 실제 삭제됨).
    _bad_word = _bad_local_word_in(local, BAD_LOCAL)
    if _bad_word:
        return f"사람 주소 아님({_bad_word})"
    if any(h in (website or "").lower() for h in PLATFORM_HOSTS):
        return "홈페이지가 업체 사이트가 아님"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="지우지 않고 대상만 출력")
    a = ap.parse_args()

    conn = DB.get_db()
    print(f"  대상 DB: {DB.DB_PATH}")
    rows = conn.execute(
        """SELECT id, name, email, website, contact_note FROM partners
            WHERE email_source='수집(홈페이지)' AND TRIM(COALESCE(email,''))<>''"""
    ).fetchall()

    print("=" * 62)
    print(f"  수집분 검사 — {len(rows)}건")
    print("=" * 62)

    bad = skip_err = 0
    for r in rows:
        why = is_junk(r["email"], r["website"])
        if not why:
            continue
        bad += 1
        old_email = r["email"]
        print(f"  {'삭제' if not a.dry else '대상'} {r['name'][:20]:22s} {old_email[:30]:32s} {why}")
        if not a.dry:
            #  ⚠⚠ [라운드271] UPDATE가 예외처리 밖에 있고 commit은 루프 전체가
            #    끝난 뒤 단 한 번뿐이었다 — 저장 하나가 실패하면(락 경합 등)
            #    이미 화면에 "삭제"로 찍힌 나머지 행까지 전부 저장되지 않았다
            #    (실측: 재조회하면 아무것도 안 지워져 있었다). 형제
            #    (geocode_fill.py·seed_boq_led.py, 라운드265·268)처럼 행마다
            #    즉시 커밋하고 실패한 행만 건너뛴다.
            #  ⚠ 지운 원문(old_email)을 정적 문구 대신 메모에 남긴다 — 예전엔
            #    "[자동수집 부적합 주소 제거]"만 찍혀 오탐이 나도 뭘 지웠는지
            #    DB 백업 없인 알 길이 없었다. 같은 주소가 재수집→재정리를
            #    반복해도 이미 있는 마커는 다시 안 붙인다(무한 중복 방지).
            marker = f"[자동수집 부적합 주소 제거: {old_email}]"
            note = (r["contact_note"] or "").strip()
            if marker not in note:
                note = (note + " " + marker).strip()
            try:
                conn.execute(
                    "UPDATE partners SET email='', email_consent=0, contact_note=? WHERE id=?",
                    (note, r["id"]))
                conn.commit()
            except Exception as ex:
                conn.rollback()
                skip_err += 1
                print(f"  ⚠ {r['name'][:20]:20} 삭제 실패({type(ex).__name__}) — 건너뜀")
                continue
    if not a.dry and bad - skip_err > 0:
        #  ⚠ 형제 배치도구(geocode_fill.py·seed_boq.py·collect_emails.py)는
        #    전부 완료 시 DB.log()로 감사로그를 남기는데 이 파일만 빠져 있었다.
        DB.log(conn, "정비도구", "수집 이메일 정리", f"부적합 {bad - skip_err}건 제거")
        conn.commit()
    left = conn.execute(
        "SELECT COUNT(*) FROM partners WHERE email_source='수집(홈페이지)' "
        "AND TRIM(COALESCE(email,''))<>''").fetchone()[0]
    conn.close()

    print("-" * 62)
    print(f"  부적합 {bad}건 · 남은 수집 주소 {left}건"
          + (f" · 저장 실패 {skip_err}건" if skip_err else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
