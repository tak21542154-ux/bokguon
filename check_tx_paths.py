# -*- coding: utf-8 -*-
"""트랜잭션 종료 누락 점검.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

BEGIN IMMEDIATE 로 쓰기 잠금을 잡은 함수에서, 어떤 경로로든 나갈 때는
반드시 commit 이나 rollback 을 거쳐야 한다.
그러지 않고 close() 만 하면 잠금이 열린 채 커넥션이 사라져,
다음 쓰기가 busy_timeout(8초)을 다 기다린 뒤 실패한다.
증상이 '가끔 느리고 가끔 실패'라서 원인 찾기가 어렵다.

실행:  python check_tx_paths.py
"""
import ast
import io
import os
import sys

# ⚠ 윈도 기본 콘솔은 cp949 라 '—' 같은 문자를 print 하면 UnicodeEncodeError 로 죽는다.
#   점검 도구가 결과를 내기 직전에 죽으면 "통과했는지 실패했는지"를 알 수 없다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))


#  ⚠⚠ [라운드291] "conn" 하나만 하드코딩돼 있었다 — app.py 의
#    _upload_damage_photos 처럼 두 번째 커넥션을 c2 라는 별도 이름으로 여는
#    함수는 이 이름 매칭을 전혀 못 지나쳐(아래 calls_of 가 conn.* 만 보므로)
#    그 BEGIN IMMEDIATE 자체를 못 찾고, c2 임계구역 전체가 검사대상에도
#    안 들어간 채 조용히 통과했다. DB.get_db() 로 대입받는 이름은 전부 커넥션
#    변수로 본다 — 이 함수 안에서 실제로 쓰는 이름만 모으므로 새 별칭이
#    생겨도(c3 등) 하드코딩을 또 늘릴 필요가 없다.
def conn_names_of(fn):
    names = {"conn"}
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "get_db"):
            names.add(node.targets[0].id)
    return names


def calls_of(node, conn_names):
    """이 노드 아래에서 <커넥션>.<이름>() 호출을 순서대로 뽑는다."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            v = n.func.value
            if isinstance(v, ast.Name) and v.id in conn_names:
                out.append((n.lineno, n.func.attr, n))
    return out


def begins_immediate(fn, conn_names):
    #  ⚠⚠ [라운드291] calls_of() 의 순서는 ast.walk() 의 너비우선 순서이지
    #    소스상의 줄 순서가 아니다 — 중첩 깊이가 다른 BEGIN IMMEDIATE 가 두 개
    #    이상이면(app.py api_login_otp: if 안쪽 2475행과 그 뒤 최상위 2493행)
    #    더 얕은 쪽(2493)이 먼저 나와 진짜 첫 잠금(2475)을 놓쳤다 — 그 사이
    #    (2475~2493)의 return 들이 전부 "잠금 이전"으로 오판돼 검사를 건너뛴
    #    실측(2483·2487행, 지금은 둘 다 우연히 정상 커밋/롤백돼 있어 실제
    #    누락 사고는 아직 없다). 맨 처음 나온 것이 아니라 **가장 이른
    #    줄번호**를 쓴다.
    linenos = [lineno for lineno, attr, call in calls_of(fn, conn_names)
               if attr == "execute" and call.args
               and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str)
               and "BEGIN IMMEDIATE" in call.args[0].value]
    return min(linenos) if linenos else None


def _is_begin_immediate_call(n, conn_names):
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id in conn_names
            and n.func.attr == "execute" and n.args
            and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
            and "BEGIN IMMEDIATE" in n.args[0].value)


#  ⚠⚠ [라운드620] return 말고 continue/break 로도 반복문 한 회차를 빠져나갈 수
#    있다 — 아래 두 함수와 main() 의 검사 대상을 (Return, Continue, Break) 로
#    넓힌다. _own_loop_exits() 참고(같은 파일 아래).
_EXIT_TYPES = (ast.Return, ast.Continue, ast.Break)


def safe_lock_failure_returns(fn, conn_names):
    """BEGIN IMMEDIATE 호출 **자체**가 실패했을 때의 return/continue/break —
    잠금을 못 얻었으니 커밋/롤백이 필요 없다(예: sweep_warranty_expiry 의
    `except sqlite3.Error: return 0`). 이 노드들의 id() 집합을 돌려준다."""
    safe_ids = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        if not any(_is_begin_immediate_call(n, conn_names) for stmt in node.body for n in ast.walk(stmt)):
            continue
        for handler in node.handlers:
            for n in ast.walk(handler):
                if isinstance(n, _EXIT_TYPES):
                    safe_ids.add(id(n))
    return safe_ids


def safe_finally_protected_returns(fn):
    """try 의 body/handlers 안에서 하는 return/continue/break 은, 그 try 에
    finally 가 있으면 안전하다 — 파이썬은 그 문 위치와 무관하게 finally 를 반드시
    실행한 뒤에 실제로 빠져나간다. 텍스트 창(BEGIN IMMEDIATE ~ 그 문)은 이 finally
    가 소스상 **뒤에** 있으면 못 본다(예: try 앞부분에서 조기 종료, try 끝에
    finally: conn.commit()) — 구조로 직접 확인한다."""
    safe_ids = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try) or not node.finalbody:
            continue
        for stmt in node.body + node.handlers:
            for n in ast.walk(stmt):
                if isinstance(n, _EXIT_TYPES):
                    safe_ids.add(id(n))
    return safe_ids


#  ⚠⚠ [라운드620] "conn" 하나만 하드코딩됐다가 c2 등도 보게 넓힌 291라운드의
#    conn_names_of() 와 같은 종류의 사각지대를 continue/break 에서 찾았다 —
#    이 파일은 지금까지 함수 안의 return 문만 봤다(main() 참고). 그런데
#    BEGIN IMMEDIATE 를 반복문 **한 회차마다** 열고 그 회차 안에서 커밋/롤백하는
#    패턴(sweep_dispatches·sweep_webhook_retries·sweep_send_notifications·
#    sweep_auctions — 전부 실측 확인 결과 이미 정상)에서는 `continue`/`break` 로
#    그 회차를 빠져나가는 것도 return 과 똑같이 "이 회차에서 연 잠금을 안 닫고
#    나간다"는 같은 사고가 된다. 이 사각지대가 지금까지 실제 결함을 감춘 적은
#    없었지만(위 4개 함수 전수 확인), 이 도구 자신의 첫 줄 docstring("어떤
#    경로로든 나갈 때는 반드시 commit 이나 rollback 을 거쳐야 한다")이 이미
#    약속한 범위를 실제 구현이 못 지키고 있었다 — 같은 반복문 안에 새 continue/
#    break 가 하나 추가되는 다음 실수는 지금 이 파일로는 못 잡는다.
#    return 과 달리 continue/break 는 **자신을 감싼 가장 가까운 반복문에만**
#    영향을 준다 — 그 반복문 자체가 BEGIN IMMEDIATE 를 담고 있을 때만 검사
#    대상으로 삼는다(무관한 계산용 중첩 루프의 continue 까지 잡으면 오탐이 된다).
def _own_loop_exits(loop):
    """이 반복문 **몸통**(body)에 직접 속한 continue/break 만 뽑는다 — 중첩
    반복문·중첩 함수 안의 것은 그쪽 소관이라 내려가지 않는다."""
    out = []

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Continue, ast.Break)):
                out.append(child)
            elif isinstance(child, (ast.For, ast.AsyncFor, ast.While,
                                     ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                pass    # 중첩 반복문·함수 소관 — 내려가지 않는다
            else:
                walk(child)

    for stmt in loop.body:
        walk(stmt)
    return out


def _is_commit_or_rollback_call(n, conn_names):
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id in conn_names
            and n.func.attr in ("commit", "rollback"))


#  ⚠⚠ [라운드621] main() 의 "잠금~반환 구간에 commit/rollback 이 있었는가"
#    판정이 그 구간의 **원문 텍스트**에서 "conn.commit()"/"conn.rollback()"/
#    "finally" 라는 글자가 있는지만 봤다(텍스트 윈도 검색, ast 가 아니라 raw
#    source 줄만 join 해서 in 연산자로 찾음) — 이 저장소 자신의 관례상 그
#    구간에 "옛 코드는 conn.rollback()을 안 불렀다"·"finally 블록은 이제 안
#    쓴다"류의 **설명 주석**이 매우 흔한데(바로 이 세션이 되돌림-증명 코드에
#    쓴 표현들과 같은 문체), 그 주석 한 줄만 있어도 실제로는 그 갈래에
#    커밋/롤백 호출이 전혀 없거나 진짜 try/finally 구조가 없는 반환이
#    "안전"으로 오판됨을 synthetic 함수로 직접 재현해 확인(실행 기반 —
#    return 바로 앞줄에 "# ...conn.rollback()..." 뿐인 주석만 있어도, 또는
#    "finally" 라는 낱말만 있어도 통과 처리됨). AST 로 **진짜 호출·진짜
#    try/finally 구조**만 보도록 두 판정 다 바꾼다(텍스트 검색 완전 폐기).
#    중첩 헬퍼 함수 안의 commit/rollback 호출은(그 함수가 지금 당장 불렸다는
#    보장이 없으므로) main() 이 이미 exit_nodes 에 쓰는 것과 같은 inner
#    집합으로 제외한다 — 그러지 않으면 이번 수정 자체가 "중첩 함수 속 커밋도
#    바깥을 지켜준다"는 새 오판을 낳는다. 109개 실제 함수 재실행 결과는
#    여전히 클린(0건, 아래 회귀테스트가 재확인)이라 이 사각지대가 지금까지
#    실제 결함을 감춘 적은 없었지만, round124·574·620과 같은 "점검 도구
#    자신의 사각지대" 유형으로 다음에 추가되는 주석 한 줄이 조용히 이 방어를
#    무력화할 수 있는 상태였다.
def _commit_rollback_calls(fn, conn_names, inner):
    """이 함수 안에서 실제로 <conn>.commit()/<conn>.rollback() 을 호출하는
    모든 호출 노드(중첩 헬퍼 함수 안은 제외) — 주석 속 글자가 아니라 진짜 AST
    Call 노드만 본다."""
    return [n for n in ast.walk(fn)
            if id(n) not in inner and _is_commit_or_rollback_call(n, conn_names)]


def _parent_map(fn):
    """각 노드 → 바로 위 부모 노드(1촌만). if 가지 판정에 쓴다."""
    parents = {}
    for parent in ast.walk(fn):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


#  ⚠⚠ [라운드640] 위 _commit_rollback_calls() 로 찾은 commit/rollback 호출은
#    main() 에서 "잠금~반환 구간 줄 안에 있는가"만으로 그 return 을 지켜주는
#    것으로 인정됐다 — if/elif/else 로 갈라진 **서로 다른 가지**에 있어도
#    줄 순서만 그 구간 안이면 통과했다. synthetic 함수로 재현
#    (test_scan_round640_fixes.py):
#        if flag_a:
#            conn.commit(); return "a"
#        elif not flag_a:
#            return "b"          # commit/rollback 전혀 없음
#    "b" 가지의 return 은 실제로는 잠금이 안 닫힌 채 나가는데도, "a" 가지의
#    commit() 줄이 같은 (head, r.lineno] 구간에 있다는 이유만으로 클린으로
#    오판됐다(고치기 전 실측 — 아래 회귀테스트가 되돌림-증명으로 재확인).
#    공통 조상 if 에서 서로 다른 가지(body/orelse, elif 포함)로 갈라지면 그
#    commit 은 이 return 을 지키지 못한다 — 그 경우만 걸러낸다.
#    ⚠ 이번에 다루는 건 딱 이 모양(공통 if 조상에서 갈라지는 가지)뿐이다.
#    ①try/except 가지 사이의 같은 성격 사각지대(try 안의 commit 이 다른
#    except 가지의 return 을 못 지키는데 안전 처리되는 경우), ②서로 다른
#    if 로 각각 조기 return 하는 "가드절" 형태(예: `if a: return`; 그 뒤에
#    이어지는 `if b: return` — elif 가 아니라 두 개의 독립된 if 라 이 판정이
#    공유 조상을 못 찾는다)는 이번 판정 범위 밖이다 — 실제 4개 대상 파일에
#    이 두 모양이 있는지, 있다면 진짜 결함을 감추고 있는지는 **확인되지
#    않았다**(이번 고침으로 새로 위반이 잡히지도, 새 오탐이 생기지도 않았다는
#    사실만 아래 실측으로 확인). 완전한 제어흐름(지배자) 분석은 이 점검
#    도구의 몸집을 넘어서므로 다음 라운드감.
#  ⚠⚠ [라운드665] round640이 범위 밖으로 명시적으로 남기고 round663이 "다음
#    라운드감"으로 재확인한 두 사각지대 중 나머지 하나 — try 가지와 except
#    가지 사이("①try/except 가지 사이의 사각지대")를 이번에 닫는다. If 만 보던
#    이 함수는 Try 를 그냥 지나쳐 올라갔다 — try 본문의 commit() 과 형제
#    except 안의 return 이 서로 **배타적**(예외가 나면 그 지점 이후 try 본문은
#    실행되지 않는다)인데도 같은 가지로 오인되지 않고, 아예 "가지 구분 없음"
#    취급되어 _may_precede() 의 기본값(증명 못 하면 안전)에 그대로 넘어갔다.
#    synthetic 재현(아래 test_scan_round665_fixes.py):
#        try:
#            conn.execute(...); conn.commit(); return "ok"
#        except sqlite3.Error:
#            return "boom"        # commit/rollback 전혀 없음
#    "boom" 가지로 가려면 애초에 try 본문에서 예외가 나야 하므로 그 commit() 은
#    "boom" 가지에서 실행됐다는 보장이 전혀 없는데도, 고치기 전엔 클린으로
#    오판했다. handler 끼리도 같은 문제다(서로 다른 except 는 한쪽만 걸린다) —
#    각 handler 를 id() 로 구분해 서로 배타적인 별개 가지로 취급한다.
#    finally 는 기록하지 않는다 — 어느 가지를 타든 항상 실행되므로 배타적
#    가지가 아니다(이미 _finally_protecting_ends() 가 별도로 다룬다).
#    ⚠ 이 일반화를 실제 4개 대상 파일에 그대로 적용해 보니(수정 직후 1차
#    실측) **오탐 5건**이 새로 잡혔다 — 전부 진짜 결함이 아니라 이 판정이
#    아직 모르는 두 가지 안전한 관용구였다(아래 두 헬퍼가 각각 해소):
#      · app.py 4곳(sweep_no_bid_alert 6335·sweep_warranty_expiry 6725·
#        sweep_approval_overdue 6830·_sweep_award_approval 6933) —
#        `except Exception: ...; try: conn.rollback() except sqlite3.Error:
#        pass; return X` 모양. try 본문이 rollback 시도 **그 자체** 한 줄뿐인
#        방어용 try 를 "진짜 갈림길"로 봐서, 그 rollback 이 감싸는 바깥
#        except 가지와 같은 가지인데도 다르게 봤다(_is_bare_rollback_guard 로
#        투명 처리 — 옛 코드가 Try 를 아예 안 보던 것과 같은 효과를 이 좁은
#        모양에만 남긴다).
#      · dispatch.py:1020 sweep_dispatches() — 바깥 try 의 유일한 handler가
#        `_release_lease(conn, "오류"); raise` 로 **항상 다시 던진다**. 다시
#        던지는 handler 는 절대 try 문 **다음** 코드로 이어지지 않으므로
#        (그 handler 자신의 return 등은 별도 r 로 이미 따로 검사된다), 그
#        handler 가 커밋하는지는 "그 다음 코드가 안전한가"와 무관한데도
#        _try_guarantees_commit() 이 무조건 모든 handler 에게 커밋을
#        요구했다(_handler_falls_through 로 그런 handler 를 제외).
def _is_bare_rollback_guard(try_node, conn_names):
    """`try: <conn>.rollback() except ...: ...` — 이 try 하나의 존재 이유가
    그 rollback 시도 자체를 감싸는 것뿐인가(본문이 rollback 호출 한 줄).
    예외 처리 중 마지막 정리 시도이고, 그 시도 자체가 또 실패하면 이 코드가
    더 할 수 있는 일이 없다 — 배타적 가지로 치지 않는다. commit() 한 줄짜리는
    포함하지 않는다 — 커밋 실패는 트랜잭션 상태가 불확실해져 오히려 뒤이은
    rollback 시도가 꼭 필요한 상황이라, 여기서 눈감아주면 안 된다."""
    if len(try_node.body) != 1:
        return False
    stmt = try_node.body[0]
    return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Attribute)
            and isinstance(stmt.value.func.value, ast.Name)
            and stmt.value.func.value.id in conn_names
            and stmt.value.func.attr == "rollback")


def _branch_path(node, parents, fn, conn_names):
    """node 에서 fn 까지 조상을 타고 올라가며, 갈라지는 if/try 마다
    (그 노드 자신, 어느 가지였는지) 를 기록한다."""
    path = []
    child = node
    while True:
        parent = parents.get(id(child))
        if parent is None or parent is fn:
            break
        if isinstance(parent, ast.If):
            if any(child is b for b in parent.body):
                path.append((parent, "body"))
            elif any(child is b for b in parent.orelse):
                path.append((parent, "orelse"))
        elif (isinstance(parent, ast.Try) and parent.handlers
                and not _is_bare_rollback_guard(parent, conn_names)):
            if any(child is h for h in parent.handlers):
                path.append((parent, ("except", id(child))))
            elif any(child is b for b in parent.body) or any(child is b for b in parent.orelse):
                path.append((parent, "try"))
            # else: child 는 finalbody — 배타적 가지가 아니므로 기록하지 않는다
        child = parent
    return path


def _branch_has_commit(stmts, conn_names, inner):
    """이 문장 목록(if 의 body 또는 orelse) 어딘가에 실제 commit/rollback
    호출이 있는가(중첩 함수 안은 제외 — main() 이 이미 쓰는 inner 집합)."""
    return any(_is_commit_or_rollback_call(n, conn_names)
               for stmt in stmts for n in ast.walk(stmt) if id(n) not in inner)


def _if_guarantees_commit(if_node, conn_names, inner):
    """이 if/else 는 **어느 가지를 타든** commit 이나 rollback 을 반드시
    거치는가 — 그렇다면 이 if 문 바로 다음에 오는 코드(그 if 안이 아니라)는
    실제로 어느 가지가 실행됐는지와 무관하게 이미 커밋/롤백이 끝난 뒤다.
    orelse 가 없으면(그 if 를 건너뛰는 경로엔 commit 이 전혀 없다) 보장할 수 없다.
    """
    if not if_node.orelse:
        return False
    return (_branch_has_commit(if_node.body, conn_names, inner)
            and _branch_has_commit(if_node.orelse, conn_names, inner))


_NO_FALLTHROUGH = (ast.Raise, ast.Return, ast.Continue, ast.Break)


def _handler_falls_through(handler):
    """이 except 블록이 try 문 **다음** 코드로 실제로 이어질 수 있는가 —
    마지막 문장이 raise/return/continue/break 면 이 handler 는 함수를
    빠져나가거나 예외를 다시 던지거나 반복문을 벗어나며 끝나므로, try 문
    다음 코드로는 결코 이어지지 않는다(그 handler 자신의 return 등은 main()
    이 별도의 r 로 이미 독립적으로 검사한다 — 여기서는 "이 handler 가 try
    다음 코드로 이어지는가"만 본다)."""
    return not (handler.body and isinstance(handler.body[-1], _NO_FALLTHROUGH))


def _try_guarantees_commit(try_node, conn_names, inner):
    """이 try/except 는 **정상 완료든, try 다음 코드로 이어지는 어떤 except 로
    빠지든** commit 이나 rollback 을 반드시 거치는가 — if/else 의
    _if_guarantees_commit() 과 같은 역할이지만 가지가 두 개가 아니라
    (본문+orelse) 대 handler 여러 개다. try 다음으로 이어지지 않는 handler
    (raise/return/continue/break 로 끝남, _handler_falls_through)는 애초에
    "다음 코드"에 영향을 못 주므로 커밋 요구에서 뺀다. handler 가 하나도
    없으면(_branch_path() 가 애초에 이 갈래를 기록하지 않는다) 호출되지 않는다."""
    if not try_node.handlers:
        return False
    normal = _branch_has_commit(try_node.body + try_node.orelse, conn_names, inner)
    falling = [h for h in try_node.handlers if _handler_falls_through(h)]
    return normal and all(_branch_has_commit(h.body, conn_names, inner) for h in falling)


#  ⚠⚠ [라운드663] 라운드640 이 "확인되지 않았다"고 남긴 두 사각지대 중 하나
#    ("서로 다른 if 로 각각 조기 return 하는 가드절 형태")를 확인해 보니 실제로
#    이 함수 자체에 살아 있는 결함이었다 — `r_path.get(if_id, branch) == branch`
#    는 **r 이 그 if 안에 아예 없을 때도**(딕셔너리 기본값이 그대로 branch 와
#    같아 조건을 만족한 것으로 침) 통과시켰다. "증명 못 하면 통과"라는 이
#    함수의 원래 취지(휴리스틱, 아래 docstring)를 넘어, r 이 그 if 문 **밖**
#    (다음 문장)에 있는 경우까지 "같은 가지"로 오판했다 — synthetic 재현:
#        if a: conn.commit(); return "x"
#        if b: return "y"      # commit 없음, if a 에 else 없음
#    b 가 True 인 실행에서는 if a 의 commit 이 전혀 안 도는데도, 고치기 전
#    코드는 "may_precede == True"로 봐서 return "y" 를 안전하다고 오판했다
#    (아래 test_scan_round663_fixes.py 의 되돌림-증명이 이 정확한 모양으로
#    재현·확인한다).
#    그런데 이 결함을 "r 이 그 if 안에 없으면 무조건 False"로만 고치면 이번엔
#    **정반대의 새 오탐**이 생긴다 — 이 저장소에서 실제로 가장 흔한 관용구
#    (`if X: conn.commit() else: conn.rollback()` 뒤에 무조건 return, 예:
#    sweep_review_reminders 6636행·api_defect_update 15894행)는 두 가지가
#    **서로 다른** 가지에서 각각 commit·rollback 을 부르고 그 if/else **다음**
#    문장이 무조건 실행된다 — 그 return 은 어느 쪽 if_id 에도 안 속하지만
#    실제로는 완전히 안전하다. _if_guarantees_commit() 로 "이 if 는 가지에
#    상관없이 항상 commit/rollback 을 거친다"를 먼저 확인해, 그런 경우에만
#    "그 if 안에 없어도 안전"으로 봐준다 — 그 밖의(guard 절처럼 else 가 아예
#    없는) 경우만 진짜 위험으로 남긴다.
#  ⚠⚠ [라운드665] 위 round663 이 미룬 "①try/except 가지 사이의 사각지대"를
#    같은 방식으로 닫는다 — 공통 조상이 If 가 아니라 Try 여도, 배타적인 다른
#    가지면 그 Try 가 어느 가지든 항상 commit 을 보장하지 않는 한 위험으로
#    본다(_try_guarantees_commit). If/Try 어느 쪽이든 판정 골격이 같아 변수
#    이름을 if_node 대신 범용 anc(조상)로 바꿨다.
#    ⚠ synthetic 으로 직접 돌려 보니(아래 test_scan_round665_fixes.py) "r 이
#    anc 의 가지 밖(다음 코드)에 있다"(r_path 에 anc 자체가 없음)와 "r 이 anc의
#    **다른** 가지 안에 있다"(r_path 에 anc 는 있는데 값이 다르다)를 구분하지
#    않고 둘 다 곧장 _try_guarantees_commit() 로 넘기면, 정작 지금 검사 중인
#    r **자신**이 속한 handler 가 (return 으로 끝난다는 이유로) "다음 코드로
#    안 이어지는 handler"로 스스로 면제돼 버려 이 라운드가 잡으려던 바로 그
#    genuine 사각지대(try 본문 commit, 형제 except 는 무방비 return)를 다시
#    놓쳤다. r 이 이미 그 조상의 **어느 가지**엔가 속해 있다면(anc 자체가
#    r_path 에 있다) c 와 다른 가지라는 사실만으로 충분히 위험 — guarantee
#    우회는 r 이 조상 **밖**(다음 코드)에 있을 때만 쓴다.
def _may_precede(commit_node, r, parents, fn, conn_names, inner):
    """commit_node 가 r 에 이르는 모든 실행 경로에서 실제로 실행됐다고
    볼 수 있는가(휴리스틱 — 증명하지 못하면 안전 쪽으로, 즉 함수 이름대로
    "그럴 수 있다"쪽으로 기운다. 완전한 지배자 분석은 이 도구의 몸집을
    넘어선다는 것이 라운드640 의 결론이었다)."""
    c_path = _branch_path(commit_node, parents, fn, conn_names)
    r_path = dict((id(node), branch) for node, branch in _branch_path(r, parents, fn, conn_names))
    for anc, branch in c_path:
        r_branch = r_path.get(id(anc))
        if r_branch == branch:
            continue                                   # 같은 가지 — 안전
        if r_branch is not None:
            return False                               # r 이 anc 의 다른(배타적인) 가지 안 — 곧장 위험
        if isinstance(anc, ast.If) and _if_guarantees_commit(anc, conn_names, inner):
            continue                                   # r 이 조상 밖 + 가지 무관 항상 거침 — 안전
        if isinstance(anc, ast.Try) and _try_guarantees_commit(anc, conn_names, inner):
            continue                                   # r 이 조상 밖 + 정상경로·모든 except 항상 거침 — 안전
        return False
    return True


def _finally_protecting_ends(fn, conn_names, inner):
    """finally 블록 안에서 실제로 commit/rollback 을 호출하는 try 문들의
    **끝 줄번호**를 돌려준다 — 그 지점 이후에는 그 finally 가 이미 실행된
    뒤임을 구조로 보장한다("finally" 라는 글자가 있는지가 아니라, 진짜 그런
    구조가 있는지를 ast 로 본다)."""
    out = []
    for node in ast.walk(fn):
        if id(node) in inner or not isinstance(node, ast.Try) or not node.finalbody:
            continue
        if any(_is_commit_or_rollback_call(n, conn_names)
               for stmt in node.finalbody for n in ast.walk(stmt) if id(n) not in inner):
            out.append(node.end_lineno)
    return out


#  ⚠⚠ [라운드124] app.py 만 하드코딩해서 봤다 — docstring 은 "BEGIN IMMEDIATE 로
#    쓰기 잠금을 잡은 함수" 라고 일반적으로 말하면서 실제로는 db.py·dispatch.py·
#    manage.py 도 BEGIN IMMEDIATE 를 쓰는 걸 한 번도 본 적이 없었다(dispatch.py
#    10개·manage.py 2개 함수가 이 점검을 완전히 벗어나 있었다). db.py 는 해당
#    함수가 없어 뺀다.
#  ⚠⚠ [라운드574] 라운드124가 고친 기준("BEGIN IMMEDIATE 를 실제로 쓰는 모든
#    함수")을 이 파일 자신이 다시 어기고 있었다 — TARGET_FILES 는 여전히
#    "app.py 가 import 하는가"로 뽑힌 3개뿐이었는데, seed_boq.py(app.py 가
#    import 하지 않는 독립 CLI — manage.py 와 정확히 같은 성격: 운영자가 손으로
#    돌려 표준단가표를 실제 운영 DB(BOKGUON_DB_PATH 미지정 시 bokguon.db)에
#    적재한다, activity_log 실측상 가장 자주 쓰이는 실제 적재 경로)의
#    load()(200행)도 conn.execute("BEGIN IMMEDIATE") 를 쓴다는 사실은 이제껏
#    한 번도 반영되지 않았다(전체 저장소 grep 재확인 — BEGIN IMMEDIATE 를
#    실제로 쓰는 프로덕션 파일은 정확히 이 4개뿐이고, test_*.py·run_all_tests.py
#    는 단명 프로세스라 이 도구가 막으려는 "잠금이 열린 채 남아 다음 쓰기가
#    busy_timeout 을 다 기다리는" 증상과 무관해 원래부터 범위 밖이다). 실측:
#    load() 는 유일한 return 이 try/finally(conn.close()) **밖**의 함수 끝
#    한 곳뿐이라 이번 확장으로도 위반 0건(클린) — round124·571 과 같은 "점검
#    도구 자신의 사각지대" 유형이었을 뿐, 지금까지 이 CLI 를 돌려서 실제
#    사고가 난 적은 없다.
TARGET_FILES = ("app.py", "dispatch.py", "manage.py", "seed_boq.py")


def main():
    bad = []
    checked = 0
    for relname in TARGET_FILES:
        path = os.path.join(HERE, relname)
        src = io.open(path, encoding="utf-8").read()
        tree = ast.parse(src)
        lines = src.splitlines()

        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            conn_names = conn_names_of(fn)
            bl = begins_immediate(fn, conn_names)
            if not bl:
                continue
            checked += 1
            # 중첩 함수(안쪽 헬퍼) 안의 return 은 라우트를 빠져나가는 게 아니다.
            #  이걸 안 걸러내면 헬퍼의 return 이 전부 '잠금 미해제'로 잘못 잡힌다.
            inner = set()
            for sub in ast.walk(fn):
                if sub is fn or not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                for n in ast.walk(sub):
                    inner.add(id(n))
            #  ⚠⚠ [라운드124] BEGIN IMMEDIATE 자체가 실패한 except 안의 return 은
            #    잠금을 못 얻었으니 커밋/롤백이 필요 없다(sweep_warranty_expiry·
            #    sweep_review_reminders 의 `except sqlite3.Error: return ...` 이
            #    실측으로 확인된 예다) — 구조적으로 안전한 return 으로 미리 뺀다.
            safe_lock_fail = safe_lock_failure_returns(fn, conn_names)
            safe_finally = safe_finally_protected_returns(fn)
            parents = _parent_map(fn)

            # return 외에, "이 함수 안에서 BEGIN IMMEDIATE 를 담은 반복문"의
            # continue/break 도 같은 사각지대다(위 _own_loop_exits 주석 참고).
            exit_nodes = [r for r in ast.walk(fn) if isinstance(r, ast.Return) and id(r) not in inner]
            for loopnode in ast.walk(fn):
                if (id(loopnode) in inner
                        or not isinstance(loopnode, (ast.For, ast.AsyncFor, ast.While))
                        or begins_immediate(loopnode, conn_names) is None):
                    continue
                exit_nodes.extend(_own_loop_exits(loopnode))

            # 이 함수 안의 모든 return/continue/break 마다, 그 앞에 commit/rollback 이 있었는지 본다.
            for r in exit_nodes:
                if id(r) in safe_lock_fail or id(r) in safe_finally:
                    continue
                if r.lineno <= bl:          # 잠금 이전의 return 은 대상 아님
                    continue
                #  ⚠⚠ [라운드124] 고정 6줄 룩백 창은 app.py 바깥의 실전 코드에서
                #    오탐을 낸다 — 커밋 후 후처리 코드가 있거나(dispatch.py:
                #    assign_dispatch, 커밋~return 사이 9줄), 반복문 안에서 반복마다
                #    자체 커밋/롤백 쌍을 쓰고 루프 밖에서 최종 return 만 하거나
                #    (dispatch.py:sweep_dispatches), try/finally 로 닫은 뒤 return 이
                #    룩백 창 밖에 있다(manage.py:cmd_prune_orphans). 작위적인 줄수
                #    상한 대신, BEGIN IMMEDIATE 지점부터 이 return 까지 함수 안의
                #    전체 구간을 본다 — 그 구간 어디에도 commit/rollback/finally 가
                #    없을 때만 진짜 의심 사례로 본다.
                head = bl
                #  ⚠⚠ [라운드621] 예전엔 여기서 원문 텍스트 윈도(lines[head:r.lineno]를
                #    join한 문자열)에 "conn.commit()"/"conn.rollback()"/"finally" 라는
                #    글자가 있는지만 봤다 — 주석에 그 글자가 있어도 통과됐다(위 두 헬퍼
                #    함수 docstring 참고). 이제 진짜 AST 호출·진짜 try/finally 구조만 본다.
                #  ⚠⚠ [라운드640] 그 AST 호출도 "줄 구간 안"이기만 하면 인정됐다 — if/
                #    elif/else 로 갈라진 서로 다른 가지의 commit 이 이 return 을 지켜주는
                #    것으로 오판될 수 있었다(위 _may_precede 주석 참고). 공통 조상 if 에서
                #    갈라지지 않는(상호배타가 아닌) 호출만 인정한다.
                if any(head < c.lineno <= r.lineno and _may_precede(c, r, parents, fn, conn_names, inner)
                       for c in _commit_rollback_calls(fn, conn_names, inner)):
                    continue
                # try/finally 로 닫는 형태(그 finally 가 실제로 commit/rollback 을
                # 부르는 진짜 구조)면 정상 — 구간 안에서 그 try/finally 전체가 이미
                # 끝나 있어야(그래야 이 return 에 닿기 전 finally 실행이 보장된다).
                if any(head < end <= r.lineno
                       for end in _finally_protecting_ends(fn, conn_names, inner)):
                    continue
                bad.append((relname, fn.name, r.lineno, lines[r.lineno - 1].strip()[:70]))

    print("=" * 66)
    print(f"  트랜잭션 종료 점검 — BEGIN IMMEDIATE 쓰는 함수 {checked}개"
          f" ({', '.join(TARGET_FILES)})")
    print("=" * 66)
    if not bad:
        print("  모든 반환 경로가 commit 또는 rollback 을 거칩니다 ✓")
        return 0
    for relname, name, ln, text in bad:
        print(f"  {relname}:{ln}  {name}()")
        print(f"      {text}")
    print("-" * 66)
    print(f"  확인 필요 {len(bad)}건")
    return 1


if __name__ == "__main__":
    sys.exit(main())
