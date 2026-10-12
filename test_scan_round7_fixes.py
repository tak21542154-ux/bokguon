# -*- coding: utf-8 -*-
"""7라운드 스캔 수정의 회귀 검사 — 부분실패 · 3자동시 · 신뢰경계 · 복구 · 오프라인.

  ⚠ 이 라운드에서 가장 뼈아팠던 것은 **6라운드 수정이 만든 결함**이다.
     웹훅 재전송을 데몬 스레드로 띄웠는데, `manage.py sweep` 은 크론에서 돌고
     곧바로 끝난다 — 인터프리터가 그 스레드를 사살하므로 결과 UPDATE 가 실행되지
     않고, attempts 가 영원히 그대로라 **5분마다 무한 재발사**된다. 게다가
     '재전송 N건'이라고 성공한 것처럼 보고까지 했다.
     교훈: **짧게 살다 죽는 프로세스에서는 데몬 스레드에 뒷정리를 맡기지 않는다.**

  서버가 필요 없다(로그인을 안 하므로 레이트리밋과 무관).
"""
import ast
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OK = FAIL = 0


def chk(cond, name, got=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}   {got}")


def src(*parts):
    return io.open(os.path.join(HERE, *parts), encoding="utf-8").read()


def fn_source(tree, text, name):
    """함수 하나의 소스만 떼어 온다(파일 전체 grep 이 옆 함수를 잡는 것을 막는다)."""
    lines = text.splitlines(True)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    return ""


def main():
    app_s = src("app.py")
    dsp_s = src("dispatch.py")
    mng_s = src("manage.py")
    ptl_s = src("templates", "partner_portal.html")
    app_t = ast.parse(app_s)
    mng_t = ast.parse(mng_s)

    print("[1] 부분 실패 — 짧게 죽는 프로세스에서 뒷정리를 잃지 않는가")
    retry = fn_source(app_t, app_s, "sweep_webhook_retries")
    chk(retry and "threading.Thread" not in retry,
        "★ 웹훅 재전송이 데몬 스레드가 아니다(CLI 종료 시 사살돼 결과가 안 남았다)")
    #  ⚠ [라운드84] 이 UPDATE 가 CAS(경합 방지)로 바뀌면서 attempts 증가식이
    #    인라인 SQL(COALESCE(attempts,0)+1)에서 파이썬 파라미터(tries+1 바인딩)로
    #    옮겨갔다 — "쏘기 전에 먼저 커밋한다"는 이 검사의 실제 불변식은 그대로
    #    지켜지므로, 정확한 옛 SQL 문자열이 아니라 그 불변식(증가 흔적 + 커밋)을 본다.
    chk(("attempts=COALESCE(attempts,0)+1" in retry
         or ("attempts=?" in retry and "tries" in retry))
        and "conn.commit()" in retry,
        "★ **쏘기 전에** 시도 횟수를 먼저 기록한다(중간에 죽어도 무한 재발사가 안 된다)")
    chk("count_attempt=False" in retry and "def _webhook_send(" in app_s
        and "count_attempt=True" in app_s,
        "재전송 경로에서는 시도 횟수를 두 번 세지 않는다(상한이 절반으로 닳지 않게)")
    sweep_cmd = fn_source(mng_t, mng_s, "cmd_sweep")
    chk("whr = 0" in sweep_cmd or "whr" in sweep_cmd.split("try:")[0],
        "★ --dry-run 이 UnboundLocalError 로 죽지 않는다(누산기 선초기화)")

    print("\n[2] 부분 실패 — 실패를 성공이라고 말하지 않는가")
    defect_up = fn_source(app_t, app_s, "api_defect_photos_upload")
    chk("except sqlite3.IntegrityError" in defect_up and "dup.append" in defect_up,
        "★ 하자 사진 중복이 '조용한 성공'이 아니라 중복으로 보고된다")
    chk('"ok": bool(saved)' in defect_up,
        "★ 한 장도 못 올렸으면 ok:true 라고 하지 않는다(화면은 '첨부 완료'인데 0장이었다)")
    chk("errors.append(f\"'{info['orig_name']}' 저장에 실패했습니다.\")" in defect_up,
        "저장 실패가 errors 로 사용자에게 전달된다")

    print("\n[3] 되돌린 뒤·동시 조작 — 낙찰 후보에 엉뚱한 입찰이 섞이지 않는가")
    chk(app_s.count("change_order_id IS NULL)\n             AND b.voided_at IS NULL") >= 1
        or app_s.count("WHERE case_id=? AND change_order_id IS NULL)") >= 2,
        "★ 낙찰 후보 조회가 원경매로 좁혀진다(추가분 80만이 500만 공사 낙찰가가 됐다)")
    chk(app_s.count("AND a.change_order_id IS NULL") >= 2,
        "★ 낙찰 검증(보험사·어드민 양쪽)도 원경매만 인정한다",
        app_s.count("AND a.change_order_id IS NULL"))
    chk("AND auction_id IN (SELECT id FROM auctions WHERE case_id=?)" in app_s,
        "★ 낙찰 취소가 변경견적 경매 입찰까지 무효화한다")
    chk("UPDATE change_orders SET status='철회'" in app_s,
        "★ 낙찰 취소가 진행 중이던 변경견적을 닫는다(상태값은 활성판정에서 빠지는 '철회')")
    full_re = fn_source(app_t, app_s, "api_co_full_reauction")
    chk('"CASE_MOVED"' in full_re,
        "★ 전체재경매가 '그 사이 다른 업체가 낙찰받았는지'를 본다")

    print("\n[4] 3자 동시 — 직접 배정에도 같은 가드가 있는가")
    assign = ""
    dtree = ast.parse(dsp_s)
    assign = fn_source(dtree, dsp_s, "assign_dispatch")
    chk('cs[0] != "접수" or cs[1] is not None' in assign,
        "★ 직접 배정이 사건 상태를 본다(시공 중인 사건에 제3업체가 붙어 영수증을 열람했다)")
    chk('== "무등록"' in assign,
        "★ 직접 배정도 무등록 업체를 거른다(자동 수배에만 있던 규칙)")

    print("\n[5] 신뢰 경계 — 외부 값이 그대로 쓰이지 않는가")
    chk("def _truthy(" in app_s and app_s.count("_truthy(d.get") >= 4,
        '★ 불리언을 bool() 로 강제하지 않는다 (bool("false") 는 참이다)',
        app_s.count("_truthy(d.get"))
    chk("def _s(" in app_s and app_s.count("_s(d.get(") >= 6,
        "★ 본문 값을 문자열로 강제해 .strip() 에서 500 이 나지 않는다",
        app_s.count("_s(d.get("))
    err500 = fn_source(app_t, app_s, "err_500")
    chk("_cleanup_conns(rollback=True)" in err500,
        "★ 뷰가 죽으면 쓰기 잠금을 **즉시** 놓는다(접속기록이 8초 대기 끝에 유실됐다)")
    chk("한 번도 실행된 적이 없는 죽은 안전망" in app_s,
        "죽은 안전망이었다는 사실이 코드에 남아 있다(다시 그 신호에 기대지 않게)")

    print("\n[6] 성능 — 조회 화면이 쓰기를 부르지 않는가")
    inline = fn_source(app_t, app_s, "_sweep_if_due")
    chk("INLINE_SWEEP_GAP_SEC" in app_s and "_LAST_INLINE_SWEEP" in inline,
        "★ '_if_due' 에 실제 due 판정이 있다(이름과 달리 매번 무조건 돌았다)")

    print("\n[7] 복구·재실행 — go-live 가 지울 것만 지우는가")
    golive = fn_source(mng_t, mng_s, "cmd_go_live")
    chk("DELETE FROM notifications WHERE created_at <= ?" not in golive,
        "★ 데모가 0건이어도 알림을 전량 삭제하지 않는다(실측 1,553행이 날아갔다)")
    chk("COALESCE(is_demo,0)=1" in golive and "notifications WHERE case_id IN" in golive,
        "★ 데모 사건에 딸린 알림·데모 표식 알림만 지운다")
    chk("dispatches" in golive and "field_agreements" in golive,
        "★ 사건에 딸린 출동수배·현장합의도 함께 지운다(고아 행이 남았다)")
    check_cmd = fn_source(mng_t, mng_s, "cmd_check")
    chk("고아 행" in check_cmd,
        "★ 배포 점검이 '없어진 사건을 가리키는 고아 행'을 경고한다")
    chk('"dispatches", "field_agreements"' in check_cmd,
        "데모 집계가 DEMO_TABLES 밖의 표까지 센다(거짓 초록 방지)")
    ca = fn_source(mng_t, mng_s, "cmd_create_admin")
    chk('"중간관리자"' in ca and "최고관리자" in ca and "하위관리자" in ca,
        "★ 계정 발급 기본 등급이 실제 등급표 안의 값이다"
        " (종전 '운영관리자'는 ROLE_RANK 에 없어 권한 0 이었다)")

    print("\n[8] 오프라인 — 다시 못 찍는 사진을 잃지 않는가")
    chk('"idx": info.get("idx")' in app_s and '"duplicate_idx": dup_idx' in app_s,
        "★ 서버가 '몇 번째 파일'인지 알려 준다(이름은 카메라 캡처에서 전부 같다)")
    chk("savedIdx" in ptl_s and "duplicate_idx" in ptl_s,
        "★ 화면이 이름이 아니라 색인으로 성공을 판정한다"
        " (동명 5장 중 1장만 성공해도 4장을 큐에서 지웠다)")
    chk("FIX_RETRY" in ptl_s and "uploadFixPhotoFile" in ptl_s,
        "★ 하자 보수 사진이 실패해도 파일을 놓지 않고 '다시 올리기'가 뜬다")
    chk("clearAppCaches" in ptl_s and "clearAppCaches" in src("templates", "insurer_portal.html"),
        "★ 로그아웃이 서비스워커 사본까지 지운다(이전 업체 상세주소·계약금액 노출)")

    print("\n[9] 잔여 — 대량·설정·정산·오프라인")
    appr = fn_source(app_t, app_s, "api_insurer_settlement_approve")
    chk('"SETTLEMENT_VOID"' in appr,
        "★ 취소된 정산을 완료 승인할 수 없다(지급·무효·목록은 이미 막고 있었다)")
    chk("send_file(full, mimetype=" in app_s and "conditional=True" in app_s,
        "★ 사진을 통째로 메모리에 올리지 않는다(스트리밍 + 304)")
    chk("send_from_directory, send_file" in app_s, "send_file 이 import 돼 있다")
    settings_fn = fn_source(app_t, app_s, "api_settings_set")
    chk('"ai_auto_threshold": (50, 100)' in settings_fn,
        "★ AI 자동승인 임계값이 범위 검사를 받는다(0 이면 시공 사진이 전량 자동승인된다)")
    chk("변경할 수 없는 항목입니다" in settings_fn,
        "★ 허용 목록 밖의 설정 키는 저장되지 않는다")
    chk("status='모집중' AND COALESCE(is_demo,0)=0" in app_s,
        "대시보드 출동 지표에도 데모 제외가 붙는다(운영 KPI 와 숫자가 갈렸다)")
    chk("upqAutoFlush" in ptl_s and "addEventListener('online'" in ptl_s,
        "★ '사진은 자동으로 올라갑니다'는 약속에 실제 트리거가 있다"
        " (배출 경로가 사람이 누르는 버튼 하나뿐이었다)")
    db_s = src("db.py")
    chk("idx_access_stat_path" in db_s and "idx_access_stat_role" in db_s,
        "접속통계가 풀스캔하지 않도록 복합 인덱스가 있다")
    chk("_src.backup(_dst)" in db_s,
        "★ db.py --reset 의 되돌림 사본이 WAL 커밋을 잃지 않는다(온라인 백업 API)")
    smoke = src("smoke_test.py")
    chk("BOKGUON_TEST_STAFF_PW" in smoke and 'password": "staff2026"' not in smoke,
        "★ 스모크 테스트에 비밀번호가 박혀 있지 않다(이 파일은 Z 드라이브로 나간다)")

    chk("NOTIFY_MAX_CHARS" in app_s and "message[:NOTIFY_MAX_CHARS" in app_s,
        "★ 알림 본문에 길이 상한이 있다"
        " (사건 지역 원문이 그대로 전 협력사 알림함으로 나갔다)")
    chk('업로드 용량 제한(10MB)' not in app_s,
        "★ 413 문구가 실제 상한을 말한다(실제는 260MB 인데 화면은 10MB 라고 했다)")
    brief = fn_source(app_t, app_s, "_defect_case_brief")
    chk("_cmap" in brief and "IN ({_ph})" in brief.replace('f"', '"'),
        "★ 하자 목록이 행마다 cases 를 치지 않는다(자매 함수는 이미 묶여 있었다)")
    snd = fn_source(app_t, app_s, "sweep_send_notifications")
    chk("철 지난 출동 문자" in snd,
        "★ 수배가 끝난 뒤 밀려 있던 출동 문자는 보내지 않는다(업체 헛걸음·헛전화)")
    chk("WHEN '출동수배' THEN 0" in snd,
        "★ 발송 순서가 접수순이 아니라 급한 것 먼저다(출동은 30분짜리다)")
    chk(app_s.count("ORDER BY id DESC LIMIT 300") >= 2,
        "하자 목록에 상한이 있다(쌓이기만 하는 표)",
        app_s.count("ORDER BY id DESC LIMIT 300"))

    print("\n[10] 실제로 도는가 — 새 DB 로 명령을 밟아 본다")
    tmp = tempfile.mkdtemp(prefix="bokguon_r7_")
    db = os.path.join(tmp, "r7.db")
    try:
        env = dict(os.environ)
        env.update({"BOKGUON_DB_PATH": db, "BOKGUON_ENV": "dev",
                    "BOKGUON_SEED_DEMO": "0", "PYTHONIOENCODING": "utf-8"})

        def run(*args):
            r = subprocess.run([sys.executable, "manage.py", *args], cwd=HERE, env=env,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
            return r.returncode, (r.stdout or "") + (r.stderr or "")

        run("init")
        run("migrate")
        rc, out = run("sweep", "--dry-run")
        chk(rc == 0 and "UnboundLocalError" not in out,
            "★ sweep --dry-run 이 끝까지 돈다", out.strip().splitlines()[-1:] or "")
        rc, out = run("create-admin", "r7bad", "--role", "운영관리자")
        chk(rc != 0 and "등급" in out,
            "★ 등급표에 없는 값으로는 계정이 만들어지지 않는다",
            out.strip().splitlines()[-1:] or "")
        rc, out = run("create-admin", "r7ok")
        chk(rc == 0 and "임시 비번" in out, "기본 등급으로는 정상 발급된다")
        conn = sqlite3.connect(db)
        role = conn.execute("SELECT role FROM admins WHERE username='r7ok'").fetchone()
        chk(role and role[0] in ("최고관리자", "중간관리자", "하위관리자"),
            "★ 발급된 계정의 등급이 권한 판정이 아는 값이다", role and role[0])
        conn.close()
        rc, out = run("check")
        chk("고아 행" in out or "데모 데이터 없음" in out,
            "빈 DB 에서도 점검이 끝까지 돈다")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
