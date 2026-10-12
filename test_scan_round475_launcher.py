# -*- coding: utf-8 -*-
"""라운드475 회귀(test_scan_round475_fixes.py) 전용 launcher —
`python manage.py <args...>` 를 그대로 흉내 내되, manage.py 실제 파일은
디스크에서 전혀 건드리지 않는다.

⚠⚠ [라운드626] 이전 버전은 메인 테스트 프로세스가 manage.py 를 통째로
디스크에 옛(취약) 코드로 다시 썼다가 finally 에서 원본으로 복원했다
(라운드625가 477·509에서 확립한 "서브프로세스 안에서 인메모리로만
되돌린다" 방식을 manage.py 는 `python manage.py <cmd>` 서브프로세스
호출이라 그대로 못 써 — 이 launcher 가 그 대체 진입점이다).

R475_BROKEN=1 이면 manage.py 소스를 읽어(디스크는 그대로) cmd_go_live()·
cmd_check() 두 곳만 옛(취약) 코드로 메모리에서 치환한 뒤 그 텍스트를
exec 한다 — 실제 manage.py 파일은 이 프로세스에서도 전혀 안 쓴다.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGE_PATH = os.path.join(HERE, "manage.py")
_src = io.open(MANAGE_PATH, encoding="utf-8").read()

if os.environ.get("R475_BROKEN") == "1":
    OLD_BLOCK_1 = '''                if table == "admins":
                    cur = conn.execute(f"DELETE FROM {table} WHERE {col}=?", (nm,))
                else:'''

    NEW_BLOCK_1 = '''                if table == "admins":
                    #  ⚠⚠ [라운드475] api_admin_delete()(app.py)는 마지막
                    #    최고관리자는 지우지 못하게 막는데, 이 대량정리 경로엔
                    #    그 가드가 없었다 — go-live 전에 새 관리자를 만들면서
                    #    --role 을 안 붙이면(기본값 중간관리자) 'admin' 이
                    #    유일한 최고관리자인 채로 그대로 삭제돼, 콘솔에서
                    #    최고관리자를 다시 만들 방법이 없는 영구 락아웃이
                    #    된다(실측 재현 — 서버 쉘로 create-admin 을 직접
                    #    돌리는 것 외엔 복구 수단이 없었다). 지우면 최고관리자가
                    #    0명이 될 경우에만 건너뛰고 경고한다 — 다른 데모정리는
                    #    계속 진행하고, go-live 는 재실행 가능하므로 실제
                    #    최고관리자를 만든 뒤 다시 돌리면 그때 지워진다.
                    _row = conn.execute(
                        f"SELECT role FROM {table} WHERE {col}=?", (nm,)).fetchone()
                    if _row and _row["role"] == "최고관리자":
                        _n_super = conn.execute(
                            "SELECT COUNT(*) n FROM admins WHERE role='최고관리자'"
                        ).fetchone()["n"]
                        if _n_super <= 1:
                            warn(f"'{nm}' 계정이 마지막 최고관리자라 지우지 않았습니다. "
                                 f"실제 최고관리자 계정을 만든 뒤 go-live를 다시 실행하세요"
                                 f"(python manage.py create-admin <아이디> --role 최고관리자).")
                            continue
                    cur = conn.execute(f"DELETE FROM {table} WHERE {col}=?", (nm,))
                else:'''

    OLD_BLOCK_2 = '''        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]
        if n_admin == 0:
            bad("관리자 계정이 0개입니다. 콘솔에 로그인할 수 없습니다.")
            print("        → python manage.py create-admin <아이디> --name <이름> --role 최고관리자")
            print("        ※ 아이디로 admin·staff 를 쓰지 마세요. go-live 가 다시 지웁니다.")
            fails += 1
        else:
            ok(f"관리자 계정 {n_admin}개")'''

    NEW_BLOCK_2 = '''        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]
        if n_admin == 0:
            bad("관리자 계정이 0개입니다. 콘솔에 로그인할 수 없습니다.")
            print("        → python manage.py create-admin <아이디> --name <이름> --role 최고관리자")
            print("        ※ 아이디로 admin·staff 를 쓰지 마세요. go-live 가 다시 지웁니다.")
            fails += 1
        else:
            #  ⚠⚠ [라운드475] 위 검사는 "로그인 자체가 안 되는" 최악만 잡는다 —
            #    관리자가 1명 이상이어도 전부 중간·하위관리자뿐이면 계정관리·
            #    정산이체·요율설정 등 최고관리자 전용 기능은 아무도 못 켠다
            #    (로그인은 되니 위 검사만 보면 '정상'으로 보인다). 실측(스크래치
            #    DB): create-admin 을 --role 없이 돌린 뒤 go-live 를 실행하면
            #    정확히 이 상태(관리자 1명·최고관리자 0명)가 됐었다.
            n_super = conn.execute(
                "SELECT COUNT(*) n FROM admins WHERE role='최고관리자'").fetchone()["n"]
            if n_super == 0:
                bad(f"관리자 계정은 {n_admin}개 있지만 최고관리자가 0명입니다 — "
                    f"계정관리·정산이체·요율설정을 아무도 할 수 없습니다.")
                print("        → python manage.py create-admin <아이디> --name <이름> --role 최고관리자")
                fails += 1
            else:
                ok(f"관리자 계정 {n_admin}개(최고관리자 {n_super}명 포함)")'''

    assert NEW_BLOCK_1 in _src, "R475_BROKEN: NEW_BLOCK_1을 못 찾음(manage.py 변경?)"
    assert NEW_BLOCK_2 in _src, "R475_BROKEN: NEW_BLOCK_2를 못 찾음(manage.py 변경?)"
    _src = _src.replace(NEW_BLOCK_1, OLD_BLOCK_1).replace(NEW_BLOCK_2, OLD_BLOCK_2)

#  manage.py 를 "python manage.py <args>" 로 직접 돌린 것과 똑같이 동작시킨다 —
#  sys.argv[1:] 는 이 launcher 자신이 받은 인자 그대로(런처는 자기 이름만
#  다르지 CLI 인자 파싱은 전혀 손대지 않는다), __name__="__main__" 이라
#  파일 맨 끝의 `if __name__ == "__main__": sys.exit(main())` 이 정상 발동한다.
_ns = {"__name__": "__main__", "__file__": MANAGE_PATH}
exec(compile(_src, MANAGE_PATH, "exec"), _ns)  # noqa: S102 -- 실소스 그대로(디스크 미기록), R475_BROKEN 일 때만 인메모리 치환
