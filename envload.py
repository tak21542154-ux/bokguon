# -*- coding: utf-8 -*-
"""`.env` 로더 — 모든 진입점(app.py / wsgi.py / serve_waitress.py / manage.py)이 공유한다.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

한 곳에서만 파싱하도록 모아 둔 이유
  진입점마다 파서를 따로 두면, 하나가 BOM 처리를 빼먹거나 서로 달라져서
  "app.py 로는 되는데 manage.py 로는 안 된다" 같은 미묘한 사고가 난다.
  특히 manage.py 가 .env 를 안 읽으면 BOKGUON_UPLOAD_DIR 같은 경로 설정이
  기본값으로 잡혀, go-live 의 사진 삭제가 엉뚱한 디렉터리를 지우고 조용히 실패한다.
"""
import os
import re

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
#  공백(또는 탭) 뒤에 오는 # 부터 줄 끝까지 — 값 뒤에 붙는 인라인 주석.
#  '#' 바로 앞에 공백이 없으면(KEY=abc#1) 주석이 아니라 값의 일부로 본다 —
#  python-dotenv 의 관례와 맞춘다.
_INLINE_COMMENT = re.compile(r"\s+#.*$")


def load_dotenv(path=None):
    """`.env` 를 os.environ 에 로드한다(이미 있는 값은 덮지 않음)."""
    path = path or _ENV_PATH
    if not os.path.exists(path):
        return
    # python-dotenv 가 있으면 그것을 쓴다(주석·따옴표 처리가 더 견고)
    try:
        from dotenv import load_dotenv as _ld
        #  ⚠⚠ [라운드305] python-dotenv 의 기본 encoding 은 "utf-8"이라 BOM 을
        #    안 벗긴다(아래 대체 파서가 이미 utf-8-sig 로 막아 둔 바로 그 사고 —
        #    Windows 메모장·PowerShell 이 만든 .env 의 BOM이 첫 줄 키에 그대로
        #    붙어 "﻿BOKGUON_ENV" 라는 다른 이름이 된다). requirements.txt 가
        #    python-dotenv 를 고정 설치하므로 이 분기가 항상 실행되는 살아있는
        #    경로인데, 정작 이 분기만 그 방어가 빠져 있었다 — 아래 대체 파서는
        #    이 분기가 예외를 던질 때만 도는 죽은 코드라 실제로는 아무도 안 막고
        #    있었다(실측: BOM 붙은 .env 로 첫 줄 키가 os.environ 에 전혀 안 잡힘).
        _ld(path, override=False, encoding="utf-8-sig")
        return
    except ImportError:
        pass
    # ⚠ utf-8-sig — Windows 메모장·PowerShell 로 만든 .env 의 BOM 때문에
    #   첫 줄 키가 "﻿BOKGUON_ENV" 가 되어 무시되는 사고를 막는다.
    #   하필 첫 줄이 BOKGUON_ENV=prod 라, 운영 설정을 넣고도 dev 로 도는 결과가 된다.
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip().lstrip("﻿")
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            #  ⚠⚠ [라운드286] 이 대체 파서(python-dotenv 없을 때만 도는 경로)는
            #    한 줄 전체 주석(위 35행)만 걸렀지 값 뒤에 붙는 인라인 주석
            #    (`KEY=값  # 설명`)은 안 걸러 그 문구까지 값에 그대로 붙었다
            #    (실측: `SECRET=abc123  # rotate quarterly` → 저장된 값이
            #    `'abc123  # rotate quarterly'`) — 아무 예외·로그 없이 조용히
            #    비밀값이 오염된다. 오늘은 python-dotenv 가 requirements.txt 에
            #    고정 설치돼 있어 이 경로 자체가 항상 건너뛰어지지만(죽은
            #    코드), venv 손상 등으로 이 경로를 타는 순간 바로 발현된다.
            #    따옴표로 감싼 값은 그 안의 #을 주석으로 보지 않는다(정식
            #    dotenv 관례와 맞춤).
            if v[:1] in ("'", '"'):
                q = v[0]
                end = v.find(q, 1)
                v = v[1:end] if end != -1 else v[1:]
            else:
                v = _INLINE_COMMENT.sub("", v).strip()
            os.environ.setdefault(k.strip(), v)
