# -*- coding: utf-8 -*-
"""
340라운드 회귀 — static/admin.js partnerForm() 의 신규 협력사 상태
(select#p_status) 기본값이 배열 첫 항목("활성")에 조용히 의존하던 결함.

  배경: POST /api/partners(app.py:7713-7716, 197라운드가 세운 관문)는
  status 가 "심사중"이 아니면 중간관리자 이상만 허용한다("등록 자체는
  누구나, 즉시 활성화는 중간관리자 이상만" — 7710~7712행 주석). 그런데
  partnerForm() 의 <select id="p_status"> 옵션은 `p.status===s` 로만
  selected 를 매겼다 — 신규 등록(p={}, p.status===undefined)에서는
  네 옵션 중 어느 것도 selected 가 안 붙어, 브라우저가 배열 순서상
  첫 항목("활성")을 화면에 기본 표시한다. 하위관리자가 "+ 업체 등록"을
  열어 화면에 보이는 기본값을 그대로 두고 저장하면 status="활성"이
  전송되어 백엔드가 정확히 의도대로 403을 낸다 — 권한상승은 아니지만,
  자기 등급으로는 애초에 할 수 없는 선택지가 "기본값"으로 미리
  보여지는 결함이다(337·339라운드의 "버튼이 등급 무관하게 그려진다"와는
  다른 하위유형 — 이번엔 "기본 선택값 자체가 등급과 안 맞는다").

  고침: 바로 위 형제 필드 lc_status(1460행)가 이미 쓰는
  `(p.license_status||'미확인')===s` 패턴을 그대로 재사용 — 신규 등록시
  기본값이 백엔드 기본값(심사중)과 일치하게(admin.js 1472행 단일 지점).
  기존 업체 수정(p.status 가 항상 실값)은 동작 변화 없음.

  실행기반 검증: Node vm 으로 partnerForm() 을 직접 실행해 렌더된 HTML의
  <option> selected 위치를 신규/기존(비활성 상태)/기존(활성 상태) 세
  경우 모두 확인한다 — 이 함수를 실제로 실행하는 다른 test_scan_round*.py
  는 없음을 사전 grep 으로 확인(round240·339 둘 다 순수 정적 텍스트
  추출/대조일 뿐 Node 실행이 없다 — 337라운드의 "실행 여부는 반드시
  직접 열어 확인" 습관에 따라 확인한 뒤 이 새 실행 테스트를 추가).
"""
import json
import os
import subprocess
import sys
import tempfile

PASS = 0
FAIL = 0


def chk(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


print("[1] 소스 확인 — partnerForm() 이 lc_status 와 같은 기본값 패턴을 쓰는가")
ADMIN_JS = read("static/admin.js")
i0 = ADMIN_JS.index("function partnerForm(")
i1 = ADMIN_JS.index("\n// 건설업 등록 조사", i0)
pf_src = ADMIN_JS[i0:i1]
chk("(p.status||'심사중')===s" in pf_src,
    "★★★★ p_status select 가 신규 등록 시 심사중을 기본 선택하도록 고쳤다")
chk("p.status===s" not in pf_src,
    "★★★ 옛 무조건부 비교(p.status===s, 배열 첫 항목에 암묵 의존)가 더는 없다")

print("\n[2] 실행 확인 — Node vm 으로 partnerForm() 을 신규/기존 두 경우 다 돌려본다")

NODE_HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const i0 = src.indexOf("function partnerForm(");
const i1 = src.indexOf("\n// 건설업 등록 조사", i0);
const fnSrc = src.slice(i0, i1);

function run(fixture) {
  let captured = null;
  const sandbox = {
    esc: (s) => (s == null ? '' : String(s)),
    openModal: (html) => { captured = html; },
    closeModal: () => {},
    loadAccount: () => {},
    //  [라운드689] round683 이 partnerForm() 안에 loadAccount(id) 와 나란히 넣은
    //    하위 패널 로더. 이 파일의 관심사(select#p_status 기본값)와 무관한 비동기
    //    사이드패널이므로 loadAccount 와 똑같이 빈 스텁으로 둔다. 스텁이 없으면
    //    id 가 참인 경우 partnerForm() 이 ReferenceError
    //    ("loadSubcontractCheck is not defined")로 죽어, 이 파일이 검증하려는
    //    렌더 결과에 애초에 도달하지 못한다(round689 가 실측해 잡음).
    loadSubcontractCheck: () => {},
    myRank: () => 3,
    ALL_MAJORS: ['배관', '전기', '목공'],
    partnerFilter: { ptype: '시공사' },
    window: { _partners: fixture.partners || [] },
  };
  vm.createContext(sandbox);
  vm.runInContext(fnSrc, sandbox);
  vm.runInContext('partnerForm(' + JSON.stringify(fixture.id) + ')', sandbox);
  return captured;
}

function selectedOption(html) {
  const m = html.match(/<select id="p_status">([\s\S]*?)<\/select>/);
  const opts = [...m[1].matchAll(/<option (selected)?>([^<]*)<\/option>/g)];
  return {
    all: opts.map(o => o[2]),
    selected: opts.filter(o => o[1]).map(o => o[2]),
  };
}

const results = {};
results.brandNew = selectedOption(run({ id: 0 }));
results.editWarn = selectedOption(run({ id: 5, partners: [{ id: 5, status: '경고' }] }));
results.editActive = selectedOption(run({ id: 7, partners: [{ id: 7, status: '활성' }] }));
console.log(JSON.stringify(results));
"""

harness_path = None
try:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(NODE_HARNESS)
        harness_path = f.name

    r = subprocess.run(
        ["node", harness_path, "static/admin.js"],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    if r.returncode != 0:
        chk(False, f"★★★★★ Node 실행 실패: {(r.stderr or r.stdout)[:400]}")
    else:
        data = json.loads(r.stdout.strip().splitlines()[-1])
        chk(data["brandNew"]["selected"] == ["심사중"],
            f"★★★★★ 신규 등록(id=0) 기본 선택 = 심사중 (실제: {data['brandNew']['selected']})")
        chk(data["editWarn"]["selected"] == ["경고"],
            f"★★★★ 기존 업체(status=경고) 수정 시 경고가 그대로 선택된다 (실제: {data['editWarn']['selected']})")
        chk(data["editActive"]["selected"] == ["활성"],
            f"★★★★ 기존 업체(status=활성) 수정 시 활성이 그대로 선택된다(등급 있는 관리자의 명시적 선택은 그대로) (실제: {data['editActive']['selected']})")
        chk(data["brandNew"]["all"] == ["활성", "심사중", "경고", "퇴출"],
            "★★ 옵션 목록 자체(순서 포함)는 안 바뀌었다 — 기본 선택 로직만 고쳤다")
except Exception as e:                                              # noqa: BLE001
    chk(False, f"★★★★★ [2] 준비/실행 {type(e).__name__} {e}")
finally:
    if harness_path and os.path.exists(harness_path):
        os.unlink(harness_path)

print(f"\n{'=' * 70}\n  통과 {PASS} · 실패 {FAIL}\n{'=' * 70}")
sys.exit(1 if FAIL else 0)
