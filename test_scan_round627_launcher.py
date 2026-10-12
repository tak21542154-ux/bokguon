# -*- coding: utf-8 -*-
"""라운드627 회귀(test_scan_round627_fixes.py) 전용 launcher —
`python manage.py <args...>` 를 그대로 흉내 내되, manage.py 실제 파일은
디스크에서 전혀 건드리지 않는다.

round475가 세운 launcher 패턴(test_scan_round475_launcher.py) 그대로 —
manage.py 는 `python manage.py <cmd>` 서브프로세스 호출이라 477·509처럼
같은 프로세스 안에서 view_functions 를 스왑할 대상(Flask 라우트)이 없다.

R627_BROKEN=1 이면 manage.py 소스를 읽어(디스크는 그대로) cmd_go_live()의
n_insurer 계산 + 사후요약의 발주처 0곳 경고 두 곳만 옛(회귀 전) 코드로
메모리에서 치환한 뒤 그 텍스트를 exec 한다 — 실제 manage.py 파일은 이
프로세스에서도 전혀 안 쓴다.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGE_PATH = os.path.join(HERE, "manage.py")
_src = io.open(MANAGE_PATH, encoding="utf-8").read()

if os.environ.get("R627_BROKEN") == "1":
    OLD_BLOCK_1 = '''        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]
        n_partner = conn.execute("SELECT COUNT(*) n FROM partners").fetchone()["n"]
    except sqlite3.Error as e:'''

    NEW_BLOCK_1 = '''        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]
        n_partner = conn.execute("SELECT COUNT(*) n FROM partners").fetchone()["n"]
        #  ⚠⚠ [라운드627] round406이 발견하고 미뤄 둔 형제 결함 — 관리자(n_admin)가
        #    0명이면 아래 요약이 경고+복구명령까지 주는데, 바로 위 ②단계가
        #    is_demo=1 전량을 통째로 지우는 insurers(DEMO_TABLES 소속)는 몇 곳이
        #    남았는지 어디에도 안 나온다. round626 실측(운영DB, 읽기전용): 활성
        #    발주처 7곳 중 6곳이 is_demo=1 — 오늘 go-live를 돌리면 실제로 1곳만
        #    남는데도 화면에 안 보인다. 삭제 로직은 그대로 두고(정책 변경 아님),
        #    admins·partners와 나란히 개수만 센다.
        n_insurer = conn.execute("SELECT COUNT(*) n FROM insurers").fetchone()["n"]
    except sqlite3.Error as e:'''

    OLD_BLOCK_2 = '''    print("─" * 62)
    ok(f"협력업체 {n_partner}개사 유지됨")
    if n_admin == 0:
        warn("관리자 계정이 하나도 없습니다. 반드시 만드세요:")
        print("      python manage.py create-admin <아이디> --role 최고관리자")
        print("      ※ 'admin' 이 아닌 실제 담당자 아이디를 쓰세요.")
    else:
        ok(f"관리자 계정 {n_admin}개 유지")
    print()
    print("  다음 단계:  python manage.py check")'''

    NEW_BLOCK_2 = '''    print("─" * 62)
    #  ⚠⚠ [라운드630] 바로 아래 n_insurer·n_admin과 같은 자리에서 나란히 세던
    #    n_partner만 이 요약 자신에서는 형제 취급을 못 받았다 — round627이
    #    발주처 0명을, round629가 "관리자는 있지만 최고관리자 0명"을 각각
    #    경고로 올렸는데, 바로 이 줄의 협력업체만 n_partner==0이어도 무조건
    #    ok()로 "유지됨"을 찍는다. go-live는 partners 행 자체를 지우지
    #    않지만(문서화된 대로 실제 영업 자산이라 보존 — 로그인 수단만
    #    정리), partners에는 create-admin/create-insurer 같은 CLI가 없어
    #    콘솔에서만 등록·삭제된다 — 누군가 go-live 전에 콘솔에서 협력사를
    #    전부 지웠거나(예: 삭제 기능 테스트) 애초에 한 곳도 등록하지 않은
    #    채(흔한 첫 배포 실수: init 직후 바로 go-live부터 돌리는 순서) go-live를
    #    돌리면 — 낙찰받아 공사를 진행할 업체가 하나도 없어 사건을 아무도
    #    처리 못 하는, n_insurer==0(사건 등록 불가)·n_super==0(관리 기능
    #    불가)과 정확히 같은 급의 운영 정지 상태인데도 화면은 초록만
    #    보여준다. 삭제 로직·판정 기준은 그대로 두고(정책 변경 아님) 개수만
    #    보고 형제와 같은 모양(if 0: warn 아니면 ok)으로 맞춘다. 복구 명령은
    #    CLI가 없으므로 콘솔 화면 이름을 안내한다.
    if n_partner == 0:
        warn("협력업체가 하나도 남지 않았습니다 — 낙찰받아 공사를 진행할 업체가 없습니다. 반드시 등록하세요:")
        print("      콘솔 로그인 → [업체 등록·관리] → + 업체 등록")
    else:
        ok(f"협력업체 {n_partner}개사 유지됨")
    if n_insurer == 0:
        warn("발주처(보험사) 계정이 하나도 남지 않았습니다 — 사건을 등록할 곳이 없습니다. 반드시 만드세요:")
        print("      python manage.py create-insurer <기관명> <로그인ID>")
    else:
        ok(f"발주처 {n_insurer}개사 유지됨")
    if n_admin == 0:
        warn("관리자 계정이 하나도 없습니다. 반드시 만드세요:")
        print("      python manage.py create-admin <아이디> --role 최고관리자")
        print("      ※ 'admin' 이 아닌 실제 담당자 아이디를 쓰세요.")
    elif n_super == 0:
        #  ⚠⚠ [라운드629] cmd_check()(317-337행)와 같은 기준 — 관리자는 있지만
        #    전부 중간·하위관리자뿐이면 계정관리·정산이체·요율설정을 아무도 못 켠다.
        warn(f"관리자 계정은 {n_admin}개 있지만 최고관리자가 0명입니다 — "
             f"계정관리·정산이체·요율설정을 아무도 할 수 없습니다. 반드시 만드세요:")
        print("      python manage.py create-admin <아이디> --role 최고관리자")
    else:
        ok(f"관리자 계정 {n_admin}개(최고관리자 {n_super}명 포함) 유지")
    print()
    print("  다음 단계:  python manage.py check")'''

    #  ⚠⚠ [라운드629/630] NEW_BLOCK_2는 629가 admins else 분기에 보탠 elif(n_super==0)와
    #    630이 그 앞(협력업체 줄)에 보탠 if/else까지 포함해야 현재 manage.py와
    #    문자 단위로 일치한다 — OLD_BLOCK_2(627 이전 코드, insurers 자체가
    #    없던 시절)는 629·630과 무관해 그대로 둔다.
    assert NEW_BLOCK_1 in _src, "R627_BROKEN: NEW_BLOCK_1을 못 찾음(manage.py 변경?)"
    assert NEW_BLOCK_2 in _src, "R627_BROKEN: NEW_BLOCK_2를 못 찾음(manage.py 변경?)"
    _src = _src.replace(NEW_BLOCK_1, OLD_BLOCK_1).replace(NEW_BLOCK_2, OLD_BLOCK_2)

#  manage.py 를 "python manage.py <args>" 로 직접 돌린 것과 똑같이 동작시킨다 —
#  sys.argv[1:] 는 이 launcher 자신이 받은 인자 그대로, __name__="__main__" 이라
#  파일 맨 끝의 `if __name__ == "__main__": sys.exit(main())` 이 정상 발동한다.
_ns = {"__name__": "__main__", "__file__": MANAGE_PATH}
exec(compile(_src, MANAGE_PATH, "exec"), _ns)  # noqa: S102 -- 실소스 그대로(디스크 미기록), R627_BROKEN 일 때만 인메모리 치환
