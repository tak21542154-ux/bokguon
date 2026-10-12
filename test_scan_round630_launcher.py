# -*- coding: utf-8 -*-
"""라운드630 회귀(test_scan_round630_fixes.py) 전용 launcher —
`python manage.py <args...>` 를 그대로 흉내 내되, manage.py 실제 파일은
디스크에서 전혀 건드리지 않는다.

round475/627/629가 세운 launcher 패턴(test_scan_round629_launcher.py) 그대로 —
manage.py 는 `python manage.py <cmd>` 서브프로세스 호출이라 477·509처럼
같은 프로세스 안에서 view_functions 를 스왑할 대상(Flask 라우트)이 없다.

R630_BROKEN=1 이면 manage.py 소스를 읽어(디스크는 그대로) cmd_go_live()의
사후요약에서 "협력업체 0개사"도 경고 없이 무조건 ok()로 찍던 옛(630 이전)
코드로 이 블록 하나만 메모리에서 치환한 뒤 그 텍스트를 exec 한다 — 실제
manage.py 파일은 이 프로세스에서도 전혀 안 쓴다.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGE_PATH = os.path.join(HERE, "manage.py")
_src = io.open(MANAGE_PATH, encoding="utf-8").read()

if os.environ.get("R630_BROKEN") == "1":
    NEW_BLOCK = '''    print("─" * 62)
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
    if n_insurer == 0:'''

    OLD_BLOCK = '''    print("─" * 62)
    ok(f"협력업체 {n_partner}개사 유지됨")
    if n_insurer == 0:'''

    assert NEW_BLOCK in _src, "R630_BROKEN: NEW_BLOCK을 못 찾음(manage.py 변경?)"
    _src = _src.replace(NEW_BLOCK, OLD_BLOCK)

#  manage.py 를 "python manage.py <args>" 로 직접 돌린 것과 똑같이 동작시킨다 —
#  sys.argv[1:] 는 이 launcher 자신이 받은 인자 그대로, __name__="__main__" 이라
#  파일 맨 끝의 `if __name__ == "__main__": sys.exit(main())` 이 정상 발동한다.
_ns = {"__name__": "__main__", "__file__": MANAGE_PATH}
exec(compile(_src, MANAGE_PATH, "exec"), _ns)  # noqa: S102 -- 실소스 그대로(디스크 미기록), R630_BROKEN 일 때만 인메모리 치환
