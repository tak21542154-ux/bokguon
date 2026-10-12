# -*- coding: utf-8 -*-
"""스캔 261라운드 회귀 — crypto_util.py 키 형식 오류 완전침묵 결함 1건
   (암호화 유틸 감사 Agent 조사로 발견, 독립 재검증 후 수정).

  _load_key() 는 BOKGUON_ENC_KEY 가 "아예 없을 때"만 신호를 낸다(운영은
  예외, 개발은 경고). 값은 있는데 base64 디코드 후 16/24/32바이트가 아닌
  경우(키 로테이션 중 따옴표·개행·부분복사로 형식이 깨진 경우 등)는 완전히
  침묵한 채 SHA256 파생키로 넘어갔다 — 형제(83행, 라운드120)는 복호화
  "실패"는 이미 로그를 남기는데, 그 근본 원인(키 형식)에는 신호가 없어
  증상만 한참 뒤(값을 "제대로" 고친 순간 그 사이 저장된 값이 전부 안
  열릴 때)에야 사후로 드러났다.

  ⚠ 이 수정은 로그 한 줄만 추가한다 — SHA256 파생 자체(실제 쓰이는 키)는
    그대로다. 암호화 포맷·기존 데이터 하위호환에 영향 없음(의도적으로
    최소화 — 알고리즘/포맷 변경은 재암호화 마이그레이션이 걸린 별개 판단).

      python test_scan_round261_fixes.py
"""
import base64
import io
import logging
import os
import sys
import unittest.mock as mock

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


CRYPTO_SRC = read("crypto_util.py")

print("=" * 72)
print("  스캔 261라운드 회귀 — 암호화 키 형식오류 완전침묵 차단")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = CRYPTO_SRC.index("def _load_key(")
i1 = CRYPTO_SRC.index("\n\n\ndef ", i0)
load_key_body = CRYPTO_SRC[i0:i1]
chk('_log.warning(' in load_key_body,
    "★★★★ 키 형식이 틀렸을 때(len(key) not in (16,24,32)) 경고 로그가 생겼다")
# ⚠ 경고가 진짜 그 분기 안에 있는지 — if 문 바로 다음 줄부터 sha256 파생 전까지인지 확인
_branch = load_key_body[load_key_body.index("if len(key) not in (16, 24, 32):"):
                         load_key_body.index("key = hashlib.sha256(key).digest()")]
chk("_log.warning(" in _branch,
    "STEP 경고가 정확히 그 분기(길이 불일치) 안에서 발생한다(다른 분기 아님)")
chk("env_name" in _branch and "len(key)" in _branch,
    "STEP 어떤 환경변수·몇 바이트였는지는 남기되 키 원문 자체는 안 남긴다")

# ============================================================
print("\n[2] 실행 — 실제로 경고가 뜨는지/안 뜨는지, 동작은 그대로인지")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import importlib
    import crypto_util as CU
    importlib.reload(CU)  # 이전 테스트가 바꿔 둔 env 캐시 영향 없이 순수하게

    _env_backup = dict(os.environ)
    try:
        #  ── (a) 형식이 틀린 키 — 경고가 떠야 한다 ──
        #  ⚠ "!" 는 base64 URL-safe 알파벳에 없어 디코드가 확실히 실패하고,
        #    raw.encode() 폴백 결과(7바이트)도 16/24/32 어디에도 안 걸린다 —
        #    임의 문자열이 "우연히" 유효한 24바이트로 디코드될 수 있음을
        #    실제로 겪은 뒤(처음 골랐던 문자열이 그랬다) 확정한 값이다.
        os.environ["BOKGUON_ENC_KEY"] = "bad!key"
        with mock.patch.object(CU, "_log") as m_log:
            token = CU.encrypt("R261-테스트평문")
            chk(m_log.warning.called,
                "★★★★★ 키 형식이 틀리면 경고 로그가 실제로 발생한다"
                "(고치기 전엔 완전 침묵했다)")
            if m_log.warning.called:
                _args = str(m_log.warning.call_args)
                chk("bad!key" not in _args,
                    "★★★★★ 경고 메시지에 키 원문은 담기지 않는다", _args[:200])

        #  ── (b) 그래도 암호화·복호화 자체는 여전히 동작한다(포맷 불변 확인) ──
        back = CU.decrypt(token)
        chk(back == "R261-테스트평문",
            "STEP 경고를 추가해도 암-복호화 왕복 자체는 그대로 성공한다"
            "(포맷·파생키 변경 없음)", back)

        #  ── (c) 대조군 — 형식이 올바른 32바이트 키는 경고가 안 뜬다(과잉경보 아님) ──
        good_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        os.environ["BOKGUON_ENC_KEY"] = good_key
        with mock.patch.object(CU, "_log") as m_log2:
            token2 = CU.encrypt("R261-정상키테스트")
            chk(not m_log2.warning.called,
                "STEP 대조군 — 32바이트 정상 키는 경고가 뜨지 않는다(과잉경보 아님)")
        chk(CU.decrypt(token2) == "R261-정상키테스트",
            "STEP 정상 키 경로의 왕복도 여전히 정상 동작한다")
    finally:
        os.environ.clear()
        os.environ.update(_env_backup)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드261 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
