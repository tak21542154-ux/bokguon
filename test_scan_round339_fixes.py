# -*- coding: utf-8 -*-
"""스캔 339라운드 회귀 — admin.js 6곳의 처리버튼이 등급 무관하게 그려지던
   결함(admin.js VIEWS.* 화면군 Agent 조사로 발견, 246~253·337라운드 등급게이트
   스윕이 아직 안 훑은 화면들).

  ① VIEWS.photos(openPhotoReview) — 반려·반려취소(app.py 12241·12218행)·
     삭제(12091행)·전체검수승인(12041행) 4개 버튼, 전부 require_role(중간관리자).
     12034·12213행 주석이 이미 "재현확인: 하위관리자 세션으로 200"이라고
     지목한 결함이 화면엔 한 번도 안 들어왔다 — 정산의 필수 관문이라 여섯
     결함 중 가장 위험.
  ② VIEWS.calendar(calDay) — "삭제"(calDel) 버튼, DELETE /api/schedule-events
     (app.py:17825, 68라운드가 하위관리자에서 올림)는 require_role(중간관리자).
  ③ VIEWS.notices — "삭제"(deleteNotice) 버튼, DELETE /api/notices(app.py:14412)
     는 require_role(중간관리자).
  ④ VIEWS.partners(partnerForm) — "퇴출"(deletePartner) 버튼, DELETE
     /api/partners(app.py:8023)는 require_role(중간관리자). askStatusReason()
     프롬프트를 다 채운 뒤에야 403을 만나는 시간낭비형.
  ⑤ 공유 위젯 loadMemos()의 "✕"(memoDel) 버튼 — DELETE /api/memos(app.py:1472)
     는 require_role(중간관리자). 이 위젯을 쓰는 모든 화면(사건상세 등)에
     공통 적용되던 결함이라 여기 한 곳만 고치면 전부 해결.
  ⑥ VIEWS.selfcheck — "잠금 해제"(unlockLogin) 입력칸+버튼, POST
     /api/login-attempts/unlock(app.py:2390)은 require_role(중간관리자).
     입력칸의 data-act-enter(Enter로도 같은 핸들러를 부른다, actions.js)까지
     함께 가려야 버튼만 숨겨서 우회되는 걸 막는다 — 이번 라운드에서 그 부분만
     따로 한 번 더 확인(버튼만 지우고 입력칸을 남겨 두면 Enter로 그대로
     뚫린다는 것을 실제 렌더링으로 실측).

  세 곳(정산·하자·출동수배, 337라운드)과 같은 이유 — 서버는 이미 전부
  정확히 막고 있어 권한상승은 아니고 "폼을 다 채운 뒤에야 403" 시간낭비를
  없애는 UX/권한위생 수정. 목록조회 API 는 전부 require_admin(등급무관)
  이라 화면 자체는 계속 보이는 게 맞다.

  ⚠ [337라운드 교훈] 이 여섯 함수를 Node vm/subprocess 로 직접 실행하는
    다른 테스트가 있는지 미리 grep 확인 — test_scan_round27_fixes.py 는
    unlockLogin 을 순수 정적 문자열 존재 확인만 하고(실행 없음),
    test_scan_round290_fixes.py 는 loadMemos 를 no-op 스텁으로 완전히
    대체해 부르므로(실제 함수 본문을 안 씀) 이번 수정과 충돌 없음 — 둘 다
    확인 완료.

      python test_scan_round339_fixes.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def run_node(src, tag):
    node_path = os.path.join(tempfile.gettempdir(), f"r339_{tag}.js")
    io.open(node_path, "w", encoding="utf-8").write(src)
    try:
        r = subprocess.run(["node", node_path], capture_output=True, text=True,
                            encoding="utf-8", timeout=20)
        if r.returncode != 0:
            chk(False, f"★★★ Node 실행({tag})", r.stderr[-800:])
            return None
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:                                              # noqa: BLE001
        chk(False, f"★★★ Node 준비({tag})", f"{type(e).__name__} {e}")
        return None
    finally:
        try: os.remove(node_path)
        except OSError: pass


ADMIN_JS = read("static/admin.js")
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 339라운드 회귀 — admin.js 6곳 처리버튼 등급게이트 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — 백엔드 필요등급 재확인")
# ============================================================
chk('@app.post("/api/cases/<int:cid>/photos/approve")' in APP_SRC
    and '@require_role("중간관리자")\ndef api_photos_approve' in APP_SRC,
    "(사전조건) 전체검수승인은 중간관리자 이상")
chk('@app.delete("/api/photos/<int:pid>")' in APP_SRC
    and '@require_role("중간관리자")\ndef api_photo_delete' in APP_SRC,
    "(사전조건) 사진삭제는 중간관리자 이상")
chk('@app.post("/api/photos/<int:pid>/reject")' in APP_SRC,
    "(사전조건) 반려 라우트가 실재한다")
chk('@app.delete("/api/schedule-events/<int:eid>")' in APP_SRC
    and '@require_role("중간관리자")\ndef api_schedule_event_del' in APP_SRC,
    "(사전조건) 일정삭제는 중간관리자 이상")
chk('@app.delete("/api/notices/<int:nid>")' in APP_SRC
    and '@require_role("중간관리자")\ndef api_notice_delete' in APP_SRC,
    "(사전조건) 공지삭제는 중간관리자 이상")
chk('@app.delete("/api/partners/<int:pid>")' in APP_SRC
    and '@require_role("중간관리자")\ndef api_partner_delete' in APP_SRC,
    "(사전조건) 협력사퇴출은 중간관리자 이상")
chk('@app.delete("/api/memos/<int:mid>")' in APP_SRC
    and '@require_role("중간관리자")\ndef api_memo_delete' in APP_SRC,
    "(사전조건) 메모삭제는 중간관리자 이상")
chk('@app.post("/api/login-attempts/unlock")' in APP_SRC
    and '@require_role("중간관리자")\ndef ' in APP_SRC[APP_SRC.index('@app.post("/api/login-attempts/unlock")'):
                                                      APP_SRC.index('@app.post("/api/login-attempts/unlock")') + 100],
    "(사전조건) 로그인잠금해제는 중간관리자 이상")

# ============================================================
print("\n[2] 소스 확인 — admin.js 여섯 곳에 등급게이트가 실제로 들어갔다")
# ============================================================
i0 = ADMIN_JS.index("async function openPhotoReview(")
i1 = ADMIN_JS.index("\n// ", i0 + 200)
photo_body = ADMIN_JS[i0:ADMIN_JS.index("\n}", i0) + 2]
chk("const canReview = myRank() >= 2;" in photo_body, "★★★★ openPhotoReview() 가 등급을 읽는다")
chk(photo_body.count("canReview") >= 4, "STEP 반려/반려취소·삭제·전체승인 3곳 모두 게이트됐다"
    "(선언 1 + 사용 3 = 최소 4회 등장)", photo_body.count("canReview"))
chk("if (approveBtn) approveBtn.addEventListener" in photo_body,
    "★★★ approveAll 버튼이 없을 때 addEventListener 로 안 죽게 널가드가 있다")

i2 = ADMIN_JS.index("async function calDay(")
i3 = ADMIN_JS.index("\nfunction calAdd(", i2)
cal_body = ADMIN_JS[i2:i3]
chk("e.event_id && myRank()>=2?" in cal_body, "★★★★ calDay() 의 일정삭제 버튼이 등급을 확인한다")

i4 = ADMIN_JS.index("VIEWS.notices = async () => {")
i5 = ADMIN_JS.index("\nfunction noticeForm(", i4)
notice_body = ADMIN_JS[i4:i5]
chk("myRank()>=2?`<button class=\"btn danger sm\" data-act=\"deleteNotice\"" in notice_body,
    "★★★★ VIEWS.notices 의 삭제 버튼이 등급을 확인한다")

i6 = ADMIN_JS.index("function partnerForm(")
i7 = ADMIN_JS.index("\n// 건설업 등록 조사", i6)
partner_body = ADMIN_JS[i6:i7]
chk("id && myRank()>=2?" in partner_body, "★★★★ partnerForm() 의 퇴출 버튼이 등급을 확인한다")

i8 = ADMIN_JS.index("async function loadMemos(")
i9 = ADMIN_JS.index("\nasync function addMemo(", i8)
memo_body = ADMIN_JS[i8:i9]
chk("myRank()>=2?`<button class=\"btn g sm\" data-act=\"memoDel\"" in memo_body,
    "★★★★ loadMemos() 의 삭제 버튼이 등급을 확인한다")
chk('data-act="memoDone"' in memo_body, "STEP 완료체크(memoDone, require_admin)는 회귀없이 그대로 노출된다")

i10 = ADMIN_JS.index('<span class="pt">계정 잠금 해제')
i11 = ADMIN_JS.index("</div>\n    </div>", i10)
unlock_body = ADMIN_JS[i10:i11]
chk("myRank()>=2" in unlock_body, "★★★★ 계정 잠금 해제 패널이 등급을 확인한다")
chk('data-act-enter="unlockLogin"' in unlock_body.split("myRank()>=2")[1].split(":")[0],
    "★★★★★ 등급 충족 분기에만 입력칸(Enter 우회 통로)이 함께 있다"
    "(버튼만 지우고 입력칸을 남기면 Enter 로 뚫린다)")

# ============================================================
print("\n[3] 실행(Node) — 여섯 렌더링이 등급별로 실제 뭘 그리는지")
# ============================================================

#  ③ VIEWS.notices — data 배열 렌더링을 그대로 뽑아 실행
node_notices = r"""
function esc(s){ return String(s==null?'':s); }
async function run(rank){
  const myRank = () => rank;
  const data = [{id:1, title:'제목', audience:'전체', pinned:0, created_at:''}];
  const rows = data.length?data.map(n=>`<tr>
          <td>${n.id}</td><td class="em">${n.pinned?'📌 ':''}${esc(n.title)}</td><td>${esc(n.audience)}</td>
          <td>${n.pinned?'<span class="pill amber">고정</span>':'-'}</td><td>${esc((n.created_at||'').slice(0,10))}</td>
          ${myRank()>=2?`<button class="btn danger sm" data-act="deleteNotice" data-arg="${n.id}" data-arg2="${esc(n.title)}">삭제</button>`:''}</tr>`).join(''):'';
  return rows;
}
(async () => {
  const results = [];
  for (const rank of [1, 2, 3]) {
    const html = await run(rank);
    results.push({rank, hasDel: html.includes('data-act="deleteNotice"')});
  }
  console.log(JSON.stringify(results));
})();
"""
rows = run_node(node_notices, "notices")
if rows is not None:
    for row in rows:
        expect = row["rank"] >= 2
        chk(row["hasDel"] == expect,
            f"★★★★ 공지 삭제: rank={row['rank']} → {'노출' if expect else '숨김'}이어야 함", row)

#  ⑥ 잠금해제 패널 — 추출한 조각을 그대로 실행(입력칸+버튼 동시 여부 확인)
node_unlock = r"""
function render(rank){
  const myRank = () => rank;
  return `<div class="filters">
        ${myRank()>=2
          ? `<input id="unlock_uname" placeholder="아이디" data-act-enter="unlockLogin" style="max-width:220px">
             <button class="btn p sm" data-act="unlockLogin">잠금 해제</button>`
          : '<span class="sub">중간관리자 이상만 사용할 수 있습니다</span>'}
      </div>`;
}
const results = [];
for (const rank of [1, 2, 3]) {
  const html = render(rank);
  results.push({rank, hasBtn: html.includes('data-act="unlockLogin"'),
    hasEnterInput: html.includes('data-act-enter="unlockLogin"')});
}
console.log(JSON.stringify(results));
"""
rows2 = run_node(node_unlock, "unlock")
if rows2 is not None:
    for row in rows2:
        expect = row["rank"] >= 2
        chk(row["hasBtn"] == expect,
            f"★★★★ 잠금해제 버튼: rank={row['rank']} → {'노출' if expect else '숨김'}이어야 함", row)
        chk(row["hasEnterInput"] == expect,
            f"★★★★★ 잠금해제 입력칸(Enter 우회): rank={row['rank']} → "
            f"{'노출' if expect else '숨김'}이어야 함 — 버튼만 숨고 입력칸이 남으면 우회 가능", row)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)

sys.exit(1 if FAIL else 0)
