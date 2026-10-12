# -*- coding: utf-8 -*-
"""운영용 WSGI 진입점.

Flask 개발서버(app.run)는 단일 스레드·디버그 노출·성능 문제로 운영에 사용 금지.
아래 중 하나로 구동한다.

  [Linux]   gunicorn -c gunicorn_conf.py wsgi:application
  [Windows] python serve_waitress.py
"""
import os

# .env 로드 (python-dotenv 있으면 사용, 없으면 수동 파싱)
from envload import load_dotenv as _load_dotenv
_load_dotenv()

from app import app as application  # noqa: E402

if __name__ == "__main__":
    print("이 파일은 WSGI 서버로 실행하세요.")
    print("  Linux  : gunicorn -c gunicorn_conf.py wsgi:application")
    print("  Windows: python serve_waitress.py")
