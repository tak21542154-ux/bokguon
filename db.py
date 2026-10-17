# -*- coding: utf-8 -*-
"""복구온 서비스 — SQLite 데이터 계층 (스키마 + 시드)."""
import io
import sys
import sqlite3
import os
import json
import hashlib
import hmac
import logging
import re
from datetime import datetime, timedelta, timezone

#  ⚠ 윈도 기본 콘솔은 cp949 라 '—'·'⚠' 같은 문자를 print 하면 UnicodeEncodeError 로
#    죽는다. "python db.py"(자체 점검 — 스키마 반영·건수 요약, 아래 __main__)로
#    단독 실행하면 이 파일은 app.py 처럼 repair_estimate.py 를 거쳐가지 않아
#    그 우연한 구제도 없다(실측). 형제 점검 도구(check_tx_paths.py 등)가 이미
#    쓰는 방어를 그대로 옮긴다(round519).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

_log = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
#  BOKGUON_DB_PATH 로 갈아끼울 수 있다 — 검증은 운영 DB 사본에서 돌린다.
#  (운영 기본값은 그대로. 환경변수를 안 주면 아무것도 달라지지 않는다)
DB_PATH = os.environ.get("BOKGUON_DB_PATH") or os.path.join(HERE, "bokguon.db")
SEED_JSON = os.path.join(HERE, "data", "partners_seed.json")

#  ★★ 검증 도구가 **운영 DB 를 가리킨 채로는 아예 못 돌게** 막는다.
#
#   실제로 일어난 일 — `test_dispatch.py` 를 BOKGUON_DB_PATH 없이 한 번 돌렸더니
#   기본 경로(= 운영 bokguon.db)로 붙었고, 그 실행이 중간에 예외로 죽어
#   테스트의 cleanup() 이 돌지 않았다. 운영에 검증 사건 10건·협력사 2곳·
#   배차 12·호출 208이 그대로 남았다.
#
#   ⚠ 배터리(run_all_tests.py)는 이미 입구에서 막고 있었다. 그런데 테스트 하나를
#     **직접** 돌리는 경로에는 아무 방어가 없었다 — 그 문이 36개다.
#     그래서 방어를 실행기가 아니라 **DB 를 여는 곳 한 곳**에 둔다.
#   ⚠ 자기 임시 DB 를 만들어 쓰는 검증(첫날 완주 등)은 통과해야 한다.
#     그래서 '테스트다' 만으로 막지 않고 **경로가 운영 파일일 때만** 막는다.
import sys                                    # noqa: E402 — 아래 가드에서만 쓴다
_ENTRY = os.path.basename(
    getattr(sys.modules.get("__main__"), "__file__", "") or "")
if (_ENTRY.startswith("test_")
        and os.path.abspath(DB_PATH) == os.path.abspath(os.path.join(HERE, "bokguon.db"))):
    raise SystemExit(
        f"\n[중단] {_ENTRY} 이 **운영 DB** 를 가리키고 있습니다.\n"
        f"        {DB_PATH}\n\n"
        "  검증은 사본에서만 돌립니다. 실행 전에 경로를 주세요:\n"
        "    set BOKGUON_DB_PATH=<검증용 DB 경로>      (cmd)\n"
        "    $env:BOKGUON_DB_PATH='<검증용 DB 경로>'   (PowerShell)\n"
        "    export BOKGUON_DB_PATH=<검증용 DB 경로>   (bash)\n\n"
        "  ⚠ 이 방어가 없던 시절, 검증 픽스처가 운영에 남은 적이 있습니다.\n")


# ── SQLite 운영 설정 ─────────────────────────────────────────
#  gunicorn 멀티워커/멀티스레드 뒤에서 SQLite를 쓰려면 두 가지가 반드시 필요하다.
#   1) WAL  — 읽기와 쓰기가 서로를 막지 않는다. (기본 rollback journal은 쓰기가 모든 읽기를 막는다)
#   2) busy_timeout — 잠금 충돌 시 즉시 "database is locked"로 죽지 않고 지정 시간만큼 재시도한다.
#  WAL 설정은 DB 파일에 영구 기록되지만, busy_timeout은 연결마다 다시 설정해야 한다.
BUSY_TIMEOUT_MS = int(os.environ.get("BOKGUON_SQLITE_BUSY_MS", "8000"))


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=BUSY_TIMEOUT_MS / 1000.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    # NORMAL: WAL에서는 전원 장애 시에도 DB 손상이 없고(커밋 유실 가능성만 존재) 쓰기 처리량이 크게 오른다.
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


# ── 시각 ─────────────────────────────────────────────────────
#  모든 타임스탬프는 **한국 표준시(KST)** 로 고정한다.
#  서버 로케일(UTC 인 클라우드 기본값 등)에 맡기면
#    · 하자보증 24개월 만료 판정이 9시간 어긋나고
#    · 정산 마감·입찰 마감이 하루 밀리거나 당겨진다.
#  DB 는 SQLite 라 타임존 타입이 없으므로, 저장 형식을 KST 문자열로 통일하고
#  SQL 안에서도 datetime('now','+9 hours') 로 같은 기준을 쓴다.
KST = timezone(timedelta(hours=9))


def now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


_SQL_NOW_OFFSET = re.compile(r"[+-]?\d+ (second|minute|hour|day)s?$")


def sql_now(offset=""):
    """SQL 안에서 쓸 현재시각 표현식. offset 예: '-10 minutes'

    사용 예:  f"... WHERE created_at > {DB.sql_now('-10 minutes')}"

    ⚠⚠ [라운드321] offset 을 이스케이프 없이 SQL 문자열에 그대로 이어붙인다
      — 지금 실제 호출부 2곳(app.py)은 전부 리터럴이거나 안전한 정수로만
      채운 값이라 안 뚫리지만(전수확인), 이 헬퍼 자체는 그걸 강제하지
      않았다. 나중에 사용자 입력에서 유도한 값(예: 관리자가 설정한 분·
      시간)이 그대로 들어오면 SQL 인젝션이 열린다 — docstring 이 이미
      보여주는 형식('-10 minutes' 류)만 통과시켜 원천 차단한다.
    """
    if offset and not _SQL_NOW_OFFSET.fullmatch(offset):
        raise ValueError(f"sql_now() offset 형식이 아닙니다: {offset!r}")
    parts = "'now','+9 hours'" + (f",'{offset}'" if offset else "")
    return f"datetime({parts})"


# ── 비밀번호 해싱 (PBKDF2-HMAC-SHA256, 솔트 + 고반복) ──
# 단순 SHA-256은 GPU 무차별 대입에 취약해 사용 금지.
# 표준 라이브러리만으로 구현해 추가 의존성 없이 안전성 확보.
PBKDF2_ITERATIONS = 600_000  # OWASP 2023+ 권장(PBKDF2-HMAC-SHA256)
_SALT_BYTES = 16


def hash_pw(pw, salt=None, iterations=PBKDF2_ITERATIONS):
    """salt$iterations$hash 형식으로 반환."""
    if salt is None:
        salt = os.urandom(_SALT_BYTES).hex()
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2${iterations}${salt}${dk.hex()}"


def verify_pw(pw, stored):
    """저장된 해시와 비교 (타이밍 공격 방어)."""
    if not stored:
        return False
    try:
        if stored.startswith("pbkdf2$"):
            _, iters, salt, _hash = stored.split("$", 3)
            calc = hash_pw(pw, salt=salt, iterations=int(iters))
            return hmac.compare_digest(calc, stored)
        # 레거시(sha256) 호환 — 로그인 성공 시 자동 재해싱 대상
        legacy = hashlib.sha256(("bokguon$" + pw).encode()).hexdigest()
        return hmac.compare_digest(legacy, stored)
    except Exception:
        return False


def is_legacy_hash(stored):
    return bool(stored) and not str(stored).startswith("pbkdf2$")


SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT,
    role TEXT DEFAULT '운영관리자',
    created_at TEXT
);

-- 보험사·공제조합 (포털 계정)
CREATE TABLE IF NOT EXISTS insurers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    org_type TEXT DEFAULT '손해보험사',
    login_id TEXT UNIQUE,
    password_hash TEXT,
    manager TEXT,
    dept TEXT,
    phone TEXT,
    email TEXT,
    fee_rate REAL DEFAULT 10,
    contract_status TEXT DEFAULT '계약중',
    status TEXT DEFAULT '활성',
    created_at TEXT
);

-- 하자·A/S (준공 후 하자 접수 → 재시공 배정 → 완료)
CREATE TABLE IF NOT EXISTS defects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    defect_no TEXT UNIQUE,
    case_id INTEGER,
    case_no TEXT,
    insurer TEXT,
    insurer_id INTEGER,
    partner_id INTEGER,
    partner_name TEXT,
    category TEXT,
    region TEXT,
    title TEXT NOT NULL,
    content TEXT,
    severity TEXT DEFAULT '보통',
    reporter TEXT,
    reporter_type TEXT DEFAULT '보험사',
    status TEXT DEFAULT '접수',
    assigned_at TEXT,
    due_date TEXT,
    resolved_at TEXT,
    resolution TEXT,
    cost_bearer TEXT DEFAULT '시행사',
    warranty_ok INTEGER DEFAULT 1,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_defect_case ON defects(case_id);
CREATE INDEX IF NOT EXISTS idx_defect_partner ON defects(partner_id);

-- ══════════════════════════════════════════════════════════════
--  하자 지적 사진 — **어느 사진의 무엇이 문제인가**
--
--  하자는 지금까지 제목·내용 '글자'뿐이었다. 그래서 시행사는
--  "방수 마감 불량" 같은 한 줄만 보고 현장에 다시 갔고, 어느 지점인지
--  전화로 되물어야 했다. 완료 사진은 이미 다 올라와 있는데도 그랬다.
--
--  보험사가 완료 사진을 보며 **사진 단위로 체크하고 사유를 적으면**,
--  그 사진과 사유가 그대로 시행사에게 간다. 재시공 전에 무엇을 고쳐야
--  하는지 알고 나가게 하는 것이 목적이다.
--
--  ⚠ 사진 자체는 photos 를 그대로 참조한다(복사하지 않는다).
--    같은 사진이 여러 하자에 지적될 수 있고, 하자가 닫혀도 근거는 남는다.
CREATE TABLE IF NOT EXISTS defect_photos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    defect_id INTEGER NOT NULL,
    photo_id  INTEGER NOT NULL,
    note      TEXT,              -- 이 사진의 어디가 왜 문제인가 (사진별 사유)
    marked_by TEXT,              -- 지적한 사람(보험사 담당자)
    created_at TEXT,
    UNIQUE(defect_id, photo_id)  -- 같은 사진을 한 하자에 두 번 지적하지 않는다
);
CREATE INDEX IF NOT EXISTS idx_defphoto_defect ON defect_photos(defect_id);

CREATE TABLE IF NOT EXISTS insurer_leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    org_type TEXT,
    name TEXT,
    title TEXT,
    phone TEXT,
    email TEXT,
    interest TEXT,
    message TEXT,
    status TEXT DEFAULT '신규',
    note TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS partner_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    biz_no TEXT,
    ceo TEXT,
    major TEXT,
    category TEXT,
    region TEXT,
    phone TEXT,
    email TEXT,
    has_license INTEGER DEFAULT 0,
    has_insurance INTEGER DEFAULT 0,
    equipment TEXT,
    message TEXT,
    status TEXT DEFAULT '신규',
    note TEXT,
    partner_id INTEGER,
    partner_type TEXT DEFAULT '시공사',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS partners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    partner_type TEXT DEFAULT '시공사',
    login_id TEXT UNIQUE,
    password_hash TEXT,
    biz_no TEXT,
    ceo TEXT,
    major TEXT,
    category TEXT,
    region TEXT,
    address TEXT,
    phone TEXT,
    email TEXT,
    website TEXT,
    license TEXT,
    -- [법령] 계좌번호는 암호화 저장 (개인정보 안전성 확보조치 기준 §7②, 고시 2025-9호)
    bank_name TEXT,
    bank_account_enc TEXT,
    bank_account_idx TEXT,
    bank_holder TEXT,
    rating REAL DEFAULT 0,
    jobs_done INTEGER DEFAULT 0,
    win_rate INTEGER DEFAULT 0,
    doc_status TEXT DEFAULT '정상',
    status TEXT DEFAULT '활성',
    source TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_no TEXT UNIQUE NOT NULL,
    insurer TEXT,
    insurer_id INTEGER,
    partner_id INTEGER,
    partner_name TEXT,
    completed_at TEXT,
    warranty_months INTEGER DEFAULT 24,
    category TEXT,
    region TEXT,
    address TEXT,
    urgent INTEGER DEFAULT 0,
    is_composite INTEGER DEFAULT 0,
    status TEXT DEFAULT '접수',
    est_price INTEGER DEFAULT 0,
    low_price INTEGER DEFAULT 0,
    manager TEXT DEFAULT '자동',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS work_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER,
    category TEXT,
    status TEXT DEFAULT '입찰중',
    awarded_partner_id INTEGER,
    low_price INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS auctions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER,
    lot_id INTEGER,
    deadline TEXT,
    status TEXT DEFAULT '진행',
    bid_count INTEGER DEFAULT 0,
    low_price INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS bids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    auction_id INTEGER,
    partner_id INTEGER,
    partner_name TEXT,
    amount INTEGER,
    days INTEGER,
    created_at TEXT
);

-- 입찰 인하 이력 — **역경매의 증거**
--  bids 는 재투찰 때 UPDATE 로 현재값만 남긴다(최저가 집계가 그 행을 읽으므로 그 구조는 유지).
--  그래서 '처음 얼마를 불렀고 몇 번에 걸쳐 얼마까지 내렸나'가 사라졌다. 그 결과
--   ① 절감 서사(보험사에 파는 핵심)를 데이터로 증명할 수 없고
--   ② 마감 직전 스나이핑·들러리·담합 패턴을 볼 수 없고
--   ③ 저가 경보가 걸렸던 그 금액조차 남지 않았다.
--  → 투찰이 일어날 때마다 **여기에 한 줄씩 쌓는다**(append-only, 절대 UPDATE 하지 않는다).
CREATE TABLE IF NOT EXISTS bid_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    auction_id    INTEGER,
    bid_id        INTEGER,
    case_id       INTEGER,
    partner_id    INTEGER,
    partner_name  TEXT,
    kind          TEXT,        -- 원경매 / 추가분 / 전체재경매
    seq           INTEGER,     -- 이 업체의 이 경매에서 몇 번째 투찰인가
    prev_amount   INTEGER,     -- 직전 제출가(최초면 NULL)
    amount        INTEGER,     -- 이번 제출가
    days          INTEGER,
    drop_pct      REAL,        -- 직전 대비 인하율(%)
    est_price     INTEGER,     -- 그때의 가견적(상한) — 경보 판정 재현용
    low_flag      INTEGER DEFAULT 0,   -- 저가 경보가 걸린 투찰인가
    ip            TEXT,        -- 동일 주체 다중 투찰 확인용
    portal_login  TEXT,
    created_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_bidev_auction ON bid_events(auction_id, partner_id, id);
CREATE INDEX IF NOT EXISTS idx_bidev_case ON bid_events(case_id, id);

-- 도급 적법성 판정 기록 — **형사 리스크의 소명 자료**
--  무등록 도급은 건산법상 형사벌(5년 이하)이다. compliance.gate() 가 그 방어선인데,
--  판정 결과가 어디에도 저장되지 않아 나중에 '이 건을 왜 직접 도급했는가'를 증명할
--  수단이 없었다. 게다가 합산 판단은 '최근 30일 같은 보험사·공종·지역'을 호출 시점에
--  다시 계산하므로, 사건이 늘면 **어제의 판정이 오늘 재현되지 않는다**.
--  → 확정 시점의 판정을 스냅샷으로 남긴다(판정표 버전까지 함께).
CREATE TABLE IF NOT EXISTS contract_gate_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         INTEGER,
    case_no         TEXT,
    code            TEXT,        -- 도급가능 / 중개필요 / 판정불가 …
    ok              INTEGER,
    category        TEXT,
    law             TEXT,        -- 어느 법 소관으로 봤는가
    amount          INTEGER,     -- 판정 대상 금액(확정가)
    related_amount  INTEGER,     -- 합산으로 잡힌 관련 건 금액
    related_case_nos TEXT,       -- 합산 대상 접수번호(그때 기준)
    limit_amount    INTEGER,     -- 그때 적용한 경미공사 한도
    reason          TEXT,
    rules_version   TEXT,        -- 어떤 판정표로 내린 판정인가
    route           TEXT,        -- 경매 / 1차합의
    decided_at      TEXT,
    decided_by      TEXT,
    override_reason TEXT         -- 판정을 넘겨 진행한 경우의 사유
);
CREATE INDEX IF NOT EXISTS idx_gatelog_case ON contract_gate_log(case_id, id);

-- 표준단가 개정 이력
--  price_src/price_date 는 '현재값의 출처'일 뿐 이력이 아니다. 단가가 바뀌면 과거 견적이
--  어느 단가로 계산됐는지 되짚을 수 없고, 캘리브레이션('그때 그 단가 대비 낙찰가')도 못 한다.
--  삭제도 물리 삭제였어서, 지우는 순간 그 단가로 낸 과거 견적의 근거가 함께 증발했다.
CREATE TABLE IF NOT EXISTS boq_price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    boq_id      INTEGER,
    major       TEXT,
    item        TEXT,
    spec        TEXT,
    unit        TEXT,
    old_price   INTEGER,
    new_price   INTEGER,
    price_src   TEXT,
    price_date  TEXT,
    action      TEXT,      -- 추가 / 수정 / 비활성 / 재활성(312라운드 — 비활성 항목이 seed 재실행으로 되살아난 경우)
    actor       TEXT,
    changed_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_boqhist_boq ON boq_price_history(boq_id, id);

CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER,
    case_no TEXT,
    insurer TEXT,
    partner_name TEXT,
    amount INTEGER,
    fee INTEGER,
    payout INTEGER,
    insurer_paid TEXT DEFAULT '대기',
    review_status TEXT DEFAULT '대기',
    transfer_status TEXT DEFAULT '대기',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT,
    audience TEXT DEFAULT '협력업체',
    pinned INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS standard_boq (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    major TEXT,
    item TEXT,
    spec TEXT,
    unit TEXT,
    ref_price INTEGER DEFAULT 0,
    created_at TEXT
);

-- 파손 정도 판정 이력 — 덮어쓰지 않고 쌓는다. 실패·미연동도 남긴다.
--  지금은 업로드할 때마다 cases 를 무조건 덮어써서, 두 번째 업로드가 실패하면
--  앞선 성공 판정이 실패 문구로 지워진다. 이력을 분리해 그 사고를 없앤다.
CREATE TABLE IF NOT EXISTS damage_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     INTEGER NOT NULL,
    photo_id    INTEGER,              -- 판정 대상 사진
    severity    TEXT,                 -- 경미/보통/중대. 실패·미연동이면 NULL
    summary     TEXT,                 -- 소견 원문 또는 실패 사유
    model       TEXT,                 -- 사용 모델명. 미연동이면 빈 문자열
    ok          INTEGER DEFAULT 0,    -- 1=판정 성공
    est_at_read INTEGER,              -- 판정 시점의 가견적(사후 변경 추적용)
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_damage_reads_case ON damage_reads(case_id, id DESC);

-- 가견적 점검 구간 — 운영팀이 직접 넣는 값. **시드 0행으로 출고한다.**
--  ⚠ 과거 낙찰 통계가 아니다. 낙찰 표본이 사실상 없으므로 통계를 만들지 않는다.
--    근거 없는 숫자를 화면에 띄우는 것이 이 기능에서 가장 나쁜 결과다.
CREATE TABLE IF NOT EXISTS est_check_band (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    major      TEXT NOT NULL,         -- 공종 (work_lots.category 와 같은 문자열)
    severity   TEXT NOT NULL,         -- 경미/보통/중대
    min_price  INTEGER,               -- NULL 이면 하한 없음
    max_price  INTEGER,               -- NULL 이면 상한 없음
    src        TEXT NOT NULL,         -- 이 값의 근거(입력 필수)
    updated_by TEXT,
    updated_at TEXT,
    UNIQUE(major, severity)
);

-- [B8] 낙찰 시점 스냅샷 — 나중에 실적 통계의 근거가 될 그릇.
--  ⚠ cases 를 조인해 통계를 내면 안 된다. 변경견적이 cases.award_amount 를
--    사후에 갈아치우므로, 같은 질의가 시점에 따라 다른 답을 낸다.
--    낙찰이 확정되는 그 순간의 값을 여기에 한 번만 적는다.
--  ⚠ 지금은 표본이 0에 가깝다. 이 표가 찰 때까지 화면에 평균·추천가를 내지 않는다.
CREATE TABLE IF NOT EXISTS est_outcome (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id      INTEGER NOT NULL UNIQUE,   -- 사건당 1행
    major        TEXT,                      -- 공종(work_lots 기준). 복합이면 NULL
    severity     TEXT,                      -- 낙찰 시점의 파손 정도
    severity_src TEXT,                      -- 담당자 확인 / 사진 판정 / 미정
    est_price    INTEGER,                   -- 가견적(입찰 상한)
    bid_count    INTEGER,                   -- 참여 업체 수
    low_price    INTEGER,                   -- 최저 입찰가
    award_amount INTEGER,                   -- 낙찰가(그 시점)
    final_amount INTEGER,                   -- 최종 확정액(변경견적 반영 후). 정산 확정 때 채운다
    partner_id   INTEGER,
    region       TEXT,
    awarded_at   TEXT,
    created_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_est_outcome_major ON est_outcome(major, severity);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ntype TEXT,
    channel TEXT,
    target TEXT,
    message TEXT,
    status TEXT DEFAULT '도달',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT,
    action TEXT,
    detail TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- 접속기록 (개인정보보호법 안전성 확보조치 기준 대응 + 트래픽 통계)
CREATE TABLE IF NOT EXISTS access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT,
    user_id TEXT,
    role TEXT,
    method TEXT,
    path TEXT,
    status INTEGER,
    user_agent TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_access_created ON access_log(created_at);
CREATE INDEX IF NOT EXISTS idx_access_user ON access_log(user_id);
--  ⚠ 접속통계는 **기간으로 자른 뒤 path·role 로 묶는다.** created_at 단일 인덱스로는
--    묶는 단계에서 임시 B-트리를 만들며 풀스캔이 된다(실측 36,474행/13일, 1인 개발).
--    실운영에서 협력사 수십 곳이 30초마다 폴링하면 이 표가 가장 빨리 커진다.
CREATE INDEX IF NOT EXISTS idx_access_stat_path ON access_log(created_at, path);
CREATE INDEX IF NOT EXISTS idx_access_stat_role ON access_log(created_at, role);

-- 로그인 시도 (계정 잠금·무차별 대입 방어)
CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    ip TEXT,
    success INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_login_user ON login_attempts(username, created_at);

-- 2단계 인증 복구 코드 (폰 분실 시 유일한 출구)
--  [원칙] 비밀번호와 같다 — 원문은 발급 순간에만 보여주고 DB 에는 해시만 남긴다.
--  쓴 코드는 지우지 않고 used_at 을 찍는다(언제 무엇이 쓰였는지 추적 가능해야 한다).
CREATE TABLE IF NOT EXISTS admin_recovery_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    code_hash TEXT NOT NULL,
    used_at TEXT,
    used_ip TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_recovery_admin ON admin_recovery_codes(admin_id, used_at);

-- 메모 (관리자용 추가 요청·중요 메모) — 사건·업체 등 대상에 붙인다
CREATE TABLE IF NOT EXISTS memos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT,          -- case / partner / insurer / application / lead
    target_id INTEGER,
    body TEXT NOT NULL,
    important INTEGER DEFAULT 0,
    author TEXT,
    done INTEGER DEFAULT 0,     -- 처리 완료 표시(중요 메모를 닫을 때)
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_memo_target ON memos(target_type, target_id);

-- 변경 견적(실사 후 증액) 재경매 이력
--   낙찰 업체가 실사 후 파손이 더 크면 추가 견적을 요청한다.
--   ① 추가분 경매 → 최저가를 원 낙찰 업체에 제시
--   ② 수락 → 합산가로 진행 / 거절 → 추가 사진 붙여 전체 재경매(다음 라운드)
--   ③ 유찰이면 최대 3라운드까지 재요청
CREATE TABLE IF NOT EXISTS change_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER,
    round INTEGER DEFAULT 1,           -- 1~3
    incumbent_partner_id INTEGER,      -- 1차 낙찰(원) 업체
    incumbent_amount INTEGER,          -- 원 낙찰가
    reason TEXT,                       -- 증액 사유(업체 제출)
    requested_amount INTEGER,          -- 업체가 제시한 추가 예상액(참고)
    add_low INTEGER,                   -- 추가분 경매 최저가
    add_partner_id INTEGER,            -- 추가분 최저가 업체
    combined_amount INTEGER,           -- 원+추가 합산가(제시액)
    status TEXT DEFAULT '실사요청',
    -- 상태: 실사요청 → 추가경매중 → 원업체제안 → 수락확정 / 거절 → 전체재경매중 → (낙찰확정|유찰)
    decided_at TEXT,
    note TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_co_case ON change_orders(case_id);

-- 웹훅 전송 이력 (보험사 전산으로 상태 통지) — 성공/실패를 남겨 재전송 판단
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    insurer_id INTEGER,
    event TEXT,               -- case.awarded / case.completed / settlement.paid ...
    case_no TEXT,
    payload TEXT,             -- 전송 본문(JSON)
    target_url TEXT,
    status TEXT DEFAULT '대기',   -- 성공 / 실패 / 대기 / 미설정 / 포기(재시도 상한 소진)
    http_code INTEGER,
    error TEXT,
    attempts INTEGER DEFAULT 0,
    created_at TEXT,
    delivered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_wh_insurer ON webhook_deliveries(insurer_id);

-- 포털 하위계정 (보험사·협력사 조직 내 등급 계정)
--  조직의 '원계정'은 insurers/partners 행 자체(=최고관리자)이고,
--  최고관리자가 만든 하위 담당자 계정은 여기 둔다. org_id 로 원계정에 묶여
--  로그인하면 세션의 insurer_id/partner_id 를 org_id 로 세팅 → 기존 테넌시 쿼리 그대로 동작.
CREATE TABLE IF NOT EXISTS portal_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_type TEXT NOT NULL,          -- insurer / partner
    org_id INTEGER NOT NULL,         -- insurers.id 또는 partners.id (원계정)
    login_id TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT,
    role TEXT DEFAULT '하위관리자',   -- 중간관리자 / 하위관리자 (최고관리자는 원계정뿐)
    status TEXT DEFAULT '활성',
    must_change_pw INTEGER DEFAULT 1,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_puser_org ON portal_users(org_type, org_id);

-- 마케팅 캠페인 (콜드메일·문자·알림톡) — 운영 알림과 **분리**한다.
--  운영 알림(공고 오픈·검수 요청·정산 통지)은 거래 관계에서 나오는 정보성 통지이고,
--  이 표는 **광고성 발송** 전용이다. 광고성은 정보통신망법 §50 에 따라
--  사전 수신동의·'(광고)' 표기·무료 수신거부 수단이 의무이므로 절대 섞지 않는다.
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    channel TEXT DEFAULT '메일',        -- 메일 / 문자 / 알림톡
    audience TEXT,                      -- 수신자 그룹 설명(사람이 읽는 문구)
    filter_json TEXT,                   -- 수신자 산출 조건(재현용)
    subject TEXT,
    body TEXT,
    status TEXT DEFAULT '작성중',        -- 작성중 / 발송대기 / 발송완료 / 취소
    total_count INTEGER DEFAULT 0,
    sent_count INTEGER DEFAULT 0,
    skipped_optout INTEGER DEFAULT 0,   -- 수신거부로 제외한 수
    skipped_nocontact INTEGER DEFAULT 0,-- 연락처 없어 제외한 수
    created_by TEXT,
    created_at TEXT,
    queued_at TEXT
);

-- 캠페인 수신자 스냅샷 — '누구에게 보내기로 했는지'를 발송 시점 기준으로 고정한다.
--  나중에 업체 연락처가 바뀌어도 발송 이력은 그대로 남아야 분쟁 때 소명이 된다.
CREATE TABLE IF NOT EXISTS campaign_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    partner_id INTEGER,
    name TEXT,
    contact TEXT,                       -- 발송 시점의 메일주소 또는 번호
    status TEXT DEFAULT '대기',          -- 대기 / 발송 / 실패 / 제외
    reason TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ctgt_campaign ON campaign_targets(campaign_id);

-- AI 사진 판정 대 사람 확정 (B3) — 재학습·정확도 추적의 근거 데이터
--  예전에는 불일치를 activity_log 의 자유 텍스트로만 남겨서 집계도 재학습도 불가능했다.
--  구조화해 쌓아야 '신뢰도 임계값이 적정한가'를 숫자로 되짚을 수 있다.
CREATE TABLE IF NOT EXISTS ai_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id INTEGER NOT NULL,
    case_id INTEGER,
    ai_kind TEXT,               -- AI 가 제안한 분류
    ai_confidence INTEGER DEFAULT 0,
    ai_model TEXT,
    human_kind TEXT,            -- 사람이 최종 확정한 분류
    agreed INTEGER DEFAULT 0,   -- 1=일치, 0=정정됨
    route TEXT,                 -- 자동승인 / 사람검수
    reviewer TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_airev_photo ON ai_reviews(photo_id);
CREATE INDEX IF NOT EXISTS idx_airev_agreed ON ai_reviews(agreed);

-- 잡 클레임(리스) — 스케줄러가 없는 환경에서 여러 워커 중 **한 명만** 마감 점검을 돌리게 한다.
--  ⚠ settings 에 두지 않는다. 설정 화면이 settings 전 키를 덤프·수정하므로
--    운영자가 바꿀 값과 내부 동작값이 섞이면 기능이 조용히 멈춘다.
CREATE TABLE IF NOT EXISTS job_locks (
    name        TEXT PRIMARY KEY,
    lease_until TEXT,          -- 이 시각까지 다른 워커 진입 금지 (KST)
    last_run_at TEXT,          -- 마지막 성공 시각 = 생존 신호
    last_note   TEXT
);

-- ══════════════════════════════════════════════════════════════
--  현장 출동 수배 (사진 없는 접수 건)
--
--  왜 필요한가 — 사고 접수의 상당수가 **사진 없이** 들어온다.
--  사진이 없으면 파손 규모를 알 수 없어 경매를 열 수 없다(입찰 상한을 못 정한다).
--  그래서 현장 인근 업체들에게 **동시에** 알리고, 30분 내 출동 가능한 곳을
--  **선착순으로 한 곳만** 잡아 현장 사진과 실견적을 받아온다.
--
--  ⚠ 선착순은 동시성 문제다. 두 업체가 같은 순간 수락하면 둘 다 출동해 헛걸음이 생긴다.
--    그래서 claim 은 BEGIN IMMEDIATE + 조건부 UPDATE(rowcount) 로만 처리한다.
-- ══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS dispatches (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id        INTEGER NOT NULL,
    round          INTEGER DEFAULT 1,     -- 재수배 회차
    status         TEXT DEFAULT '모집중',  -- 모집중 / 수배됨 / 도착 / 실패 / 취소
    claimed_partner_id INTEGER,           -- 선착순으로 잡은 업체(한 곳만)
    claimed_name   TEXT,
    claimed_at     TEXT,
    due_at         TEXT,                  -- 도착 기한 = 수락 + 제한시간(기본 30분)
    arrived_at     TEXT,
    photo_count    INTEGER DEFAULT 0,     -- 출동 업체가 올린 현장 사진 수
    field_estimate INTEGER DEFAULT 0,     -- 출동 업체의 실견적(참고용)
    fail_reason    TEXT,
    created_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_dispatch_case ON dispatches(case_id);
CREATE INDEX IF NOT EXISTS idx_dispatch_status ON dispatches(status);
CREATE INDEX IF NOT EXISTS idx_dispatch_due ON dispatches(status, due_at);

-- 수배 알림을 받은 업체와 응답 — 누구에게 알렸고 누가 언제 반응했는지 남긴다.
--  (같은 업체를 같은 회차에 두 번 부르지 않도록 UNIQUE)
CREATE TABLE IF NOT EXISTS dispatch_calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dispatch_id  INTEGER NOT NULL,
    partner_id   INTEGER NOT NULL,
    partner_name TEXT,
    notified_at  TEXT,
    responded_at TEXT,
    response     TEXT,                    -- 수락 / 거절 / 무응답 / 마감
    created_at   TEXT,
    UNIQUE(dispatch_id, partner_id)
);
CREATE INDEX IF NOT EXISTS idx_dcall_dispatch ON dispatch_calls(dispatch_id);
CREATE INDEX IF NOT EXISTS idx_dcall_partner ON dispatch_calls(partner_id);

-- 1차 합의 기록 — 출동 업체의 실견적을 놓고 보험사 보상 담당자와 맞춰보는 단계.
--  ⚠ 합의가 되면 경매 없이 그 업체가 시공한다. 그래서 **누가 무엇을 근거로
--    얼마에 합의했는지**가 남아야 한다(사후 소명·분쟁 대비).
--  ⚠ 복구온은 손해사정을 하지 않는다. 여기서 정하는 것은 '시공 도급 금액'이며
--    보험금 지급액 확정은 보험사 몫이다.
CREATE TABLE IF NOT EXISTS field_agreements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id       INTEGER NOT NULL,
    dispatch_id   INTEGER,
    partner_id    INTEGER,
    partner_name  TEXT,
    field_amount  INTEGER DEFAULT 0,      -- 출동 업체가 낸 실견적
    engine_low    INTEGER DEFAULT 0,      -- 표준단가 엔진의 개산 구간(참고)
    engine_high   INTEGER DEFAULT 0,
    proposed      INTEGER DEFAULT 0,      -- 우리가 보험사에 제시한 금액
    agreed_amount INTEGER DEFAULT 0,      -- 최종 합의 금액
    status        TEXT DEFAULT '검토중',   -- 검토중 / 합의 / 결렬
    our_staff     TEXT,                   -- 복구온 담당(전문가)
    insurer_staff TEXT,                   -- 보험사 보상 담당
    note          TEXT,
    decided_at    TEXT,
    created_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_fagree_case ON field_agreements(case_id);

-- ══════════════════════════════════════════════════════════════
--  일정 달력 — 수동 등록분
--
--  자동 일정(입찰 마감·출동 기한·시공 완료·하자보증 만료)은 원본 테이블에서
--  그때그때 읽는다(복사해 두면 원본이 바뀔 때 달력이 거짓말을 한다).
--  이 테이블은 회의·현장방문처럼 데이터에 없는 일정만 담는다.
-- ══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS schedule_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    memo       TEXT,
    event_date TEXT NOT NULL,          -- YYYY-MM-DD
    event_time TEXT,                   -- HH:MM (없으면 종일)
    case_id    INTEGER,                -- 사건에 붙는 일정이면 연결
    created_by TEXT,
    created_at TEXT,
    is_demo    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sched_date ON schedule_events(event_date);

-- ══════════════════════════════════════════════════════════════
--  해피콜 — 복구 완료 후 피해자 만족도 (머큐리 업무절차의 마지막 단계)
--
--  왜 필요한가 — 시공 품질의 최종 판정자는 검수자가 아니라 피해자다.
--  점수가 쌓이면 업체 평점의 근거가 되고, 낮은 점수는 재시공·관리 대상 신호가 된다.
--  ⚠ 사건당 1회(UNIQUE) — 여러 번 걸어 좋은 점수만 남기는 것을 막는다.
-- ══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS happy_calls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id    INTEGER NOT NULL UNIQUE,
    partner_id INTEGER,
    score      INTEGER NOT NULL,       -- 1~5
    feedback   TEXT,
    method     TEXT DEFAULT '전화',     -- 전화 / 문자 / 방문
    called_by  TEXT,
    created_at TEXT,
    is_demo    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_hc_partner ON happy_calls(partner_id);
"""


def log(conn, actor, action, detail=""):
    conn.execute(
        "INSERT INTO activity_log(actor,action,detail,created_at) VALUES(?,?,?,?)",
        (actor, action, detail, now()),
    )


def boq_history(conn, boq_id, row, action, old_price=None, actor="시스템"):
    """표준단가 개정 이력 한 줄. price_src/price_date 는 '현재값의 출처'일 뿐 이력이 아니다.

    ⚠⚠ [라운드180] app.py 의 관리자 콘솔 3개 라우트(추가·수정·비활성)는 이걸
      부르는데, 표준단가 대량적재 CLI(seed_boq.py·seed_boq_led.py)는 app.py
      를 import 하지 않아(무겁고, import 만으로 운영 DB 스키마를 건드리는
      부작용이 있다 — app.py 최상단의 DB.init_db() 호출) 이 함수에 닿을 길이
      없었다 — 실측: 실제 반복 적재 실행이 42개 항목의 단가를 그 자리에서
      덮어썼는데 이력은 0행이었다. app.py 와 seed 스크립트가 둘 다 이미
      신뢰하는 db.py 로 옮겨 공유 지점을 하나로 만든다.

    ⚠ 이 이력이 없으면 캘리브레이션이 불가능하다 — '그때 그 단가 대비 낙찰가'를 봐야 하는데
      그 시점 단가를 되살릴 수 없다. 삭제도 물리 삭제면 과거 견적의 근거가 함께 증발한다.
    """
    try:
        conn.execute(
            """INSERT INTO boq_price_history
                   (boq_id, major, item, spec, unit, old_price, new_price,
                    price_src, price_date, action, actor, changed_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,datetime('now','+9 hours'))""",
            (boq_id, row.get("major"), row.get("item"), row.get("spec"), row.get("unit"),
             old_price, row.get("ref_price"),
             (row.get("price_src") or "")[:200], (row.get("price_date") or "")[:20],
             action, actor))
    except sqlite3.Error as e:
        #  ⚠⚠ [라운드268] 예전엔 여기서 전부 조용히 삼켰다 — 이 함수 자체가
        #    라운드180에서 "단가 바뀌었는데 이력 0행"을 막으려 만든 통로인데,
        #    스키마 드리프트(boq_price_history 표 부재 등)로 이 INSERT 자체가
        #    실패하면 호출부(seed_boq.py 등)는 성공만 보고하고 이력 누락은
        #    아무 데도 안 남았다 — 막으려던 바로 그 상황이 침묵 속에 재발한다.
        #    형제(crypto_util.decrypt 라운드120)처럼 동작(계속 진행)은 그대로
        #    두고 실패 사실만 로그에 남긴다.
        _log.warning("boq_history 기록 실패 — 이력 없이 계속합니다 (%s: %s)",
                     type(e).__name__, e)


#  ── 지역 표기 정규화 ────────────────────────────────────────
#   실데이터에서 활성 협력사 399곳의 `region` 이 **149가지 표기**였다.
#   '경기' 27 · '경기도' 18 · '경기(안산)' 2 · '경기 (고양시)' 1 … 전부 같은 경기다.
#   그래서 지역으로 거르면 경기 75곳 중 27곳만 잡혔다 — 3분의 2가 조용히 빠진다.
#   ⚠ 원문을 덮어쓰지 않는다. '서울·경기·인천' 같은 다지역, '경기 추정(주소 미표기)'
#     같은 메모가 섞인 값이 있어 덮어쓰면 사람이 적어 둔 정보가 사라진다.
#   ⚠⚠ [라운드196] app.py 에 있던 걸 여기로 옮겼다 — compliance.py(도급 적법성
#     관문의 분할회피 합산판정)도 같은 정규화가 필요한데, compliance.py 는
#     app.py 가 거꾸로 import 하는 하위 모듈이라 app.py 를 가리킬 수 없다
#     (순환 임포트). app.py·compliance.py 가 둘 다 이미 신뢰하는 db.py 가
#     유일한 공유 지점이다. app.py 의 기존 호출부는 이름을 그대로 다시
#     내보내(재수출) 하나도 안 바뀌게 한다.
SIDO = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
        "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주")
#  긴 이름 → 짧은 이름. **긴 것부터** 봐야 '전북' 이 '전라북도' 를 가로채지 않는다.
REGION_LONG = (("충청북도", "충북"), ("충청남도", "충남"),
               ("전라북도", "전북"), ("전라남도", "전남"),
               ("경상북도", "경북"), ("경상남도", "경남"),
               ("서울특별시", "서울"), ("세종특별자치시", "세종"),
               ("강원특별자치도", "강원"), ("전북특별자치도", "전북"),
               ("제주특별자치도", "제주"), ("경기도", "경기"), ("강원도", "강원"))
_REGION_SPLIT = re.compile(r"[·,/+&]|\s*및\s*|\s+외\s+")
_REGION_PAREN = re.compile(r"[（(\[][^)）\]]*[)）\]]")


def norm_regions(s):
    """표기 → 광역 목록. 못 읽으면 빈 목록.

    ⚠ 괄호 안(시·군, 메모)은 버린다 — '경기(안산)' 과 '경기도 (평택시)' 를
      같은 것으로 봐야 지역으로 거를 수 있다.
    ⚠ 못 읽은 값을 **추측하지 않는다**. '전국' · '충청권' 은 지역이 아니다 —
      빈 목록으로 두고 화면에서 '지역 확인 필요' 로 드러낸다.
      추측해서 채우면 틀린 지역으로 업체를 부르게 된다.
    """
    s = (s or "").strip()
    if not s:
        return []
    s = _REGION_PAREN.sub(" ", s)
    out = []
    for part in _REGION_SPLIT.split(s):
        part = part.strip()
        if not part:
            continue
        for long_, short in REGION_LONG:
            if part.startswith(long_):
                if short not in out:
                    out.append(short)
                break
        else:
            for sd in SIDO:
                if part.startswith(sd):
                    if sd not in out:
                        out.append(sd)
                    break
    return out


def region_matches(raw, want):
    """이 업체(raw 표기)가 want 지역에 해당하는가.

    ⚠ 다지역 업체는 **어느 하나라도 맞으면** 해당한다 — '서울·경기·인천' 업체를
      경기로 부를 수 있어야 한다.
    """
    w = (want or "").strip()
    if not w or w == "전체":
        return True
    got = norm_regions(raw)
    if got:
        return w in got
    #  정규화가 안 되는 값은 원문에 그 글자가 들어 있는지로 마지막 판정 —
    #  '전국(주소 미표기)' 을 아무 지역으로도 부르지 않으면 영영 안 불린다.
    return w in (raw or "")


# ══════════════════════════════════════════════════════════════
#  스키마 마이그레이션
#
#  SCHEMA의 CREATE TABLE 문은 모두 IF NOT EXISTS 이므로, 이미 운영 중인 DB에
#  **컬럼을 추가해도 반영되지 않는다.** 운영 데이터를 지우지 않고 스키마를 올리려면
#  아래 목록에 (테이블, 컬럼, 정의)를 추가하기만 하면 된다. 기동할 때마다 멱등하게 실행된다.
#
#  ⚠ 컬럼 삭제·타입 변경은 이 방식으로 처리하지 않는다(테이블 재작성이 필요).
#    그런 변경이 생기면 백업 → 수동 마이그레이션 스크립트로 진행할 것.
# ══════════════════════════════════════════════════════════════
MIGRATIONS = [
    # (테이블, 컬럼, 컬럼 정의)
    # 개인정보 수집·이용 동의 기록 (개인정보 보호법 §15①1, §22 — 동의 사실의 입증책임은 처리자에게 있다)
    ("insurer_leads", "agree_privacy", "INTEGER DEFAULT 0"),
    ("insurer_leads", "agree_marketing", "INTEGER DEFAULT 0"),
    ("insurer_leads", "agreed_at", "TEXT"),
    ("insurer_leads", "agreed_ip", "TEXT"),
    ("partner_applications", "source", "TEXT DEFAULT '홈페이지'"),   # 홈페이지 / 직접접수
    #  신청서에 **사업장 주소 칸이 아예 없었다.** 그래서 승인해 만든 협력사는
    #  주소가 NULL 로 시작했고(활성 399곳 중 21곳), 주소가 없으면 좌표도 없어
    #  거리순 출동 호출에서 뒤로 밀린다. 신청 때 받아 승인 시 그대로 넘긴다.
    ("partner_applications", "address", "TEXT"),
    ("partner_applications", "lat", "REAL"),
    ("partner_applications", "lng", "REAL"),
    ("partner_applications", "agree_privacy", "INTEGER DEFAULT 0"),
    ("partner_applications", "agree_marketing", "INTEGER DEFAULT 0"),
    ("partner_applications", "agreed_at", "TEXT"),
    ("partner_applications", "agreed_ip", "TEXT"),
    # 최초 로그인 시 비밀번호 변경 강제 (초기 발급 비밀번호가 그대로 남는 것을 방지)
    ("admins", "must_change_pw", "INTEGER DEFAULT 0"),
    ("partners", "must_change_pw", "INTEGER DEFAULT 0"),
    ("insurers", "must_change_pw", "INTEGER DEFAULT 0"),
    # 낙찰 확정가 · 준공일
    #  low_price 는 '입찰 진행 중 최저가'라서 낙찰 후에도 계속 흔들릴 수 있다.
    #  정산·절감률 계산은 반드시 '확정된 낙찰가(award_amount)' 기준이어야 하므로 분리한다.
    ("cases", "award_amount", "INTEGER"),
    ("cases", "awarded_at", "TEXT"),
    # 수수료율은 실수(REAL)로 두면 부동소수 오차가 금액에 섞인다.
    #  베이시스포인트(1% = 100bp) 정수로 저장해 정확히 계산한다. 10% = 1000bp
    ("insurers", "fee_rate_bp", "INTEGER DEFAULT 1000"),
    ("settlements", "fee_rate_bp", "INTEGER DEFAULT 1000"),
    ("settlements", "case_id", "INTEGER"),
    # 정산 테넌시를 '업체명 문자열'로 판정하면 동명 업체끼리 서로의 정산을 보게 된다.
    #  (398개사에서는 우연히 중복이 없지만, 수천 개로 늘면 반드시 발생한다)
    #  ID 로 묶어 두면 이름이 바뀌어도 안전하다.
    ("settlements", "partner_id", "INTEGER"),
    ("settlements", "insurer_id", "INTEGER"),
    # 입점 신청 폼은 '보유 면허·등록업종'을 받는데 저장할 컬럼이 없어 값이 버려지고 있었다.
    # 시행사 자격(건축공사업·실내건축공사업 등) 심사의 핵심 정보다.
    ("partner_applications", "license", "TEXT"),
    # 1인 사업자(상시 인력 없음)는 받지 않는다 — 접수·심사에서 판별할 상시인력 수.
    #  NULL=미확인, 0=1인 사업자(대표뿐), 1↑=상시인력 있음.
    ("partner_applications", "staff_count", "INTEGER"),
    ("partners", "staff_count", "INTEGER"),
    # 변경 견적(실사 후 증액) 재경매 — 사건에 라운드·추가금액을 얹는다.
    ("cases", "co_round", "INTEGER DEFAULT 0"),           # 변경견적 라운드(0=없음, 1~3)
    ("cases", "co_extra", "INTEGER DEFAULT 0"),           # 확정된 추가 금액(원 낙찰가에 합산)
    # 재경매를 기존 auctions/bids 로 처리하되, 어떤 변경건의 어떤 유형 경매인지 링크한다.
    ("auctions", "change_order_id", "INTEGER"),
    ("auctions", "kind", "TEXT DEFAULT '원경매'"),        # 원경매 / 추가분 / 전체재경매
    ("auctions", "round", "INTEGER DEFAULT 0"),
    # 하자 사진 — 어떤 하자에 붙은 사진인지. 사건 사진과 같은 photos 테이블을 쓰되 구분한다.
    ("photos", "defect_id", "INTEGER"),
    #  이 사진이 **어느 지적 사진을 고친 결과**인가(photos.id).
    #   보험사가 "내가 지적한 세 곳이 다 고쳐졌나"를 대조하려면 짝이 있어야 한다.
    #   NULL 이면 그냥 하자에 붙인 참고 사진이다.
    ("photos", "fix_for", "INTEGER"),
    # ── 보험사 API 연동 ────────────────────────────────────────
    #  보험사 전산이 우리 API 로 사건을 바로 접수하고 상태를 받아간다.
    #  API 키는 비밀번호처럼 **원문을 저장하지 않는다** — SHA-256 해시만 두고,
    #  화면 식별용으로 접두부(prefix)만 평문으로 남긴다. 키는 발급 순간에 딱 한 번 보여준다.
    ("insurers", "api_key_hash", "TEXT"),        # sha256(키) — 조회·대조용
    ("insurers", "api_key_prefix", "TEXT"),      # 화면 표시용 앞 12자 (bok_live_xxxx)
    ("insurers", "api_key_created", "TEXT"),
    ("insurers", "api_enabled", "INTEGER DEFAULT 0"),   # 키 발급만으로는 안 되고 명시적으로 켠다
    ("insurers", "webhook_url", "TEXT"),         # 상태 변경 시 통지받을 주소
    ("insurers", "webhook_secret", "TEXT"),      # 웹훅 본문 HMAC 서명 키(위변조 검증)
    # 사건 등록 시 보험사가 붙이는 추가 전달사항(등록 메모)
    ("cases", "note", "TEXT"),
    # 사건 접수 출처 — 포털/ API/ 관리자 수동 (통계·감사용)
    ("cases", "source", "TEXT DEFAULT '포털'"),
    # AI 파손 분석 리포트(등록 사진 기반) — 사건에 1건 요약 저장
    ("cases", "ai_report", "TEXT"),
    ("cases", "ai_severity", "TEXT"),            # 경미 / 보통 / 중대 (AI 판정)
    # ── 실시간 알림 수신 대상·읽음 상태 ─────────────────────────
    #  기존 notifications 는 '누구에게 갔는지'가 문자열 한 칸(target)뿐이라
    #  포털에서 '내 알림'을 못 고른다. 수신 주체를 ID 로 붙이고 읽음 시각을 둔다.
    ("notifications", "audience_type", "TEXT"),  # insurer / partner / admin / all
    ("notifications", "insurer_id", "INTEGER"),
    ("notifications", "partner_id", "INTEGER"),
    ("notifications", "case_id", "INTEGER"),
    ("notifications", "read_at", "TEXT"),        # NULL = 안 읽음
    ("notifications", "url", "TEXT"),            # 클릭 시 이동할 경로(선택)
    # ── 보험사·협력사 조직 하위계정 등급 ────────────────────────
    #  포털 계정도 콘솔처럼 3등급. 최고관리자만 하위 아이디를 만든다.
    #  parent_id 가 있으면 하위계정(같은 기관 소속), NULL 이면 조직 원계정.
    ("insurers", "portal_role", "TEXT DEFAULT '최고관리자'"),
    ("insurers", "parent_id", "INTEGER"),        # 소속 원계정(조직) id — NULL=원계정
    ("partners", "portal_role", "TEXT DEFAULT '최고관리자'"),
    ("partners", "parent_id", "INTEGER"),
    # ── 정산 자동 흐름: 보험사 최종 완료 승인 ───────────────────
    #  사용자 정의 흐름: 보험사 '공사 완료 승인' → (보험사 입금) → 우리 입금확인
    #   → 더블 크로스체크 → 우리 승인 → 10% 공제 자동이체.
    #  보험사 승인이 입금확인의 선행 관문이 된다.
    ("settlements", "insurer_approved", "INTEGER DEFAULT 0"),
    ("settlements", "insurer_approved_at", "TEXT"),
    ("settlements", "double_checked", "INTEGER DEFAULT 0"),   # 우리측 더블 크로스체크 완료 표식
    # ── 협력업체 연락처 수집·마케팅 수신 관리 ────────────────────
    #  초기 398개사는 리서치로 모아 **전화는 있고 이메일이 없다.**
    #  콜드메일을 보내려면 이메일을 채워야 하고, 광고성 발송에는 수신거부 관리가 법정 의무다.
    ("partners", "email2", "TEXT"),            # 보조 이메일(대표 외 담당자)
    ("partners", "manager", "TEXT"),           # 담당자명
    ("partners", "contact_note", "TEXT"),      # 수집 메모(통화 결과 등)
    ("partners", "contact_updated", "TEXT"),   # 연락처 최종 확인 시각
    ("partners", "email_opt_out", "INTEGER DEFAULT 0"),   # 광고성 수신거부(정보통신망법 §50④)
    ("partners", "sms_opt_out", "INTEGER DEFAULT 0"),
    # ⚠ 이메일을 '어디서 얻었는지'와 '광고 수신 동의가 있는지'는 반드시 구분해 저장한다.
    #    정보통신망법 §50① — 영리 목적 광고성 정보는 **사전 동의**가 있어야 전송할 수 있다.
    #    §50-2  — 수집 거부 의사가 밝혀진 홈페이지에서 자동으로 주소를 수집하면 안 된다.
    #    홈페이지에서 자동 수집한 주소는 '공개된 연락처'일 뿐 **동의가 아니다.**
    #    이 둘을 한 칸에 뭉뚱그리면 동의 없는 주소로 광고를 보내게 된다.
    ("partners", "email_source", "TEXT"),        # 입점신청 / 직접입력 / 수집(홈페이지)
    ("partners", "email_consent", "INTEGER DEFAULT 0"),   # 광고 수신 동의 여부
    # ⚠ 문자·알림톡 동의는 이메일 동의와 **법적으로 별개**다(정보통신망법 §50①).
    #   예전에는 email_consent 하나뿐이라, 문자 캠페인은 동의를 볼 수단 자체가 없었다.
    #   기본 0 — '연락처를 안다'는 동의가 아니다.
    ("partners", "sms_consent", "INTEGER DEFAULT 0"),
    # 계정 상태 변경 사유 — 협력사는 자기 계정이 왜 내려갔는지 알 수 없었다.
    #  퇴출·경고는 생계가 걸린 일이라 사유·시점·처리자를 남기고 본인에게 알려야 한다.
    ("partners", "status_reason", "TEXT"),
    ("partners", "status_changed_at", "TEXT"),
    ("partners", "status_changed_by", "TEXT"),
    # ⚠⚠ [라운드136] 보험사는 이 3컬럼이 아예 없었다 — '중지' 버튼이 협력사
    #   퇴출과 똑같이 로그인을 영구히 막는데도, 사유·시점·처리자를 남길 곳이
    #   없어 왜 멈췄는지 아무도 설명할 수 없었다(실측: 협력사 쪽 강등 관문과
    #   대조해 발견).
    ("insurers", "status_reason", "TEXT"),
    ("insurers", "status_changed_at", "TEXT"),
    ("insurers", "status_changed_by", "TEXT"),
    # 하자 이의제기 — 판정하지 않고 '검토 요청'만 받는다(귀책 판단은 사람이 한다)
    ("defects", "dispute_reason", "TEXT"),
    ("defects", "disputed_at", "TEXT"),
    #  ⚠ dispute_reason 을 지우는 코드가 전 코드에 없다(협력사가 그 사유를 되짚어
    #    볼 수 있어야 한다) — 그런데 그러면 화면의 "이의 검토중" 배지가 dispute_reason
    #    존재 여부만으로 판정되는 한 **영원히** 뜬다. '있음/없음'과 '아직 안 봄/봤음'은
    #    다른 질문이라 별도 컬럼으로 답한다.
    ("defects", "dispute_resolved_at", "TEXT"),
    ("partners", "email_collected_at", "TEXT"),
    # ── B4 입찰 마감 자동화 ────────────────────────────────────
    #  원경매 재개(연장·재공고) 횟수. auctions.round 는 **재경매 라운드**로 이미 쓰이므로
    #  절대 재사용하지 않는다(한 컬럼이 두 의미를 가지면 화면만 조용히 틀어진다).
    ("auctions", "extend_count", "INTEGER DEFAULT 0"),
    #  ⚠⚠ [라운드103] 바로 위 경고가 그대로 현실이 됐다 — extend_count 는 낙찰취소
    #    재공고(api_case_cancel_award)·직접배정 재개(_open_original_auction) 등
    #    "이 경매 행을 다시 열었다"는 사건 전부가 같이 올리는데, api_case_reopen
    #    의 MAX_REOPEN(3회) 상한만 이 값을 "내가 유찰 뒤 재개를 누른 횟수"로 읽었다.
    #    운영자가 재개 버튼을 두 번밖에 안 눌렀어도, 그 전에 낙찰취소가 한 번
    #    있었으면 세 번째 클릭에서 "재개 상한 도달"로 막혀 정상 사건이 조기에
    #    오프라인 종결로 내몰렸다(되돌리는 경로 없음). api_case_reopen 전용
    #    카운터를 따로 둔다 — extend_count 는 기존 표시·다른 경로 그대로 둔다.
    ("auctions", "reopen_count", "INTEGER DEFAULT 0"),
    # ── B5 가견적 정합성 점검 ──────────────────────────────────
    #  판정 메타 — "어느 사진을 언제 보고 판정했나". 지금은 둘 다 기록이 없다.
    ("cases", "ai_severity_at", "TEXT"),
    ("cases", "ai_photo_id", "INTEGER"),
    #  담당자가 직접 고른 파손 정도. AI 키가 없어도 점검이 돌게 하는 축이다.
    #  대조에는 이 값이 AI 값보다 **우선**한다 — 판정 주체는 사람이다.
    ("cases", "human_severity", "TEXT"),
    ("cases", "human_severity_by", "TEXT"),
    ("cases", "human_severity_at", "TEXT"),
    #  경고 확인 처리 — "시스템이 이의를 달았고 사람이 그래도 이 금액이라 정했다"는 기록.
    ("cases", "est_ack_code", "TEXT"),
    ("cases", "est_ack_est", "INTEGER"),      # 확인 당시 가견적 — 금액이 바뀌면 확인은 무효
    ("cases", "est_ack_by", "TEXT"),
    ("cases", "est_ack_at", "TEXT"),
    #  시험·데모로 만들어진 사건을 근거 숫자에서 뺀다.
    ("cases", "stats_exclude", "INTEGER DEFAULT 0"),
    #  표준 단가의 신뢰 근거 — "언제 무엇을 근거로 정한 단가인가"에 답할 수단.
    ("standard_boq", "price_src", "TEXT"),
    ("standard_boq", "price_date", "TEXT"),
    ("standard_boq", "updated_at", "TEXT"),
    ("standard_boq", "active", "INTEGER DEFAULT 1"),
    # ── B7 도달 관문 ───────────────────────────────────────────
    #  발송 대기 건을 사람이 수동으로 처리했다는 기록. "보낸 척" 하지 않으면서
    #  도달을 사람이 책임지는 유일한 방법이다.
    ("notifications", "handled_by", "TEXT"),
    ("notifications", "handled_at", "TEXT"),
    ("notifications", "handled_note", "TEXT"),
    # ── 데모 데이터 표식 ────────────────────────────────────────
    #  운영 개시 때 데모만 골라 지우려면 '어떤 행이 데모인지'를 알아야 한다.
    #  예전에는 보험사명에 '○○'/'△△' 가 들어있는지로 판별했는데,
    #  시드에는 '메리츠화재'·'DB손보' 처럼 **실제 사명**으로 들어간 행도 있어서
    #  그 데모 사건·정산이 운영 데이터에 그대로 남아 통계·정산을 오염시켰다.
    #  이름이 아니라 표식으로 판별한다.
    ("cases", "is_demo", "INTEGER DEFAULT 0"),
    ("settlements", "is_demo", "INTEGER DEFAULT 0"),
    ("defects", "is_demo", "INTEGER DEFAULT 0"),
    ("insurers", "is_demo", "INTEGER DEFAULT 0"),
    ("insurer_leads", "is_demo", "INTEGER DEFAULT 0"),
    ("partner_applications", "is_demo", "INTEGER DEFAULT 0"),
    ("notices", "is_demo", "INTEGER DEFAULT 0"),
    ("notifications", "is_demo", "INTEGER DEFAULT 0"),
    # 실발송(팝빌) — 시도 횟수·발송 시각·결과 상세(번호는 마스킹해서만 기록)
    ("notifications", "send_attempts", "INTEGER DEFAULT 0"),
    ("notifications", "sent_at", "TEXT"),
    ("notifications", "send_detail", "TEXT"),
    # 2단계 인증(일회용 비밀번호) — 외부 접속 시 필수
    #  [법령] 개인정보 안전성 확보조치 기준 §6④ 외부 접속 시 안전한 인증수단
    #  totp_counter: 마지막으로 쓴 시간구간. 같은 코드 재사용을 막는 값이라 반드시 갱신한다.
    ("admins", "totp_secret", "TEXT"),
    ("admins", "totp_enabled", "INTEGER DEFAULT 0"),
    ("admins", "totp_counter", "INTEGER"),
    ("admins", "totp_at", "TEXT"),
    ("auctions", "is_demo", "INTEGER DEFAULT 0"),
    ("bids", "is_demo", "INTEGER DEFAULT 0"),
    ("standard_boq", "is_demo", "INTEGER DEFAULT 0"),
    # ── 2트랙 접수 (사진 유무로 갈리는 흐름) ──────────────────────
    #  사고 접수의 상당수가 사진 없이 들어온다. 사진이 없으면 파손 규모를 몰라
    #  입찰 상한을 정할 수 없고, 그래서 경매를 열 수 없다.
    #  · '사진있음' → 곧바로 경매
    #  · '사진없음' → 인근 업체 선착순 출동으로 사진·실견적을 먼저 확보
    ("cases", "intake_type", "TEXT DEFAULT '사진있음'"),   # 사진있음 / 사진없음
    ("cases", "dispatch_status", "TEXT"),                 # 수배중 / 출동중 / 사진확보 / 수배실패
    ("cases", "first_partner_id", "INTEGER"),             # 최초 출동해 사진을 올린 업체
    ("cases", "first_photo_at", "TEXT"),
    # 1차 합의로 경매 없이 시공이 확정된 건인지 (경매 건과 통계를 섞지 않기 위해)
    ("cases", "award_route", "TEXT"),                     # 경매 / 1차합의
    ("dispatches", "is_demo", "INTEGER DEFAULT 0"),
    ("field_agreements", "is_demo", "INTEGER DEFAULT 0"),
    # ── 1차 합의의 '개산 근거' 재현용 ────────────────────────────
    #  예전에는 engine_low/high 정수 두 개만 남아, 어떤 수선패턴에 어떤 입력을 넣어
    #  나온 값인지 사후에 소명할 수 없었다(단가가 개정되면 재계산도 불가).
    #  게다가 그 두 값을 **요청 본문에서 그대로 받아** 저장해, 화면을 우회하면
    #  '엔진이 이렇게 냈다'는 기록을 임의로 만들 수 있었다 → 서버 재계산으로 전환.
    ("field_agreements", "engine_pattern", "TEXT"),   # 수선패턴 id
    ("field_agreements", "engine_inputs", "TEXT"),    # 입력값 JSON
    ("field_agreements", "engine_basis", "TEXT"),     # estimate() 반환 전체 JSON 스냅샷
    ("field_agreements", "engine_ver", "TEXT"),       # 단가·할증 개정 버전
    ("field_agreements", "engine_at", "TEXT"),        # 계산 시각(KST)
    # ── 승인 주체 (법률 철칙: 금액을 정하는 것은 보험사) ─────────
    #  복구온은 견적 원문을 전달할 뿐이고, 승인/부동의는 **보험사 계정이** 한다.
    #  기존 insurer_staff 는 운영자가 손으로 적는 자유입력이라 신뢰 근거가 못 된다
    #  → 표시용으로만 남기고, 판단 근거는 아래 로그인 계정 기록을 쓴다.
    ("field_agreements", "approver_org_id", "INTEGER"),   # 승인한 보험사(기관) id
    ("field_agreements", "approver_user_id", "INTEGER"),  # 하위계정 id(원계정이면 NULL)
    ("field_agreements", "approver_name", "TEXT"),        # 로그인 계정 이름
    ("field_agreements", "approver_role", "TEXT"),        # 그 계정 등급
    ("field_agreements", "approved_at", "TEXT"),
    ("field_agreements", "reject_reason", "TEXT"),        # 부동의 사유
    # ── 추가공사(변경견적) 발주처 확인 ─────────────────────────
    #  증액되면 청구액이 승인 금액과 달라진다. 보상 담당자가 결재 라인에서 그 차이를
    #  설명할 수 있어야 하므로, 확인/부동의 사실을 기록으로 남긴다.
    #  ⚠ 금액을 바꾸는 기능이 아니다(우리가 금액을 정하지 않는다는 원칙과 같다).
    ("change_orders", "insurer_ack", "TEXT"),          # 확인 / 부동의
    ("change_orders", "insurer_ack_by", "TEXT"),
    ("change_orders", "insurer_ack_at", "TEXT"),
    ("change_orders", "insurer_ack_note", "TEXT"),
    ("change_orders", "insurer_ack_amount", "INTEGER"),  # 확인 당시의 합산가(금액 변경 시 확인 무효)
    # ── 정산 취소(무효화) ──────────────────────────────────────
    #  검수 승인을 잘못 눌렀거나, 변경 견적이 정산 이후에 확정돼 막힌 경우의 유일한 해법이
    #  DB 직접 수정이었다. **행을 지우지 않고** 취소 표시만 한다 —
    #  지우고 다시 만들면 과거 월 정산 명세서와 누적 거래액이 조용히 달라진다.
    ("settlements", "void_status", "TEXT"),      # NULL(정상) / '취소'
    ("settlements", "void_reason", "TEXT"),
    ("settlements", "void_by", "TEXT"),
    ("settlements", "void_at", "TEXT"),
    # ── 낙찰 취소 ──────────────────────────────────────────────
    #  낙찰업체가 부도·잠적·착공거부하면 '시공중' 사건을 되살릴 방법이 없었다.
    ("cases", "award_canceled_at", "TEXT"),
    ("cases", "award_cancel_reason", "TEXT"),
    # 최초 투찰 시각 — 재투찰이 created_at 을 덮어써 '언제 처음 들어왔나'가 사라졌다.
    #  (created_at 은 '마지막 제출 시각'의 의미로 그대로 둔다)
    ("bids", "first_bid_at", "TEXT"),
    #  낙찰을 취소하면 그 회차의 입찰은 여기에 시각이 박혀 **후보에서 빠진다**.
    #  없을 때는 부도로 취소한 그 업체의 옛 입찰이 재낙찰 후보로 그대로 남았다.
    #  지우지 않고 표시만 하는 이유 — 입찰 이력은 소명 자료라 보존해야 한다.
    #  보험사 전산이 같은 요청을 두 번 보내도 사건이 하나만 생기게 하는 열쇠.
    #  (타임아웃 뒤 재시도가 사건·경매·정산을 통째로 2벌 만들었다)
    ("cases", "idem_key", "TEXT"),
    #  ⚠⚠ [라운드227] idem_key 만으로는 "같은 열쇠, 다른 내용"을 못 잡는다 —
    #    실측: 열쇠를 재사용하며 공종·지역·가견적을 완전히 다르게 보내도
    #    조용히 첫 요청의 사건을 그대로 돌려주고 두 번째 요청 내용은
    #    아무 흔적도 없이 사라졌다. 핵심 내용의 지문을 같이 저장해 대조한다.
    ("cases", "idem_fingerprint", "TEXT"),
    #  ⚠⚠ [라운드228] api_settlement_undo 는 "지금 상태만 보고" 되돌릴 다음
    #    단계를 추론한다 — 같은 요청이 재시도되면 첫 호출이 이미 되돌린
    #    다음 단계까지 캐스케이드로 또 되돌렸다(실측: 지급검수 되돌리기
    #    재시도가 보험사 입금확인까지 되돌림). 클라이언트가 클릭 1회당
    #    한 번만 만드는 열쇠를 저장해, 같은 열쇠로 재시도되면 이미 한 일을
    #    또 하지 않고 그대로 응답만 다시 준다.
    ("settlements", "last_undo_key", "TEXT"),
    #  ⚠⚠ [라운드229] photo_ai.save_upload() 는 EXIF(GPS 포함) 제거가 실패하면
    #    "사진을 잃는 것보다 낫다"며 원본을 그대로 저장하고 그 사실을 반환값
    #    (exif_error)에 담아 준다(_warn_exif 가 운영팀에 알리기만 함) — 그런데
    #    이 값이 photos 테이블에 저장되지 않아, 열람 게이트(_photo_visible_to)
    #    가 "이 사진의 GPS 가 안 지워졌다"는 사실 자체를 알 방법이 없었다.
    #    실측: 42,000,000픽셀급(요즘 고화소 폰 원본 흔한 범위) JPEG/PNG 는
    #    8MB 상한 안에 쉽게 들어오면서 재인코딩(EXIF 제거)은 픽셀상한 초과로
    #    건너뛰어, GPS 가 박힌 원본이 그대로 저장되고 입찰 중인 모든 협력사
    #    (아직 낙찰 안 된 경쟁사 포함)에게 그대로 열렸다.
    ("photos", "exif_error", "TEXT"),
    ("bids", "voided_at", "TEXT"),
    ("bids", "void_reason", "TEXT"),
    # ── 견적엔진 ↔ 표준단가표 연결 열쇠 ─────────────────────────
    #  엔진(repair_estimate.SKU)과 어드민 단가표(standard_boq)가 두 벌로 따로 놀아,
    #  어드민에서 단가를 고쳐도 견적이 안 바뀌었다. 이 키가 붙은 행의 단가가 엔진에 주입된다.
    ("standard_boq", "sku_key", "TEXT"),
    # ── 미수선 종결 ────────────────────────────────────────────
    #  현장에 가 보면 수선하지 않고 끝나는 건이 있다.
    #  피해자가 원치 않거나, 파손이 경미하거나, 이미 복구됐거나, 자기 부담으로 처리하는 경우다.
    #  이 결과를 남기지 않으면 사건이 '출동은 했는데 아무 일도 없는' 상태로 떠 있고,
    #  나중에 왜 공사가 없었는지 아무도 설명하지 못한다.
    #  ⚠ 미수선도 '결과'다 — 실패가 아니라 정상 종결의 한 갈래로 기록한다.
    ("dispatches", "outcome", "TEXT"),            # 수선진행 / 미수선종결
    ("dispatches", "no_repair_reason", "TEXT"),   # 미수선 사유(분류)
    ("dispatches", "no_repair_note", "TEXT"),     # 현장 설명(자유 기재)
    ("dispatches", "no_repair_by", "TEXT"),       # 누가 확인했는지(업체 담당자명)
    ("dispatches", "no_repair_at", "TEXT"),
    # ── 거리순 배차 ────────────────────────────────────────────
    #  수배 시 각 협력사가 현장에서 몇 km 떨어졌는지(개략치)와 몇 번째로 불렸는지 기록.
    #  콘솔에서 '가까운 순으로 불렀다'가 보이고, 나중에 도착률 분석에도 쓴다.
    ("dispatch_calls", "dist_km", "REAL"),
    ("dispatch_calls", "call_order", "INTEGER"),
    ("cases", "no_repair_reason", "TEXT"),        # 사건에도 남겨 목록·통계에서 바로 보이게
    # ── 단계 체류시간 ──────────────────────────────────────────
    #  '지금 무엇이 며칠째 멈춰 있는가'가 이 플랫폼 운영의 핵심 화면인데, 상태가 언제
    #  이 값이 됐는지를 아무도 기록하지 않아 경과일을 계산할 수 없었다(경보 패널이
    #  '최근 8건'을 보여준 이유). 상태를 바꿀 때마다 여기에 시각을 남긴다.
    ("cases", "status_at", "TEXT"),
    # ── 현장 지도 ──────────────────────────────────────────────
    #  사건에는 주소 문자열만 있어 지도에 못 올린다. 지역 중심좌표로 자동 배치하되,
    #  정밀 위치가 필요하면 수동 좌표를 넣는다(수동이 항상 우선).
    ("cases", "lat", "REAL"),
    ("cases", "lng", "REAL"),
    ("cases", "geo_src", "TEXT"),                 # 지역중심 / 수동 / 주소검색
    # ── 협력사 좌표 ────────────────────────────────────────────
    #  협력사에는 좌표 칸이 아예 없어서, 거리순 배차가 '시군구 중심 + 업체번호 해시'
    #  로 만든 가짜 좌표로 거리를 쟀다. 실제 데이터에서 활성 399곳이 서로 다른
    #  140개 점에 뭉쳐, 같은 구 안에서의 '가까운 순'은 사실상 해시 순서였다.
    #  주소를 검색해서 고르면 진짜 좌표가 들어오고, 그때부터 거리가 거리다.
    ("partners", "lat", "REAL"),
    ("partners", "lng", "REAL"),
    ("partners", "geo_src", "TEXT"),
    # ── 담당 매니저 (머큐리의 필드매니저에 해당) ──────────────
    #  cases.manager 가 이미 있으나 기본값 '자동' 문자열이라, 실제 배정과 구분해
    #  '누가 언제 배정했는지'를 함께 남긴다.
    ("cases", "manager_assigned_by", "TEXT"),
    ("cases", "manager_assigned_at", "TEXT"),
    # ── 피해자 진행조회 (로그인 없는 링크 접속) ────────────────
    #  피해자는 계정이 없다. 추측 불가능한 토큰 하나로 자기 사건만 본다.
    ("cases", "track_token", "TEXT"),
    #  ⚠⚠ [라운드295] 개인정보 파기(cmd_prune_personal)가 track_token 을
    #    NULL 로 지우면 그 시점부터 track_page() 가 이 행을 원문 토큰으로
    #    영원히 못 찾는다 — "링크 만료"(track_expired.html)를 보여줘야 할
    #    자리에 "페이지 없음"(404)이 나갔다. 원문과 별도로 한 방향 해시를
    #    둬서, 파기 뒤에도 "이 토큰이 예전에 발급됐었는가"만은 답할 수 있게
    #    한다(해시는 원문을 복원할 수 없으므로 파기 대상이 아니다).
    ("cases", "track_token_hash", "TEXT"),
    #  피해자 조회 링크는 만료가 없어서, 공사가 끝난 뒤에도 영원히 열렸다.
    #  문자가 전달·유출되면 담당자 이름·업체명·진행이력이 계속 조회된다.
    #  발급 시각을 남겨 일정 기간이 지나면 닫는다(재발급하면 다시 열린다).
    ("cases", "track_issued_at", "TEXT"),
    #  피해자가 **실제로 열어 봤는가** — 링크를 보낸 것과 본 것은 다르다.
    #  발주처에게 "고객이 스스로 확인했다" 를 보여 줄 유일한 증거다.
    #  ⚠ 횟수와 마지막 시각만 센다. 누가·어디서는 세지 않는다(개인정보 최소수집).
    ("cases", "track_views", "INTEGER DEFAULT 0"),
    ("cases", "track_last_at", "TEXT"),
    ("cases", "victim_name", "TEXT"),
    ("cases", "victim_phone", "TEXT"),
    # ── 협력사 건설업 등록 전수조사 (머큐리 재현조건 0단계) ────
    #  하도급 상대는 등록 건설사업자여야 한다(건산법 §25②).
    #  '등록군/미등록군'을 갈라 두지 않으면 무등록 업체 배정을 시스템이 못 막는다.
    ("partners", "license_status", "TEXT DEFAULT '미확인'"),  # 등록확인 / 무등록 / 미확인
    ("partners", "license_no", "TEXT"),           # 등록번호 (예: 대전중구 22-나-05)
    ("partners", "license_trades", "TEXT"),       # 보유 업종 (쉼표 구분)
    ("partners", "license_checked_at", "TEXT"),   # 조사 시각
    ("partners", "license_checked_by", "TEXT"),   # 조사자
    #  ── 온보딩 추적 ────────────────────────────────────────
    #  계정을 만든 것 / 안내를 보낸 것 / 실제로 들어와 본 것은 **전부 다르다.**
    #  399곳 중 계정 1곳이던 시절엔 이 셋을 구분할 방법이 없어
    #  "업체를 확보했다" 와 "업체가 입찰할 수 있다" 를 같은 것으로 착각했다.
    ("partners", "cred_issued_at", "TEXT"),       # 계정을 만든 시각
    ("partners", "invited_at", "TEXT"),           # 안내를 보낸(또는 전달한) 시각
    ("partners", "first_login_at", "TEXT"),       # 처음 실제로 들어온 시각
    #  ⚠⚠ [라운드164] _campaign_recipients() 가 돌려주는 넷(ok·no_contact·
    #    opted·no_consent) 중 no_consent 만 저장 컬럼이 없었다 — 캠페인을
    #    저장하는 순간 "수신동의가 없어 몇 곳을 뺐는가"(정보통신망법 §50①
    #    소명 근거)가 영구히 사라졌다. 형제 skipped_optout/skipped_nocontact
    #    와 같은 대우를 준다.
    ("campaigns", "skipped_noconsent", "INTEGER DEFAULT 0"),
    #  ⚠ 정산 구조 변경(2026-10-18, 토니 결정) — 전자금융거래법상 PG(전자지급결제대행)
    #    등록 리스크를 없애기 위해 "보험사→복구온→시행사"(복구온이 전액을 경유)를
    #    "보험사→시행사 직접 지급 + 보험사→복구온 수수료(fee) 별도 지급"으로 바꾼다.
    #    기존 insurer_paid/transfer_status 는 "시행사가 돈을 받았는가"를 그대로
    #    추적하면 되므로 안 건드린다(누가 보냈는지는 바뀌어도 받았다는 사실 자체는
    #    같은 의미). 새로 필요한 건 수수료(fee) 입금만 **독립적으로** 추적하는 것 —
    #    전에는 fee 가 amount 안에 섞여 들어와 insurer_paid 하나로 같이 확인됐지만,
    #    이제 보험사가 fee 를 별도 송금하므로 그게 들어왔는지 따로 확인해야 한다.
    ("settlements", "fee_collect_status", "TEXT DEFAULT '대기'"),   # 대기 / 완료
    ("settlements", "fee_collected_at", "TEXT"),
    ("settlements", "fee_collected_by", "TEXT"),
]

# seed() 가 넣은 행을 전부 데모로 표시할 테이블 목록
DEMO_TABLES = ["cases", "settlements", "defects", "insurers", "insurer_leads",
               "partner_applications", "notices", "notifications", "auctions",
               "bids", "standard_boq"]

# 시공 사진 — 별도 CREATE 로 관리(컬럼이 많고 인덱스가 필요)
PHOTO_SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    partner_id INTEGER,
    uploader TEXT,                      -- 업로드한 주체 표시명
    uploader_role TEXT,                 -- 협력사 / 내부
    -- 파일 (원본명은 표시용. 실제 저장명·경로는 서버가 만든 값만 쓴다)
    rel_path TEXT NOT NULL,
    orig_name TEXT,
    mime TEXT,
    ext TEXT,
    size INTEGER,
    sha256 TEXT,
    -- 분류
    kind TEXT,                          -- 확정 분류 (착공전/시공중/완료/영수증/기타)
    ai_kind TEXT,                       -- AI 가 제안한 분류
    ai_confidence INTEGER DEFAULT 0,
    ai_model TEXT,
    ai_note TEXT,
    -- 검수
    review_status TEXT DEFAULT '대기',   -- 대기 / 승인 / 반려
    reviewed_by TEXT,
    reviewed_at TEXT,
    reject_reason TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_photo_case ON photos(case_id);
CREATE INDEX IF NOT EXISTS idx_photo_review ON photos(review_status);
-- 같은 사건에 같은 파일을 두 번 올리는 것을 DB 차원에서 막는다
CREATE UNIQUE INDEX IF NOT EXISTS idx_photo_dedup ON photos(case_id, sha256);
"""


def migrate(conn, verbose=False):
    """운영 DB를 지우지 않고 스키마를 최신으로 올린다. 이미 있는 컬럼은 건너뛴다."""
    # [R5-04] CREATE TABLE 문을 먼저 실행한다.
    #  예전 migrate() 는 컬럼 추가만 해서, photos 처럼 **테이블 자체가 없는** 경우를
    #  만들지 못했다. DEPLOY.md 가 안내하는 `manage.py migrate` 갱신 절차에 구멍이 있었다.
    #  CREATE ... IF NOT EXISTS 라 이미 있으면 아무 일도 하지 않는다.
    conn.executescript(SCHEMA)
    conn.executescript(PHOTO_SCHEMA)
    conn.commit()

    applied = []
    for table, column, coldef in MIGRATIONS:
        try:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if not cols or column in cols:
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")
            applied.append(f"{table}.{column}")
        except sqlite3.OperationalError as e:
            # [R5-05] gunicorn 워커 5개가 동시에 부팅하면 같은 ALTER 가 겹쳐
            #  "duplicate column name" 이 날 수 있다. 그건 다른 워커가 이미 했다는 뜻이니 무시한다.
            #  (예외를 밖으로 던지면 그 워커가 죽어 기동이 실패한다)
            if "duplicate column" not in str(e).lower():
                if verbose:
                    print(f"  [마이그레이션] {table}.{column} 실패: {e}")
    if applied:
        conn.commit()
        if verbose:
            print(f"  [마이그레이션] 컬럼 {len(applied)}개 추가: {', '.join(applied)}")

    # ── 마이그레이션 컬럼 위의 인덱스 ──────────────────────────
    #  ALTER 로 방금 추가한 컬럼은 SCHEMA 의 CREATE INDEX 로는 못 만든다(구 DB엔 컬럼이 없었음).
    #  컬럼이 확실히 생긴 지금 시점에 멱등하게 만든다.
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_notif_insurer ON notifications(insurer_id, read_at)",
        "CREATE INDEX IF NOT EXISTS idx_notif_partner ON notifications(partner_id, read_at)",
        "CREATE INDEX IF NOT EXISTS idx_notif_audience ON notifications(audience_type, read_at)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_insurer_apikey ON insurers(api_key_hash)",
        "CREATE INDEX IF NOT EXISTS idx_insurer_parent ON insurers(parent_id)",
        "CREATE INDEX IF NOT EXISTS idx_partner_parent ON partners(parent_id)",
        "CREATE INDEX IF NOT EXISTS idx_auctions_sweep ON auctions(status, deadline)",
        #  ⚠ 하자 목록이 행마다 photos 를 defect_id 로 센다 — 인덱스가 없으면 매 행 풀스캔.
        #    defect_id·fix_for 는 **마이그레이션으로 추가되는 컬럼**이라 SCHEMA 쪽에 두면
        #    새 DB 생성이 통째로 죽는다(no such column). 반드시 여기에 둔다.
        "CREATE INDEX IF NOT EXISTS idx_photo_defect ON photos(defect_id, fix_for)",
    #  같은 보험사가 같은 열쇠로 두 번 접수하는 것을 **DB 가** 막는다.
    #  (NULL 은 여러 개 허용되므로 열쇠를 안 보낸 접수에는 영향이 없다)
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_cases_idem "
    "  ON cases(insurer_id, idem_key) WHERE idem_key IS NOT NULL",
        # ── 매 화면이 때리는 핵심 조회 경로 ────────────────────
        #  인덱스가 정작 cases·bids·settlements 에는 없어서, 보험사 1곳만 실운영에 들어가도
        #  월 정산 명세서·운영 KPI·협력사 실적 재계산이 전부 풀스캔이 된다.
        #  ⚠ created_at 단독 인덱스는 넣지 않는다 — 조회가 date()/strftime() 으로 감싸므로
        #    인덱스를 만들어도 타지 못한다(있어도 안 쓰는 인덱스는 쓰기만 느리게 한다).
        "CREATE INDEX IF NOT EXISTS idx_cases_partner ON cases(partner_id)",
        "CREATE INDEX IF NOT EXISTS idx_cases_insurer ON cases(insurer_id)",
        "CREATE INDEX IF NOT EXISTS idx_bids_auction ON bids(auction_id)",
        "CREATE INDEX IF NOT EXISTS idx_bids_partner ON bids(partner_id)",
        #  ⚠ [라운드424] 애플리케이션(api_partner_bid·api_partner_reauction_bid)은
        #    이미 BEGIN IMMEDIATE 안에서 "voided_at IS NULL인 기존 입찰이 있으면
        #    UPDATE, 없으면 INSERT"로 파트너당 활성 입찰 1건을 지킨다 — 이 인덱스는
        #    그 규율을 어기는 새 코드가 생기더라도 DB 자체가 중복을 거부하게 하는
        #    마지막 안전망이다(idx_cases_idem과 같은 부분 UNIQUE 인덱스 패턴).
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_bids_active_partner "
        "  ON bids(auction_id, partner_id) WHERE voided_at IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_settle_case ON settlements(case_id)",
        "CREATE INDEX IF NOT EXISTS idx_settle_insurer ON settlements(insurer_id)",
        "CREATE INDEX IF NOT EXISTS idx_worklots_case ON work_lots(case_id)",
        "CREATE INDEX IF NOT EXISTS idx_auctions_case ON auctions(case_id)",
        # 정체(체류시간) 정렬용 — 경보 패널·사건 목록이 이 순서로 읽는다
        "CREATE INDEX IF NOT EXISTS idx_cases_status_at ON cases(status, status_at)",
        #  ⚠ 로그인마다(성공·실패 불문) 이 표를 찌른다(_recent_fails). 기존 인덱스는
        #    (username, created_at)까지만이라, 같은 아이디를 여러 IP로 두드리는
        #    분산 공격 상황(이 표가 막아야 할 바로 그 상황)에서 ip=? 필터가 인덱스
        #    밖에서 걸러져 매칭행 수만큼 스캔한다. 실측(5만행, 동일아이디·IP 5천개
        #    분산) 271배 — 정상 사용자는 원래도 빨라 영향 없음.
        "CREATE INDEX IF NOT EXISTS idx_login_lockout "
        "  ON login_attempts(username, ip, created_at)",
        #  ⚠ 콘솔 벨이 주기적으로 물어보는 자리(api_admin_notifications) — 기존
        #    인덱스(audience_type, read_at)는 'ORDER BY id DESC LIMIT 60'을 못 태워
        #    매칭 전체를 모아 정렬한다. id 를 넣으면 LIMIT 을 인덱스 순서로 바로
        #    끊을 수 있다. 실측(4만행) 582배.
        "CREATE INDEX IF NOT EXISTS idx_notif_admin_feed "
        "  ON notifications(audience_type, id)",
        #  ⚠ [라운드70] 연락처 일괄등록(api_contact_import)이 행마다 이 두 컬럼으로
        #    조회한다 — 인덱스가 없어 행마다 partners 전체를 훑었다.
        "CREATE INDEX IF NOT EXISTS idx_partner_bizno ON partners(biz_no)",
        "CREATE INDEX IF NOT EXISTS idx_partner_name ON partners(name)",
    ):
        try:
            conn.execute(idx_sql)
        except sqlite3.OperationalError:
            pass
    conn.commit()

    # status_at 백필 — 기존 행은 상태 진입 시각을 모른다. 아는 것 중 가장 가까운 값으로
    #  채우고(완료일 > 낙찰일 > 등록일), 그게 추정값임을 화면이 알 수 있게 created_at 을 쓴다.
    #  ⚠ 한 번만 채운다(NULL 인 행만). 이후에는 상태를 바꾸는 코드가 갱신한다.
    #  ⚠⚠ [라운드277] 여기부터 함수 끝까지 모든 except 에 rollback 을 더했다. 실측: 없으면
    #    실패한 블록에서 이미 실행됐던(커밋 전) 문장이 다음 블록의 트랜잭션에 얹혀,
    #    다음 블록이 성공하면 "우연히" 같이 커밋되고(자가치유) 다음 블록들마저 전부
    #    실패하면 close() 에서 통째로 사라진다 — job_locks 행이 그렇게 조용히 유실되면
    #    _sweep_claim() 이 기댈 행이 없어 경매 마감이 예외도 로그도 없이 멈춘다.
    #    여러 문장을 한 커밋에 묶던 블록(구 B4·관리자등급·정산백필)은 문장별로 쪼개
    #    각자 커밋해, 한 문장이 실패해도 앞서 성공한 문장은 그대로 남긴다.
    try:
        conn.execute("""UPDATE cases SET status_at = COALESCE(completed_at, awarded_at, created_at)
                         WHERE status_at IS NULL""")
        conn.commit()
    except sqlite3.OperationalError as e:
        conn.rollback()
        if verbose:
            print(f"  [마이그레이션] status_at 백필 실패: {e}")

    _backfill_sku_keys(conn)
    _backfill_child_is_demo(conn)
    _backfill_track_token_hash(conn, verbose)

    #  ── 발송대기함 정리 (일회성·멱등) ─────────────────────────
    #   웹·인앱·앱푸시는 저장하는 순간 포털 알림함에 뜬다 = 이미 전달된 것인데
    #   과거에는 이것까지 '발송대기'로 적혔다. 그 결과 발송대기함이 1천 건 소음에
    #   묻혀, 정작 사람 손이 필요한 문자·알림톡 수십 건이 안 보였다.
    #   지금 코드는 채널로 갈라 넣지만, 이미 쌓인 행은 여기서 한 번 정리한다.
    try:
        conn.execute("""UPDATE notifications SET status='전달됨'
                         WHERE status='발송대기'
                           AND channel NOT IN ('알림톡','문자')""")
        conn.commit()
    except sqlite3.OperationalError as e:
        conn.rollback()
        if verbose:
            print(f"  [마이그레이션] 발송대기함 정리 실패: {e}")

    # ── B4 마감 자동화 준비 ────────────────────────────────────
    #  ⚠ [라운드277] job_locks 가 가장 중요하다(없으면 마감 점검이 조용히 멈춘다) — 설정값·
    #    auctions.deadline 백필과 커밋을 분리해, 그쪽이 실패해도 이 행들은 반드시 남긴다.
    try:
        # 리스 초기행. 없으면 조건부 UPDATE 의 rowcount 가 영원히 0 이라
        # 마감 점검이 **예외도 로그도 없이** 아무 것도 안 하게 된다.
        conn.execute("INSERT OR IGNORE INTO job_locks(name,lease_until,last_run_at,last_note) "
                     "VALUES('auction_sweep','1970-01-01 00:00:00',NULL,NULL)")
        # 출동 수배도 시간이 지나면 자동으로 정리돼야 한다(30분 내 미도착 → 재수배).
        conn.execute("INSERT OR IGNORE INTO job_locks(name,lease_until,last_run_at,last_note) "
                     "VALUES('dispatch_sweep','1970-01-01 00:00:00',NULL,NULL)")
        #  ⚠ **예약 실행(cron)이 실제로 도는지**를 재는 행. 이게 없으면 화면이
        #    auction_sweep 으로 대신 읽는데, 그 값은 누가 포털을 열기만 해도 갱신된다
        #    (_sweep_if_due). 그래서 cron 이 한 번도 안 돌아도 배지가 영원히 초록이었고,
        #    승인 독촉·출동 기한·알림 발송이 통째로 죽어 있어도 아무도 몰랐다.
        #    last_run_at 을 NULL 로 둬서, 예약이 한 번 돌기 전까지는 '실행된 적 없음'으로 보인다.
        conn.execute("INSERT OR IGNORE INTO job_locks(name,lease_until,last_run_at,last_note) "
                     "VALUES('cli_sweep','1970-01-01 00:00:00',NULL,NULL)")
        conn.commit()
    except sqlite3.OperationalError as e:
        conn.rollback()
        if verbose:
            print(f"  [마이그레이션] job_locks 초기행 실패: {e}")

    try:
        # 새 설정값은 시드가 아니라 여기서 넣는다. 시드는 새 DB 를 만들 때만 도는데,
        # 이미 돌고 있는 DB 에도 설정 화면에 값이 보여야 하기 때문이다.
        # (없어도 코드는 기본값으로 동작하지만, 화면에 빈칸이 보이면 운영자가 헷갈린다)
        for k, v in (("auction_hours", "48"), ("reauction_hours", "24"),
                     # 출동 제한시간(분) — 수락 후 이 시간 안에 도착 보고가 없으면
                     # 자동으로 실패 처리하고 다음 회차 수배를 연다.
                     ("dispatch_minutes", "30"),
                     # 한 회차에 동시에 부를 업체 수 상한(너무 많이 부르면 헛걸음이 늘고,
                     # 너무 적으면 아무도 안 잡아 수배가 지연된다)
                     ("dispatch_fanout", "20"),
                     # 재수배 최대 회차 — 이 회차를 넘기면 사람이 개입해야 한다
                     ("dispatch_max_round", "3"),
                     #  ⚠⚠ [라운드246] 이 둘이 이 백필에 빠져 있었다 — 설정 화면의
                     #    <select> 는 키가 없으면(String(undefined)가 어떤 옵션과도
                     #    안 맞아) 첫 옵션('15분 간격')을 조용히 선택된 것처럼
                     #    보여준다. 실제 서버 기본값(app.py _remind_minutes 의
                     #    default=30)은 30분인데, 화면을 열고 다른 설정만 고쳐
                     #    저장해도(다른 필드처럼 매번 전체를 다시 보낸다) 이 '15분'이
                     #    그대로 DB 에 박혀 리마인드 주기가 조용히 반토막났다.
                     ("reminder_photo", "30분 간격"),
                     ("reminder_payment", "30분 간격")):
            conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        conn.commit()
    except sqlite3.OperationalError as e:
        conn.rollback()
        if verbose:
            print(f"  [마이그레이션] 설정값 기본 백필 실패: {e}")

    try:
        # 레거시 백필 — 지금까지 auctions INSERT 2곳 모두 deadline 을 안 넣어 전 행이 NULL 이다.
        #  NULL 은 `deadline <= now` 비교에서 항상 거짓이라, 백필하지 않으면 그 공고들은
        #  영원히 안 닫힌다(증상이 '아무 일도 안 일어남'이라 발견이 늦다).
        #  ⚠ created_at+48h 로만 채우면 옛 행이 전부 즉시 과거가 되어 첫 점검에서 무더기로
        #    마감된다. 최소 24시간 유예를 준다.
        conn.execute(
            "UPDATE auctions SET deadline = MAX(datetime(created_at,'+48 hours'), "
            "                                   datetime('now','+9 hours','+24 hours')) "
            " WHERE deadline IS NULL AND status='진행'")
        conn.commit()
    except sqlite3.OperationalError as e:
        conn.rollback()
        if verbose:
            print(f"  [마이그레이션] auctions.deadline 백필 실패: {e}")

    # ── 관리자 등급 정규화 ─────────────────────────────────────
    #  3등급(최고/중간/하위)으로 통일하기 전의 구 역할명을 매핑한다.
    #  '운영관리자'→중간, 그 외 미지 역할은 안전하게 하위로.
    try:
        conn.execute("UPDATE admins SET role='중간관리자' "
                     "WHERE role IN ('운영관리자','staff','관리자')")
        conn.commit()
    except sqlite3.OperationalError as e:
        conn.rollback()
        if verbose:
            print(f"  [마이그레이션] 관리자 등급 정규화(중간관리자) 실패: {e}")

    try:
        conn.execute("UPDATE admins SET role='하위관리자' "
                     "WHERE role NOT IN ('최고관리자','중간관리자','하위관리자')")
        conn.commit()
    except sqlite3.OperationalError as e:
        conn.rollback()
        if verbose:
            print(f"  [마이그레이션] 관리자 등급 정규화(하위관리자) 실패: {e}")

    # ── 데이터 백필 : 구 REAL fee_rate → 정수 bp ──────────────────
    #  ⚠ 함정: `ALTER TABLE ... ADD COLUMN fee_rate_bp INTEGER DEFAULT 1000` 은
    #     **기존 모든 행이 1000 을 읽게** 만든다(NULL/0 이 아님). 그래서 예전의
    #     `(fee_rate_bp IS NULL OR =0)` 조건은 **한 행도 안 걸려** 환산이 통째로 죽었고,
    #     9% 공제조합이 조용히 10%(1000bp)로 청구되는 요율 원복이 발생했다.
    #  올바른 판별 = **fee_rate(구 컬럼)가 남아 있는가**.
    #     운영자가 화면/CLI 로 요율을 바꾸면 항상 `fee_rate=NULL` 로 비운다
    #     (api_insurer_update·manage set-fee). 즉 fee_rate 가 NOT NULL 인 행은
    #     '사람이 손대지 않은 레거시/시드 행'뿐이다 → 그 값으로 bp 를 확정하고 비운다.
    #     환산 후 fee_rate 가 NULL 이 되므로 재기동해도 다시 걸리지 않는다(멱등).
    #     운영자 지정 행(fee_rate NULL)은 절대 건드리지 않아 조용한 원복이 없다.
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(insurers)")}
        if {"fee_rate", "fee_rate_bp"} <= cols:
            cur = conn.execute(
                "UPDATE insurers SET fee_rate_bp = CAST(ROUND(fee_rate * 100) AS INTEGER), "
                "                    fee_rate = NULL "
                "WHERE fee_rate IS NOT NULL AND fee_rate > 0")
            if cur.rowcount:
                conn.commit()
                if verbose:
                    print(f"  [마이그레이션] 보험사 수수료율 {cur.rowcount}건을 bp 단위로 환산")
    except sqlite3.Error as e:
        conn.rollback()
        if verbose:
            print(f"  [마이그레이션] 보험사 수수료율 bp 환산 실패: {e}")

    # 기존 정산 행에 partner_id·insurer_id 를 이름으로 한 번만 채워 넣는다.
    # (이름이 유일할 때만 매칭 — 동명이 있으면 사람이 확인해야 하므로 비워 둔다)
    try:
        _settle_cols = {r["name"] for r in conn.execute("PRAGMA table_info(settlements)")}
    except sqlite3.Error:
        _settle_cols = set()
    if {"partner_id", "insurer_id"} <= _settle_cols:
        try:
            conn.execute("""
                UPDATE settlements SET partner_id = (
                    SELECT p.id FROM partners p WHERE p.name = settlements.partner_name
                     AND (SELECT COUNT(*) FROM partners q WHERE q.name = settlements.partner_name) = 1)
                 WHERE partner_id IS NULL AND partner_name IS NOT NULL""")
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            if verbose:
                print(f"  [마이그레이션] 정산 partner_id 백필 실패: {e}")

        try:
            conn.execute("""
                UPDATE settlements SET insurer_id = (
                    SELECT i.id FROM insurers i WHERE i.name = settlements.insurer
                     AND (SELECT COUNT(*) FROM insurers j WHERE j.name = settlements.insurer) = 1)
                 WHERE insurer_id IS NULL AND insurer IS NOT NULL""")
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            if verbose:
                print(f"  [마이그레이션] 정산 insurer_id 백필 실패: {e}")
    return applied


#  ── 자식표의 데모 표식 — **사건에서 물려받는다** ──────────────────
#   ⚠⚠ 화면·집계 23곳이 `bids.is_demo` · `dispatches.is_demo` ·
#     `field_agreements.is_demo` · `notifications.is_demo` 를 보고 데모를 거른다.
#     그런데 그 표식을 **채우는 코드가 어디에도 없었다**(시드 전용 코드 하나뿐).
#     전 행이 0 이니 그 조건들은 언제나 참 — 23곳 전부가 아무것도 못 걸렀다.
#     실측(2026-08-18): 발주처 포털 승인 대기 2건이 둘 다 데모 사건이었고,
#     협력사 '누적 제출' 이 78건(실제 76)으로, 운영 KPI 의 출동 지표는 100% 데모였다.
#   → 표식을 **채우는 쪽**을 고친다. 읽는 23곳을 각각 고치면 새로 쓰는 질의가
#     같은 실수를 반복한다. 기동할 때마다 도므로 놓친 행도 다음 기동에 메워진다.
#   ⚠ 되돌리지 않는다(1 → 0 으로는 안 바꾼다). 사람이 손으로 데모 표시한 것을
#     지워 버리면 안 된다 — 채우기만 한다.
_CHILD_DEMO_SQL = (
    ("bids",
     """UPDATE bids SET is_demo=1
         WHERE COALESCE(is_demo,0)=0 AND auction_id IN (
               SELECT a.id FROM auctions a JOIN cases c ON c.id=a.case_id
                WHERE COALESCE(c.is_demo,0)=1)"""),
    ("dispatches",
     """UPDATE dispatches SET is_demo=1
         WHERE COALESCE(is_demo,0)=0 AND case_id IN (
               SELECT id FROM cases WHERE COALESCE(is_demo,0)=1)"""),
    ("field_agreements",
     """UPDATE field_agreements SET is_demo=1
         WHERE COALESCE(is_demo,0)=0 AND case_id IN (
               SELECT id FROM cases WHERE COALESCE(is_demo,0)=1)"""),
    ("notifications",
     """UPDATE notifications SET is_demo=1
         WHERE COALESCE(is_demo,0)=0 AND case_id IN (
               SELECT id FROM cases WHERE COALESCE(is_demo,0)=1)"""),
    #  ⚠⚠ [라운드96] 정확히 같은 사고가 여기 하나 더 있었다 — settlements 는
    #    바로 위 넷과 나란히 자기 is_demo 컬럼도 있고(db.py DEMO_TABLES 목록에도
    #    있다) case_id 로 사건에 묶여 있는데, 유일한 생성 지점(api_case_approve,
    #    app.py INSERT INTO settlements)이 이 컬럼을 아예 안 채운다 — 그래서 여태
    #    이 넷과 똑같이 "채우는 코드가 없어 전 행이 0" 이었다. settlements 는
    #    보험사가 직접 내려받는 정산 명세서(_insurer_statement)의 원본이라
    #    넷 중 어느 것보다 재무적으로 더 무겁다.
    ("settlements",
     """UPDATE settlements SET is_demo=1
         WHERE COALESCE(is_demo,0)=0 AND case_id IN (
               SELECT id FROM cases WHERE COALESCE(is_demo,0)=1)"""),
    #  ⚠⚠ [라운드100] 위 다섯과 똑같은 사고가 두 표 더 있었다 — defects·happy_calls
    #    모두 자기 is_demo 컬럼이 있고 읽는 쪽(보험사 대시보드 하자 배지·해피콜
    #    평균·partner_rating)은 이미 이 컬럼으로 데모를 거르는데, 채우는 코드가
    #    어디에도 없어(INSERT 문 컬럼 목록에 없음) 그 필터가 항상 전 행을 통과시켰다.
    ("defects",
     """UPDATE defects SET is_demo=1
         WHERE COALESCE(is_demo,0)=0 AND case_id IN (
               SELECT id FROM cases WHERE COALESCE(is_demo,0)=1)"""),
    ("happy_calls",
     """UPDATE happy_calls SET is_demo=1
         WHERE COALESCE(is_demo,0)=0 AND case_id IN (
               SELECT id FROM cases WHERE COALESCE(is_demo,0)=1)"""),
    #  ⚠⚠ [라운드116] 위 여섯과 똑같은 사고가 또 있었다 — auctions 도 자기
    #    is_demo 컬럼이 있고 DEMO_TABLES 목록에도 있어 "덮인 것처럼" 보이는데,
    #    유일한 생성 지점 셋(app.py 의 INSERT INTO auctions) 중 어느 것도 이
    #    컬럼을 안 채웠다. 자식인 bids 는 이 목록 맨 위에서 auctions 를 JOIN해
    #    사건까지 거슬러 가므로 정상 백필됐는데, auctions 자신은 두 번의 전수
    #    점검(96·100라운드)을 전부 통과해 놓쳤다. go-live 미리보기(_demo_counts)
    #    가 삭제 대상 auctions 를 실제보다 적게(0건) 보여준 원인이 이것이다.
    ("auctions",
     """UPDATE auctions SET is_demo=1
         WHERE COALESCE(is_demo,0)=0 AND case_id IN (
               SELECT id FROM cases WHERE COALESCE(is_demo,0)=1)"""),
    #  ⚠⚠ [라운드122] 위 일곱과 똑같은 사고가 또 있었다 — schedule_events 도 자기
    #    is_demo 컬럼이 있고 캘린더 조회(app.py)가 이 컬럼으로 데모를 거르는데,
    #    유일한 생성 지점(api_schedule_event_add)이 이 컬럼을 안 채운다. case_id 가
    #    없는(사건과 무관한 일반 일정) 행은 이 UPDATE 의 IN() 에 안 걸려 그대로
    #    is_demo=0 으로 남는다 — 의도된 동작이다(데모가 아니므로).
    ("schedule_events",
     """UPDATE schedule_events SET is_demo=1
         WHERE COALESCE(is_demo,0)=0 AND case_id IN (
               SELECT id FROM cases WHERE COALESCE(is_demo,0)=1)"""),
)


def _backfill_track_token_hash(conn, verbose=False):
    """진행조회 토큰의 한 방향 해시를 채운다 — 원문이 아직 있는 행만.

    ⚠⚠ [라운드295] track_page() 가 원문 track_token 으로만 이 행을 찾다 보니,
    개인정보 파기(manage.py cmd_prune_personal 버킷④)가 그 값을 NULL 로
    지우는 순간부터 이 행 자체를 다시는 못 찾는다 — "링크가 만료됐습니다"
    (track_expired.html, 410)를 보여줘야 할 자리에 "그런 페이지가 없습니다"
    (404)가 영원히 나갔다. 실측: TRACK_LINK_DAYS(기본 180일)보다 짧은
    BOKGUON_VICTIM_KEEP_DAYS(기본 90일)에 파기되는 취소·미수선종결·유찰
    사건에서 재현 — 90~180일 사이는 물론, 그 뒤로도 영원히 404 만 나간다.
    해시는 원문을 복원할 수 없는 일방향값이라 그 자체로 개인정보가 아니고
    "이 토큰이 예전에 발급된 적이 있는가"만 답한다 — 파기 때도 지우지
    않는다(app.py의 track_page()가 원문이 NULL 인데 해시만 있으면
    무조건 410 을 보여주도록 판정한다). 이미 발급된 기존 행만 한 번
    채운다 — 이후 신규 발급은 issue_track_link() 이 발급 시점에 직접 채운다.
    """
    try:
        rows_ = conn.execute(
            "SELECT id, track_token FROM cases "
            " WHERE track_token IS NOT NULL AND track_token_hash IS NULL").fetchall()
    except sqlite3.OperationalError:
        return
    n = failed = 0
    for r in rows_:
        #  ⚠⚠ [라운드321] 형제 두 함수(_backfill_sku_keys 의 행별 UPDATE,
        #    _backfill_child_is_demo 의 표별 UPDATE)는 전부 이 자리를
        #    try/except sqlite3.OperationalError 로 감싸는데 이 함수만
        #    무방비였다 — DEPLOY.md 의 실제 배포절차(327~337행)가 서비스
        #    재시작 **전에** manage.py migrate 를 먼저 돌리므로, 살아있는
        #    서비스가 쓰기 잠금을 쥔 순간과 겹치면 "database is locked"가
        #    여기서 그대로 새어나가 migrate()→init_db()→app.py 모듈
        #    최상위의 무방비 DB.init_db() 호출까지 뚫려 워커 기동 자체가
        #    죽을 수 있었다(실측: 격리 DB에 실제 쓰기잠금을 쥐게 하고
        #    재현 — OperationalError 가 그대로 전파됨). 이 함수는 이미
        #    멱등(다음 migrate() 가 남은 행을 마저 채운다)이라 개별 행
        #    실패를 건너뛰는 게 안전하다 — 형제와 같은 패턴으로 통일.
        try:
            conn.execute("UPDATE cases SET track_token_hash=? WHERE id=?",
                         (hashlib.sha256(r["track_token"].encode()).hexdigest(), r["id"]))
            n += 1
        except sqlite3.OperationalError:
            failed += 1
    if n:
        conn.commit()
        if verbose:
            print(f"  [마이그레이션] 진행조회 토큰 해시 {n}건 채움")
    if failed and verbose:
        print(f"  [마이그레이션] 진행조회 토큰 해시 {failed}건 실패 — 다음 실행에서 재시도됩니다")


def _backfill_child_is_demo(conn, verbose=False):
    """자식표의 데모 표식을 사건에서 물려받아 채운다. 멱등하다."""
    total = 0
    for table, sql in _CHILD_DEMO_SQL:
        try:
            #  컬럼이 없는 구버전 DB 에서도 죽지 않는다
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if "is_demo" not in cols:
                continue
            total += conn.execute(sql).rowcount or 0
        except sqlite3.OperationalError:
            continue
    if total:
        conn.commit()
        if verbose:
            print(f"  [마이그레이션] 자식표 데모 표식 {total}행 채움")
    return total


def _backfill_sku_keys(conn):
    """standard_boq ↔ 엔진 SKU 자동 매핑 — **확실한 것만** 잇는다.

    엔진 상수는 애초에 이 표에서 시드된 값이라, '이름 유일 일치 + 가격 동일'이면
    같은 항목이라고 봐도 된다. 그 밖의 경우는 잇지 않는다:
      · 가드레일 판 설치비는 지주간격 4m/2m 가 단가가 다른데 표에는 4m 행만 있다
        — 이름만 보고 이으면 2m 키에 4m 단가가 주입된다(틀린 매핑 > 미매핑).
      · 채광판 3T 도 표에는 2T 행만 있다. 이런 키는 내장값 폴백으로 남는 게 맞다.
    운영자가 손으로 넣은 sku_key 는 절대 덮어쓰지 않는다(NULL 인 행만 채운다).
    """
    import re as _re
    try:
        import repair_estimate as _RE     # 순수 모듈(역참조 없음) — 지연 import 로 순환 차단
    except ImportError:
        return
    norm = lambda s: _re.sub(r"\s+", "", (s or ""))
    try:
        rows_ = conn.execute(
            "SELECT id, item, ref_price, sku_key FROM standard_boq "
            " WHERE COALESCE(active,1)=1").fetchall()
    except sqlite3.OperationalError:
        return
    taken = {r["sku_key"] for r in rows_ if r["sku_key"]}
    n = 0
    for key, (name, _spec, _unit, price, _ct, _src) in _RE.SKU.items():
        if key in taken:
            continue
        hits = [r for r in rows_
                if norm(r["item"]) == norm(name) and (r["ref_price"] or 0) == price
                and not r["sku_key"]]
        if len(hits) != 1:
            continue
        try:
            conn.execute("UPDATE standard_boq SET sku_key=? WHERE id=? AND sku_key IS NULL",
                         (key, hits[0]["id"]))
            n += 1
        except sqlite3.OperationalError:
            pass
    if n:
        conn.commit()


def init_db(force=False, seed_demo=None, verbose=False):
    """DB 생성·스키마 반영·마이그레이션. seed_demo=False면 데모 데이터를 넣지 않는다.

    seed_demo 를 지정하지 않으면 환경변수 BOKGUON_SEED_DEMO 를 따르며,
    운영 모드(BOKGUON_ENV=prod)에서는 기본적으로 데모 데이터를 넣지 않는다.
    """
    if force and os.path.exists(DB_PATH):
        for suffix in ("", "-wal", "-shm"):     # WAL 부속 파일까지 함께 제거
            p = DB_PATH + suffix
            if os.path.exists(p):
                os.remove(p)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.executescript(PHOTO_SCHEMA)
    conn.commit()
    migrate(conn, verbose=verbose)

    if seed_demo is None:
        is_prod = os.environ.get("BOKGUON_ENV", "dev").lower() == "prod"
        seed_demo = os.environ.get("BOKGUON_SEED_DEMO", "0" if is_prod else "1") == "1"

    #  ⚠ **`admins==0` 만으로는 '빈 DB' 가 아니다.**
    #    go-live 가 데모 관리자(admin·staff)를 지우면 실운영 DB 도 admins=0 이 된다.
    #    그 상태에서 dev+SEED_DEMO 로 한 번만 들어와도 시드가 돌면서
    #    운영 데이터에 데모 표식이 박히고, 그 다음 go-live 가 실사건을 지운다.
    #    사건이 하나라도 있으면 그 DB 는 이미 쓰이고 있는 DB 다 — 건드리지 않는다.
    _empty = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"] == 0
    if _empty:
        #  ⚠ **`cases==0` 도 '빈 DB' 의 증거가 못 된다.**
        #    go-live 는 사건을 전부 지우고 데모 관리자도 지운다 —
        #    끝나고 나면 admins=0 · cases=0 이 되어 여기 조건에 정확히 들어맞는다.
        #    출시 당일 서버를 한 번 재시작하는 것만으로 방금 비운 운영 DB 에
        #    데모 96건이 되돌아온다. **go-live 가 지우지 않는 증거**를 봐야 한다.
        _used, _why = 0, ""
        for _sql, _msg in (
            ("SELECT COUNT(*) n FROM cases", "사건이 이미 {n}건 있습니다"),
            #  협력업체는 go-live 가 **의도적으로 남긴다**(399개사) — 좋은 증거다
            ("SELECT COUNT(*) n FROM partners", "협력업체가 이미 {n}개사 등록돼 있습니다"),
            #  출시 표식. go-live 가 settings 에 남기고, 무엇을 지워도 지워지지 않는다
            ("SELECT COUNT(*) n FROM settings WHERE key='go_live_at'",
             "이미 실서비스 전환(go-live)을 마친 DB 입니다"),
        ):
            try:
                _n = conn.execute(_sql).fetchone()["n"]
            except sqlite3.Error as e:
                #  ⚠⚠ [라운드585] 조회 실패를 "증거 없음"(_n=0)으로 삼으면 이 게이트가
                #    막으려는 바로 그 사고(운영 DB 재시드)를 오히려 열어준다 — 일시적
                #    쓰기잠금·I/O 오류로 세 신호가 전부 조회 실패하면 _empty 가 그대로
                #    True 로 남는다(실측: admins=0 은 go-live 직후 정상 상태 — 바로 위
                #    주석대로 그 순간마다 이 판정이 돈다). 판정 불가는 "증거 있음"과
                #    동일하게 다뤄 시드를 막는다 — 실패 방향이 비대칭이다: 시드를 한
                #    번 안 하는 쪽은 manage.py create-admin 으로 바로 복구되지만,
                #    잘못 시드해 버리면 실사건·실협력사가 데모로 표시돼 다음 go-live
                #    삭제 대상이 된다.
                _used, _why = 1, f"안전 판정 조회 실패({_sql}) — 확인될 때까지 시드하지 않습니다: {e}"
                break
            if _n:
                _used, _why = _n, _msg.format(n=_n)
                break
        if _used:
            _empty = False
            if verbose:
                print(f"  [시드] {_why} — 시드를 넣지 않습니다.")
                print("         (관리자 계정만 없다면:  python manage.py create-admin <아이디>)")
    if _empty:
        if seed_demo:
            seed(conn)
        else:
            if verbose:
                print("  [시드] 운영 모드 — 데모 데이터를 넣지 않습니다.")
                print("         관리자 계정 생성:  python manage.py create-admin <아이디>")
    conn.close()


def seed(conn):
    #  ★ **표식 범위를 미리 잡아 둔다.** 마지막의 `UPDATE {표} SET is_demo=1` 에
    #    WHERE 가 없어서, 어쩌다 데이터가 있는 DB 에서 이 함수가 돌면
    #    **운영 데이터 전량이 데모로 표시**되고 go-live 가 그걸 지운다.
    #    지금 시점의 최대 id 를 기억해 두고, 그 위(=이 함수가 넣은 행)만 표시한다.
    _base = {}
    for _t in DEMO_TABLES:
        try:
            _base[_t] = conn.execute(f"SELECT COALESCE(MAX(id),0) m FROM {_t}").fetchone()["m"]
        except sqlite3.Error:
            #  ⚠⚠ [라운드585] 여기서 0 을 기본값으로 쓰면 "이 함수가 넣기 전부터 있던
            #    행"의 경계가 사라져, 조회가 실패한 그 표는 바로 아래 표시 루프에서
            #    기존 행까지 전부(id>0) 데모로 표시된다 — 바로 위 주석(★)이 막으려는
            #    사고 그 자체를 이 except 가 되살리는 셈이었다. 기준을 못 구했으면
            #    None 을 남겨 그 표만 표시를 건너뛴다(아래 표시 루프가 스킵) —
            #    안 지워지는 것(표시 누락)이 잘못 지워지는 것(실데이터 오표시)보다 낫다.
            _base[_t] = None
    t = now()
    # --- 관리자 계정 ---
    conn.execute(
        "INSERT INTO admins(username,password_hash,name,role,created_at) VALUES(?,?,?,?,?)",
        ("admin", hash_pw("bokguon2026"), "유경탁", "최고관리자", t),
    )
    conn.execute(
        "INSERT INTO admins(username,password_hash,name,role,created_at) VALUES(?,?,?,?,?)",
        ("staff", hash_pw("staff2026"), "김운영", "중간관리자", t),
    )

    # --- 협력업체 시드 (리서치 162개사) ---
    try:
        with open(SEED_JSON, encoding="utf-8") as f:
            partners = json.load(f)
    except Exception as e:
        #  ⚠⚠ [라운드628] ingest_partners.py 의 round300 주석이 이미 예언한 결함 —
        #    "db.py 쪽은 json.load() 실패를 빈 목록으로 조용히 삼켜, 잘린 파일로
        #    새 DB 를 만들면 협력사 0곳으로 조용히 끝난다"(그때는 쓰는 쪽 원자적
        #    교체만 고치고 읽는 쪽인 여기는 그대로 남겨 뒀다). boq_history()의
        #    round268 과 같은 처방 — 동작(계속 진행)은 그대로 두고 실패 사실만
        #    로그에 남긴다.
        _log.warning("협력업체 시드 파일(%s)을 읽지 못해 0개사로 시작합니다 (%s: %s)",
                     SEED_JSON, type(e).__name__, e)
        partners = []
    if not (isinstance(partners, list) and all(isinstance(p, dict) for p in partners)):
        #  형식은 맞아도(JSON 파싱은 성공) 최상위가 배열이 아니거나 원소가
        #  dict 가 아니면(예: {} · null · ["a","b"]) 옛 코드는 걸러내지 않아
        #  바로 아래 for 루프의 p.get() 이 없는 타입을 만나 여기서 못 잡고
        #  app.py 모듈 최상단의 무방비 DB.init_db() 까지 새어나가 서버 기동
        #  자체가 죽었다(빈 배열·빈 dict 처럼 우연히 안 죽는 모양은 대신
        #  아무 경고 없이 조용히 0곳이 됐다) — 같은 자리에서 형태 전체를
        #  검증해 함께 막는다.
        _log.warning("협력업체 시드 파일(%s)의 형식이 올바르지 않아 0개사로 시작합니다 (최상위 %s)",
                     SEED_JSON, type(partners).__name__)
        partners = []
    import random
    rnd = random.Random(42)
    for p in partners:
        #  ★ **근거 없는 숫자를 만들지 않는다.** 종전에는 난수로 평점·실적을 지어냈다.
        #    이 명부는 데모가 아니라 **실명 리서치 협력사 399곳**이고, 그 난수가
        #    보험사 낙찰 화면에 '평점 4.7 ★' 으로 실적처럼 표시되며
        #    낙찰 점수의 15%를 차지했다(철칙 3·7).
        #    해피콜이 없으면 평점은 없다 — partner_rating() 이 이미 그렇게 판정한다.
        rating = None
        jobs = 0
        win = 0
        doc = rnd.choices(["정상", "정상", "정상", "보험 만료 임박"], k=1)[0]
        ptype = p.get("partner_type") or ("시행사" if (p.get("major", "") or "").startswith("종합") else "시공사")
        conn.execute(
            """INSERT INTO partners(name,partner_type,biz_no,ceo,major,category,region,address,phone,email,website,
               license,rating,jobs_done,win_rate,doc_status,status,source,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                p.get("name", ""), ptype, "", "", p.get("major", ""), p.get("category", ""),
                p.get("region", ""), p.get("address", ""), p.get("phone", ""), "",
                p.get("website", ""), p.get("license", ""), rating, jobs, win, doc, "활성",
                (p.get("source_url", "") or "리서치 수집"), t,
            ),
        )

    # --- 보험사·공제조합 (포털 계정) ---
    insurers = [
        # ※ name 은 cases.insurer 와 정확히 일치해야 사건이 연결된다
        ("○○손보", "손해보험사", "insurer", "bokguon2026", "김보상", "대물보상2팀", "02-1588-0001", "claim@aa.co.kr", 10, "계약중"),
        #  ⚠⚠ [라운드303] login_id/password 가 계속 빈칸이었다 — manage.py 의
        #    DEMO_ACCOUNTS(1632행 부근)는 이미 "insurer"·"insurer2" 둘 다
        #    go-live 가 지울 이름으로 예약해 뒀고 smoke_test.py 도 처음부터
        #    "insurer2" 로 로그인을 시도했는데, 정작 이 자리를 채우는 코드가
        #    없어 그 계정이 한 번도 존재한 적이 없었다 — 타 보험사 접근차단
        #    (IDOR) 회귀 검사가 표준 리허설에서도 매번 로그인 실패로 조용히
        #    비어 있었다.
        ("△△화재", "손해보험사", "insurer2", "bokguon2026", "이대물", "보상기획팀", "02-1588-0002", "claim@bb.co.kr", 10, "시범운영"),
        ("메리츠화재", "손해보험사", None, None, "박담당", "대물보상팀", "02-1588-0003", "", 10, "계약중"),
        ("DB손보", "손해보험사", None, None, "최담당", "대물보상팀", "02-1588-0004", "", 10, "계약중"),
        ("KB손보", "손해보험사", None, None, "정담당", "대물보상팀", "02-1588-0005", "", 10, "계약중"),
        ("□□공제조합", "공제조합", None, None, "한공제", "보상부", "02-1588-0006", "", 9, "계약중"),
    ]
    for nm, ot, lid, pw, mg, dp, ph, em, fr, cs in insurers:
        # ⚠ 시드는 migrate() 이후에 돌아 백필이 닿지 않는다. 요율은 처음부터
        #   **정수 bp 로** 넣고 구 fee_rate 는 **명시적으로 NULL** 로 둔다(9%→900, 10%→1000).
        #   fee_rate 컬럼 DEFAULT 가 10 이라, 안 적으면 10 이 들어가 **다음 기동의 백필이
        #   fee_rate=10→bp=1000 으로 900 을 덮어쓴다(조용한 요율 원복)**. 반드시 NULL 로.
        conn.execute(
            """INSERT INTO insurers(name,org_type,login_id,password_hash,manager,dept,phone,email,
               fee_rate,fee_rate_bp,contract_status,status,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (nm, ot, lid, (hash_pw(pw) if pw else None), mg, dp, ph, em,
             None, int(round(fr * 100)), cs, "활성", t),
        )

    # --- 데모 협력사 계정 (웹 포털 로그인용) ---
    demo = conn.execute(
        "SELECT id FROM partners WHERE partner_type='시행사' ORDER BY id LIMIT 1").fetchone()
    if demo:
        conn.execute(
            "UPDATE partners SET login_id=?, password_hash=? WHERE id=?",
            ("partner", hash_pw("partner2026"), demo["id"]),
        )

    # --- 표준 내역서 (빈도 상위 공종) ---
    boq = [
        ("가드레일·방호울타리", "레일(W빔)", "4M·2겹", "본", 62000),
        ("가드레일·방호울타리", "지주", "Ø139.8", "본", 48000),
        ("가드레일·방호울타리", "반사지·볼트류", "일식", "식", 35000),
        ("유리·샷시·자동문", "강화유리", "12T", "㎡", 88000),
        ("유리·샷시·자동문", "자동문 센서·모터", "표준형", "식", 420000),
        ("누수·배관·설비", "누수탐지", "장비진단", "건", 180000),
        ("누수·배관·설비", "배관 교체", "PVC 100A", "m", 26000),
        ("셔터·차단기·게이트", "주차차단기 바(Bar)", "표준형", "식", 340000),
        ("외벽·석재·담장·조적", "조적(벽돌)", "표준형", "㎡", 72000),
        ("도장·방수·미장", "우레탄 방수", "3회", "㎡", 34000),
    ]
    for major, item, spec, unit, price in boq:
        conn.execute(
            "INSERT INTO standard_boq(major,item,spec,unit,ref_price,created_at) VALUES(?,?,?,?,?,?)",
            (major, item, spec, unit, price, t),
        )

    # --- 사건 시드 ---
    cases = [
        ("26-07160", "○○손보", "복합(유리·샷시·가드레일)", "서울 강서", "화곡로 12", 0, 1, "입찰중", 12400000, 10580000, "김운영"),
        ("26-07158", "△△화재", "간판·전기·가로등", "경기 수원", "권선로 88", 0, 0, "입찰중", 2400000, 2180000, "자동"),
        ("26-07151", "○○손보", "가드레일·방호울타리", "경기 용인", "처인구 42호선", 0, 0, "입찰중", 5400000, 3910000, "자동"),
        ("26-07142", "○○손보", "외벽·석재·담장·조적", "인천 남동", "구월동 1138", 0, 0, "승인대기", 3600000, 2760000, "김운영"),
        ("26-07138", "□□공제", "방음벽·휀스·펜스", "부산 사상", "사상로 55", 0, 0, "시공중", 18200000, 15400000, "자동"),
        ("26-07131", "○○손보", "셔터·차단기·게이트", "광주 서구", "상무대로 30", 1, 0, "완료보고지연", 1200000, 960000, "자동"),
        ("26-07120", "메리츠화재", "유리·샷시·자동문", "서울 송파", "가락동 99", 0, 0, "검수대기", 2100000, 1840000, "김운영"),
        ("26-07098", "DB손보", "가드레일·방호울타리", "충남 천안", "동남구 1", 0, 0, "정산진행", 3800000, 2960000, "자동"),
        ("26-07083", "○○손보", "방음벽·휀스·펜스", "경기 성남", "분당 100", 0, 0, "완료", 17000000, 15400000, "자동"),
        ("26-07071", "□□공제", "조경·수목", "전남 나주", "빛가람 50", 0, 0, "완료", 3600000, 3240000, "자동"),
    ]
    # 낙찰 시행사 (데모) — 완료·정산 단계 사건에 배정
    prime_rows = conn.execute(
        "SELECT id,name FROM partners WHERE partner_type='시행사' ORDER BY id LIMIT 5").fetchall()
    primes = [(r["id"], r["name"]) for r in prime_rows] or [(None, "")]
    ins_map = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM insurers").fetchall()}

    for idx, c in enumerate(cases):
        case_no, insurer, category, region, address, urgent, comp, status, est, low, mgr = c
        pid, pname = (primes[idx % len(primes)] if status in ("시공중", "검수대기", "완료보고지연",
                                                              "정산진행", "완료") else (None, ""))
        # 완료 건은 준공일 기록 (하자보증 기산점)
        done = None
        if status in ("완료", "정산진행"):
            #  [라운드68] naive datetime.now() — 형제(app.py/manage.py)는 67라운드에서
            #  전부 KST 기준으로 고쳤는데 데모 시드만 남아 있었다. 데모 데이터라
            #  화면에만 영향(서버가 KST 아니면 준공일이 최대 9시간 밀려 보인다).
            done = (datetime.now(KST) - timedelta(days=20 + idx * 5)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO cases(case_no,insurer,insurer_id,partner_id,partner_name,completed_at,
               warranty_months,category,region,address,urgent,is_composite,status,est_price,low_price,manager,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (case_no, insurer, ins_map.get(insurer), pid, pname, done, 24,
             category, region, address, urgent, comp, status, est, low, mgr, t),
        )

    # --- 정산 시드 ---
    setts = [
        ("26-07098", "DB손보", "세진안전산업", 2960000, 296000, 2664000, "입금완료", "대기", "대기"),
        ("26-07120", "메리츠화재", "대한글라스텍", 1840000, 184000, 1656000, "대기", "대기", "대기"),
        ("26-07083", "○○손보", "중부금속", 15400000, 1540000, 13860000, "입금완료", "승인", "이체완료"),
        ("26-07071", "□□공제", "호남조경개발", 3240000, 324000, 2916000, "입금완료", "승인", "이체완료"),
    ]
    for s in setts:
        cid = conn.execute("SELECT id FROM cases WHERE case_no=?", (s[0],)).fetchone()
        conn.execute(
            """INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,payout,insurer_paid,review_status,transfer_status,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (cid["id"] if cid else None,) + s + (t,),
        )

    # --- 도입 문의 / 입점 신청 시드 (샘플) ---
    conn.execute(
        """INSERT INTO insurer_leads(company,org_type,name,title,phone,email,interest,message,status,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        ("△△화재", "손해보험사", "이보상", "대물보상팀장", "02-1234-5678", "claim@aa.co.kr",
         "손해율 절감 · 경쟁입찰", "기타피해물 복구 위탁 시범운영을 검토 중입니다. 절감 리포트 샘플 요청.", "신규", t),
    )
    conn.execute(
        """INSERT INTO partner_applications(company,biz_no,ceo,major,category,region,phone,email,has_license,has_insurance,equipment,message,status,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("강원휀스산업", "223-45-67890", "박강원", "방음벽·휀스·펜스", "휀스·방음벽 시공", "강원 전역",
         "033-555-1234", "kw@fence.kr", 1, 1, "크레인 1대·용접기 3대 보유", "강원권 물량 수주 희망합니다.", "신규", t),
    )

    # --- 하자·A/S 시드 ---
    done_cases = conn.execute(
        "SELECT * FROM cases WHERE status IN ('완료','정산진행') ORDER BY id LIMIT 3").fetchall()
    defect_seed = [
        ("가드레일 지주 유격 발생", "준공 3주 후 지주 1본에 흔들림이 발생했습니다. 기초 고정 재시공이 필요합니다.",
         "보통", "접수", None),
        ("도장 부위 들뜸·박리", "복구 도장면 일부가 들뜨고 벗겨졌습니다. 재도장 요청드립니다.",
         "경미", "재시공배정", None),
        ("우천 시 이음부 누수 재발", "복구 완료 부위에서 비가 오면 누수가 다시 발생합니다. 긴급 확인 요청.",
         "중대", "완료", "이음부 실링 전면 재시공 및 방수 보강 완료. 3일간 살수 시험 통과."),
    ]
    for i, dc in enumerate(done_cases):
        if i >= len(defect_seed):
            break
        title, content, sev, st, resolution = defect_seed[i]
        #  [라운드68] naive datetime.now() — 위 completed_at 과 같은 이유로 KST 고정.
        created = (datetime.now(KST) - timedelta(days=12 - i * 4)).strftime("%Y-%m-%d %H:%M:%S")
        due = (datetime.now(KST) + timedelta(days=5 - i * 2)).strftime("%Y-%m-%d")
        conn.execute(
            """INSERT INTO defects(defect_no,case_id,case_no,insurer,insurer_id,partner_id,partner_name,
               category,region,title,content,severity,reporter,reporter_type,status,
               assigned_at,due_date,resolved_at,resolution,cost_bearer,warranty_ok,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"D26-{1001 + i}", dc["id"], dc["case_no"], dc["insurer"], dc["insurer_id"],
             dc["partner_id"], dc["partner_name"], dc["category"], dc["region"],
             title, content, sev, dc["insurer"] + " 보상담당", "보험사", st,
             (created if st != "접수" else None), due,
             (created if st == "완료" else None), resolution, "시행사", 1, created),
        )

    # --- 공지사항 시드 ---
    conn.execute(
        "INSERT INTO notices(title,body,audience,pinned,created_at) VALUES(?,?,?,?,?)",
        ("[필독] 표준 내역서 v1.0 배포 안내", "가드레일·유리·차단기 등 상위 5개 공종의 표준 내역 항목이 확정되었습니다. 입찰 시 반드시 표준 내역 기준으로 단가를 제출해 주세요.", "협력업체", 1, t),
    )
    conn.execute(
        "INSERT INTO notices(title,body,audience,pinned,created_at) VALUES(?,?,?,?,?)",
        ("정산 자동이체 도입 안내", "검수 승인 건은 매일 16:00 일괄 자동이체됩니다. 수수료 10% 공제 후 입금됩니다.", "협력업체", 0, t),
    )

    # --- 알림 로그 시드 ---
    for nt, ch, tg, msg in [
        ("진행알림", "알림톡+푸시", "보험사·피해자·업체", "천안 가드레일 현장 작업이 최종 완료되었습니다"),
        ("사진전송", "알림톡+웹", "DB손보 담당·업체", "검수 완료 — 보험사 API 전송 완료"),
        ("공고오픈", "푸시", "매칭 업체 9곳", "수원 간판 공고 — 대상 업체 호출"),
    ]:
        conn.execute(
            "INSERT INTO notifications(ntype,channel,target,message,status,created_at) VALUES(?,?,?,?,?,?)",
            (nt, ch, tg, msg, "도달", t),
        )

    # --- 설정 ---
    defaults = {
        "fee_rate": "10",
        "min_bidders": "3",
        "low_price_alert": "20",
        "report_deadline_hours": "24",
        "reminder_photo": "30분 간격",
        "reminder_payment": "30분 간격",
        "auction_hours": "48",         # 원경매 입찰 창(시간)
        "reauction_hours": "24",       # 재경매 입찰 창(시간)
    }
    #  ⚠ OR IGNORE 여야 한다. OR REPLACE 로 두면 시드를 다시 돌리는 것만으로
    #    운영자가 조정한 min_bidders·low_price_alert 이 조용히 기본값으로 돌아가고,
    #    B4 이후에는 그게 곧 마감 판정과 저가 경보 기준이 바뀌는 일이 된다.
    for k, v in defaults.items():
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))

    # ── 데모 표식 ──────────────────────────────────────────────
    #  이 함수가 넣은 모든 행에 is_demo=1 을 박는다.
    #  운영 개시(`manage.py go-live`) 때 이 표식만 보고 정확히 지운다.
    #  ⚠ 협력업체(partners)는 실제 영업 자산이라 표시하지 않는다 — 지우면 안 된다.
    for t in DEMO_TABLES:
        if _base.get(t) is None:
            continue  # [라운드585] 시드 전 기준 id 를 못 구한 표 — 표시를 건너뛴다
        try:
            #  ⚠ WHERE 가 반드시 있어야 한다 — 없으면 그 표의 **모든 행**이 데모가 된다.
            conn.execute(f"UPDATE {t} SET is_demo=1 WHERE id > ?", (_base.get(t, 0),))
        except sqlite3.Error:
            pass

    log(conn, "정비도구", "시드 초기화", f"협력업체 {len(partners)}개 · 사건 {len(cases)}건 (데모 표식 적용)")
    conn.commit()


if __name__ == "__main__":
    import sys
    force = "--reset" in sys.argv

    if force:
        # ⚠ --reset 은 DB 파일을 통째로 지운다. 운영 데이터가 들어 있으면 복구가 불가능하다.
        #   실수로 운영 서버에서 실행되는 일을 막기 위해 세 겹으로 잠근다.
        if os.environ.get("BOKGUON_ENV", "dev").lower() == "prod":
            raise SystemExit(
                "\n  운영 모드(BOKGUON_ENV=prod)에서는 --reset 을 쓸 수 없습니다.\n"
                "  스키마만 갱신하려면:  python manage.py migrate\n")
        if os.path.exists(DB_PATH) and "--yes" not in sys.argv:
            conn = get_db()
            counts = {t: conn.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
                      for t in ("partners", "cases", "settlements", "insurer_leads",
                                "partner_applications")}
            conn.close()
            if any(counts.values()):
                print("\n  ⚠ 기존 DB 에 데이터가 있습니다:")
                for k, v in counts.items():
                    if v:
                        print(f"      {k:24s} {v:,}건")
                raise SystemExit(
                    "\n  이 데이터는 --reset 으로 **영구 삭제**됩니다.\n"
                    "  먼저 백업하세요:   python manage.py backup\n"
                    "  그래도 지우려면:   python db.py --reset --yes\n")
        # 지우기 직전 자동 백업 — 되돌릴 마지막 수단
        #  ⚠ shutil.copy2 로 본체만 복사하면 **-wal 에 있는 최근 커밋이 빠진다.**
        #    바로 다음 줄에서 init_db(force=True) 가 -wal 을 지우므로 그 작업들은
        #    사본에도 원본에도 남지 않는다. manage.py backup 은 이미 온라인 백업
        #    API 로 고쳐 뒀는데 여기만 옛 방식이었다.
        if os.path.exists(DB_PATH):
            keep = DB_PATH + datetime.now().strftime(".before_reset_%y%m%d_%H%M%S")
            try:
                _src = sqlite3.connect(DB_PATH)
                _dst = sqlite3.connect(keep)
                with _dst:
                    _src.backup(_dst)      # 잠금을 존중하며 WAL 까지 포함한 일관 스냅샷
                _dst.close(); _src.close()
                print(f"  기존 DB 를 백업했습니다 → {keep}")
            except sqlite3.Error as e:
                raise SystemExit(f"\n  백업에 실패해 초기화를 중단합니다: {e}\n")

    init_db(force=force, verbose=True)
    conn = get_db()
    for tbl in ["admins", "partners", "cases", "settlements", "insurer_leads",
                "partner_applications", "notices", "standard_boq", "notifications"]:
        n = conn.execute(f"SELECT COUNT(*) n FROM {tbl}").fetchone()["n"]
        print(f"  {tbl:24s} {n}")
    conn.close()
    print("DB:", DB_PATH)
