# -*- coding: utf-8 -*-
"""Linux 운영 구동 (gunicorn).

실행: gunicorn -c gunicorn_conf.py wsgi:application
설치: pip install gunicorn
"""
import multiprocessing
import os

bind = os.environ.get("BOKGUON_BIND", "127.0.0.1:8771")   # nginx 뒤에 두므로 로컬 바인딩
workers = int(os.environ.get("BOKGUON_WORKERS", str(min(multiprocessing.cpu_count() * 2 + 1, 8))))
#  ⚠⚠ [라운드287] BOKGUON_THREADS 는 .env.example 에 이미 있고(23행) 형제
#    진입점 serve_waitress.py(23행)는 실제로 읽는데, 여기만 하드코딩 4라
#    운영자가 이 값을 올려도(BOKGUON_WORKERS 는 바로 옆이라 착각하기 쉽다)
#    gunicorn 은 조용히 그대로 4로 돈다 — 경고도 로그도 없다. 형제와 같은
#    변수를 읽도록 통일(기본값 4는 유지 — 이미 이 값으로 운영 중인 배포의
#    동작을 바꾸지 않는다).
threads = int(os.environ.get("BOKGUON_THREADS", "4"))
worker_class = "gthread"
timeout = 60
graceful_timeout = 30
keepalive = 5

# 로그
accesslog = os.environ.get("BOKGUON_ACCESS_LOG", "-")
errorlog = os.environ.get("BOKGUON_ERROR_LOG", "-")
loglevel = os.environ.get("BOKGUON_LOG_LEVEL", "info")
access_log_format = '%({X-Forwarded-For}i)s %(t)s "%(r)s" %(s)s %(b)s %(D)sus'

# [보안] 프록시 신뢰 — nginx만 허용
forwarded_allow_ips = os.environ.get("BOKGUON_FORWARDED_ALLOW", "127.0.0.1")
proc_name = "bokguon"

#  ⚠⚠ [라운드287] 아래 세 값은 gunicorn 23.0.0 자체 기본값과 완전히 동일하다
#    (실측: gunicorn/config.py 의 LimitRequestLine/Fields/FieldSize 클래스
#    default 가 각각 4094/100/8190) — 즉 "헤더 기반 DoS 완화"라는 원래 주석은
#    이 블록이 gunicorn 기본보다 더 강화된 값을 쓴다고 오해하게 만들지만
#    실제로는 아무것도 강화하지 않는다(있으나 없으나 동작이 같다). 그렇다고
#    지울 이유는 아니다 — **명시적으로 고정**해 두면 나중에 gunicorn 자체
#    기본값이 바뀌어도(버전업 등) 이 값들은 코드리뷰 없이 조용히 안 바뀐다.
#    값 자체를 기본보다 더 좁히는 것은 실제 트래픽(인증 쿠키·헤더 크기 등)을
#    보지 않고는 판단할 수 없는 보안정책 결정이라 이번 라운드 범위 밖이다.
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
