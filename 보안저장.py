# -*- coding: utf-8 -*-
"""보안카드·개인정보를 Windows DPAPI 로 암호화해서 저장.
암호화한 PC, 같은 윈도우 계정에서만 풀림 → 폴더가 통째로 새도 다른 PC 에서는 못 읽음."""
import base64
import ctypes
import ctypes.wintypes as wt
import json
import os

PREFIX = "DPAPI:"
CRYPTPROTECT_UI_FORBIDDEN = 0x1

# 설정.json 에서 암호화해서 저장할 항목
비밀항목 = ("아이디", "비밀번호", "주민번호_앞6", "주민번호_뒤1", "이름", "생년월일", "휴대폰_뒷자리")


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _in(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _out(blob):
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def 잠그기(text: str) -> str:
    if text is None or text == "":
        return ""
    src, _keep = _in(text.encode("utf-8"))
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), "세금계산서", None, None, None,
                                                  CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise OSError("암호화 실패")
    return PREFIX + base64.b64encode(_out(out)).decode("ascii")


class 풀기실패(Exception):
    """다른 PC·다른 계정에서 암호화된 값 → 못 풂"""


def 풀기(value: str) -> str:
    if not value or not str(value).startswith(PREFIX):
        return value or ""  # 아직 암호화 안 된 값(예전 파일)
    raw = base64.b64decode(value[len(PREFIX):])
    src, _keep = _in(raw)
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None,
                                                    CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise 풀기실패("이 컴퓨터에서 저장한 값이 아니에요")
    return _out(out).decode("utf-8")


# ── 설정.json ──
def 설정_읽기(path, 기본):
    """(설정 dict, 못 푼 항목 목록). 평문이 남아 있으면 그 자리에서 암호화해서 다시 저장."""
    s = dict(기본)
    raw = {}
    if os.path.exists(path):
        try:
            raw = json.load(open(path, encoding="utf-8"))
        except Exception:
            raw = {}
    못푼것, 평문있음 = [], False
    for k, v in raw.items():
        if k in 비밀항목:
            if v and not str(v).startswith(PREFIX):
                평문있음 = True
            try:
                s[k] = 풀기(v)
            except 풀기실패:
                s[k] = ""
                못푼것.append(k)
        else:
            s[k] = v
    if "업데이트_토큰" in raw:  # 이제 안 씀 (저장소 공개) → 파일에서도 지움
        평문있음 = True
    s.pop("업데이트_토큰", None)
    if 평문있음 and not 못푼것:
        설정_쓰기(path, s)
    return s, 못푼것


def 설정_쓰기(path, s):
    out = {}
    for k, v in s.items():
        if k == "업데이트_토큰":
            continue
        out[k] = 잠그기(v) if k in 비밀항목 and v else v
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


# ── 보안카드 ──
def 보안카드_파일(here):
    return os.path.join(here, "보안카드.dat")


def 보안카드_읽기(here):
    """{번호: (앞2, 뒤2)} . 예전 평문 보안카드.txt 가 있으면 암호화해서 옮기고 평문은 지움.
    못 풀면 풀기실패, 없으면 {}"""
    import re
    txt = os.path.join(here, "보안카드.txt")
    dat = 보안카드_파일(here)
    if os.path.exists(txt) and not os.path.exists(dat):
        card = {}
        for line in open(txt, encoding="utf-8"):
            m = re.match(r"\s*(\d+)\s*:\s*(\d\d)\s+(\d\d)", line)
            if m:
                card[int(m.group(1))] = (m.group(2), m.group(3))
        if len(card) == 30:
            보안카드_쓰기(here, card)
            os.remove(txt)
            return card
    if not os.path.exists(dat):
        return {}
    data = json.loads(풀기(open(dat, encoding="utf-8").read().strip()))
    return {int(k): tuple(v) for k, v in data.items()}


def 보안카드_쓰기(here, card):
    data = json.dumps({str(k): list(v) for k, v in card.items()})
    open(보안카드_파일(here), "w", encoding="utf-8").write(잠그기(data))
