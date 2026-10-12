# -*- coding: utf-8 -*-
"""라운드629 회귀(test_scan_round629_fixes.py) 전용 launcher —
`python manage.py <args...>` 를 그대로 흉내 내되, manage.py 실제 파일은
디스크에서 전혀 건드리지 않는다.

round475/627이 세운 launcher 패턴(test_scan_round627_launcher.py) 그대로 —
manage.py 는 `python manage.py <cmd>` 서브프로세스 호출이라 477·509처럼
같은 프로세스 안에서 view_functions 를 스왑할 대상(Flask 라우트)이 없다.

R629_BROKEN=1 이면 manage.py 소스를 읽어(디스크는 그대로) cmd_go_live()의
n_super 계산 + 사후요약의 "관리자는 있지만 최고관리자 0명" 경고 두 곳만
옛(629 이전) 코드로 메모리에서 치환한 뒤 그 텍스트를 exec 한다 — 실제
manage.py 파일은 이 프로세스에서도 전혀 안 쓴다.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGE_PATH = os.path.join(HERE, "manage.py")
_src = io.open(MANAGE_PATH, encoding="utf-8").read()

if os.environ.get("R629_BROKEN") == "1":
    OLD_BLOCK_1 = '''        conn.commit()

        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]'''

    NEW_BLOCK_1 = '''        conn.commit()

        #  ⚠⚠ [라운드629] 바로 아래 n_admin과 같은 자리에 있는 진짜 형제 결함 — round475가
        #    이미 "관리자 1명 이상이어도 전부 중간·하위관리자뿐이면 계정관리·
        #    정산이체·요율설정을 아무도 못 켠다"며 cmd_check()(317-337행)에 n_super
        #    분기를 넣고, 위 ③단계 삭제 루프(2129-2137행)에도 "이 삭제 자체가
        #    마지막 최고관리자를 지우면 안 된다"는 가드를 넣었다 — 그런데 go-live가
        #    **자기 실행 직후 찍는 이 요약**만은 그 형제 취급을 못 받았다. ③단계
        #    가드는 go-live의 삭제가 최고관리자를 0명으로 만드는 것만 막을 뿐, go-live를
        #    돌리기 **전부터** 최고관리자가 0명이던 상태(예: create-admin을 --role
        #    없이 돌려 만든 계정 하나뿐이고 데모 admin/staff는 애초에 없거나 이미
        #    지워진 경우)는 그대로 통과시킨다 — 아래 요약은 n_admin>0 이면 무조건
        #    "관리자 계정 N개 유지"(정상)로 찍어, cmd_check()가 이미 "bad"로 잡는
        #    바로 그 상태를 go-live 자신의 화면에서는 초록으로 보여준다. 다음 줄의
        #    "python manage.py check"가 뒤늦게 잡아 주긴 하지만, round627이 insurers에
        #    적용한 것과 같은 원칙(형제 요약이 이미 아는 것을 이 요약도 알아야 한다)
        #    으로 여기도 맞춘다 — 삭제 로직·판정 기준은 전혀 안 바꾸고 개수만 센다.
        #    n_admin·n_partner·n_insurer 세 줄(round627이 이미 확정한 블록) **앞**에
        #    둔다 — 그 블록 안이나 뒤에 끼우면 round627 자신의 회귀테스트가 소스를
        #    원문 그대로(문자 단위) 대조하는 자리를 깨뜨린다(직접 재현·확인).
        n_super = conn.execute(
            "SELECT COUNT(*) n FROM admins WHERE role='최고관리자'").fetchone()["n"]
        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]'''

    OLD_BLOCK_2 = '''    if n_admin == 0:
        warn("관리자 계정이 하나도 없습니다. 반드시 만드세요:")
        print("      python manage.py create-admin <아이디> --role 최고관리자")
        print("      ※ 'admin' 이 아닌 실제 담당자 아이디를 쓰세요.")
    else:
        ok(f"관리자 계정 {n_admin}개 유지")
    print()
    print("  다음 단계:  python manage.py check")'''

    NEW_BLOCK_2 = '''    if n_admin == 0:
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

    assert NEW_BLOCK_1 in _src, "R629_BROKEN: NEW_BLOCK_1을 못 찾음(manage.py 변경?)"
    assert NEW_BLOCK_2 in _src, "R629_BROKEN: NEW_BLOCK_2를 못 찾음(manage.py 변경?)"
    _src = _src.replace(NEW_BLOCK_1, OLD_BLOCK_1).replace(NEW_BLOCK_2, OLD_BLOCK_2)

#  manage.py 를 "python manage.py <args>" 로 직접 돌린 것과 똑같이 동작시킨다 —
#  sys.argv[1:] 는 이 launcher 자신이 받은 인자 그대로, __name__="__main__" 이라
#  파일 맨 끝의 `if __name__ == "__main__": sys.exit(main())` 이 정상 발동한다.
_ns = {"__name__": "__main__", "__file__": MANAGE_PATH}
exec(compile(_src, MANAGE_PATH, "exec"), _ns)  # noqa: S102 -- 실소스 그대로(디스크 미기록), R629_BROKEN 일 때만 인메모리 치환
