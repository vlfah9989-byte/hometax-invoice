# -*- coding: utf-8 -*-
"""
홈택스 자동화
  1) 바탕화면 'Google Chrome' 아이콘 더블클릭
  2) 맨 위 검색창에 '홈택스' 검색 → 맨 위 '홈택스' 클릭
  3) 로그인 → 아이디 로그인 → 로그인 → 2차인증(주민번호 앞 7자리) → 확인
  4) 계산서·영수증·카드 → 전자(세금)계산서 건별발급
  5) 인증선택 창: 간편인증 → 카카오톡 → 이름/생년월일/휴대폰 → 전체동의 → 인증요청
"""
import ctypes
import json
import os
import sys
import time
import subprocess

# ── 화면 배율(125%·150% 노트북 등) 보정: 다른 것보다 먼저 켜야 좌표가 안 어긋남 ──
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 모니터별 배율 인식
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import pyautogui
import pyperclip
import uiautomation as auto
import winocr  # 윈도우 내장 글자인식(한국어) - 예비용

# exe 로 묶었을 때도 같은 폴더의 설정/장부를 쓰도록
_BASE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
# 코드가 "소스코드" 폴더에 있으면 장부·설정·기록은 한 단계 위(프로그램 폴더)에 있는 걸 같이 씀
HERE = os.path.dirname(_BASE) if os.path.basename(_BASE) == "소스코드" else _BASE
설정파일 = os.path.join(HERE, "설정.json")
기본설정 = {  # 실제 값은 같은 폴더의 설정.json 에만 있음 (깃허브에 안 올라감)
    "아이디": "",
    "비밀번호": "",
    "주민번호_앞6": "",
    "주민번호_뒤1": "",
    "이름": "",
    "생년월일": "",
    "휴대폰_뒷자리": "",
    "상호": "",
}


import 보안저장


def 설정_읽기():
    s, 못푼것 = 보안저장.설정_읽기(설정파일, 기본설정)
    s["_못푼것"] = 못푼것
    return s


def 설정_쓰기(s):
    보안저장.설정_쓰기(설정파일, {k: v for k, v in s.items() if not k.startswith("_")})


설정 = 설정_읽기()
주민번호_앞6 = 설정["주민번호_앞6"]
주민번호_뒤1 = 설정["주민번호_뒤1"]
이름 = 설정["이름"]
생년월일 = 설정["생년월일"]
휴대폰_뒷자리 = 설정["휴대폰_뒷자리"]
인증요청_누르기 = True        # False 면 인증요청 직전에 멈춤 (시험용)

pyautogui.FAILSAFE = True  # 마우스를 화면 왼쪽 위 구석으로 밀면 즉시 멈춤
auto.SetGlobalSearchTimeout(1)

CHROME_EXE_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    # 크롬이 없으면 엣지 (크롬과 같은 구조)
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
BROWSER_ICON_NAMES = ("Google Chrome", "Chrome", "크롬", "Microsoft Edge", "Edge")
HOMETAX_URL = "https://www.hometax.go.kr"

SPI_GETSCREENREADER = 0x0046
SPI_SETSCREENREADER = 0x0047


이번에_발급 = []  # 이번 실행에서 발급 완료한 것 (멈췄을 때 안내용)


class 멈춤(Exception):
    pass


def log(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def wait_for(find_fn, timeout, interval=0.5):
    end = time.time() + timeout
    while True:
        r = find_fn()
        if r:
            return r
        if time.time() >= end:
            return None
        time.sleep(interval)


# ── 크롬이 버튼 이름을 알려주게 하는 '화면읽기 모드' 신호 ──
def screen_reader_flag(on):
    ctypes.windll.user32.SystemParametersInfoW(SPI_SETSCREENREADER, 1 if on else 0, None, 0x2)


def screen_reader_flag_get():
    v = ctypes.c_int(0)
    ctypes.windll.user32.SystemParametersInfoW(SPI_GETSCREENREADER, 0, ctypes.byref(v), 0)
    return bool(v.value)


def capslock_끄기():
    """Caps Lock 이 켜져 있으면 영어 대소문자가 뒤집혀 입력됨 → 끔. 껐으면 True"""
    try:
        if ctypes.windll.user32.GetKeyState(0x14) & 1:
            pyautogui.press("capslock")
            time.sleep(0.2)
            return True
    except Exception:
        pass
    return False


# ── 도는 동안 절전·화면꺼짐 막기 ──
def 절전_막기(on):
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED if on else 0)
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


def 팝업_차단됐나():
    """크롬 주소창 오른쪽의 '팝업 차단됨' 표시가 있으면 True"""
    for w in chrome_windows():
        if "홈택스" not in w.Name:
            continue
        try:
            for c, _ in auto.WalkControl(w, maxDepth=12):
                n = c.Name or ""
                if c.ControlTypeName == "ButtonControl" and (("팝업" in n and "차단" in n) or "Pop-up" in n):
                    return True
        except Exception:
            pass
    return False


팝업_안내 = ("인증 창(새 창)이 막혔어요.\n"
         "주소창 오른쪽의 '팝업 차단됨' 아이콘을 눌러 [항상 허용]을 고른 뒤 다시 실행해 주세요.")


# ── 화면 요소 찾기/누르기 ─────────────────────────────
def norm(s):
    s = s or ""
    for ch in " \t\r\n·ㆍ∙•.":
        s = s.replace(ch, "")
    return s


def chrome_windows():
    """크롬(또는 엣지) 창 목록 (맨 앞에 있는 창부터)"""
    out = []
    try:
        for c in auto.GetRootControl().GetChildren():
            n = (c.Name or "").replace("​", "")
            if c.ClassName == "Chrome_WidgetWin_1" and (n.endswith("Chrome") or n.endswith("Edge")):
                out.append(c)
    except Exception:
        pass
    return out


def com_safe(default=None, tries=4):
    """화면이 바뀌는 순간 요소를 읽다가 나는 오류(COMError)면 잠깐 쉬고 다시 시도"""
    import _ctypes
    import functools

    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **k):
            for i in range(tries):
                try:
                    return fn(*a, **k)
                except (_ctypes.COMError, LookupError, AttributeError):
                    time.sleep(0.5)
            return default
        return wrap
    return deco


@com_safe()
def find_in(win, name, types=None, exact=True, startswith=False):
    target = norm(name)
    for c, _ in auto.WalkControl(win, maxDepth=60):
        if types and c.ControlTypeName not in types:
            continue
        n = norm(c.Name)
        if not n:
            continue
        ok = (n == target) if exact else (n.startswith(target) if startswith else target in n)
        if not ok:
            continue
        r = c.BoundingRectangle
        if r.width() <= 0 or r.height() <= 0:
            continue
        return c
    return None


def find(name, types=None, exact=True, startswith=False, timeout=15, win_key=None):
    def _f():
        for w in chrome_windows():
            if win_key and win_key not in w.Name:
                continue
            c = find_in(w, name, types, exact, startswith)
            if c:
                return c
        return None
    return wait_for(_f, timeout, interval=0.7)


def _visible_area(ctrl):
    """버튼이 들어있는 크롬 창의 웹페이지 부분(화면 좌표)"""
    sw, sh = pyautogui.size()
    cands = []
    try:
        top = _top_ctrl(ctrl)
        doc = top.DocumentControl(searchDepth=15)
        if doc.Exists(0, 0):
            cands.append(doc.BoundingRectangle)
        cands.append(top.BoundingRectangle)
    except Exception:
        pass
    for r in cands:
        if r.width() > 200 and r.height() > 200:
            return auto.Rect(max(r.left, 0), max(r.top, 0), min(r.right, sw), min(r.bottom, sh - 40))
    return auto.Rect(0, 0, sw, sh - 40)  # 작업표시줄 빼고 화면 전체


def scroll_into_view(ctrl):
    """버튼이 화면 밖(아래/위)에 있으면 마우스 휠로 스크롤해서 보이게 함"""
    try:
        ctrl.GetScrollItemPattern().ScrollIntoView()
        time.sleep(0.3)
    except Exception:
        pass
    last = None
    for _ in range(25):
        area = _visible_area(ctrl)
        r = ctrl.BoundingRectangle
        # 웹페이지 안에 조금이라도 들어와 있고 가운데가 보이면 그대로 누름 (맨 위 작은 '로그인'처럼 끝에 붙은 것도)
        if area.top <= r.ycenter() <= area.bottom and r.bottom > area.top and r.top < area.bottom:
            return
        if last == (r.top, r.bottom):  # 굴려도 안 움직임 → 더 굴려봐야 소용없음
            return
        last = (r.top, r.bottom)
        pyautogui.moveTo(area.xcenter(), area.ycenter(), duration=0.1)
        pyautogui.scroll(-300 if r.ycenter() > area.bottom else 300)  # 아래면 내리고, 위면 올림
        time.sleep(0.4)


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _root_at(x, y):
    u = ctypes.windll.user32
    u.WindowFromPoint.restype = ctypes.c_void_p
    u.GetAncestor.restype = ctypes.c_void_p
    h = u.WindowFromPoint(_POINT(int(x), int(y)))
    return u.GetAncestor(ctypes.c_void_p(h), 2) if h else None  # GA_ROOT


def _top_ctrl(ctrl):
    """ctrl 이 들어 있는 진짜 창 (부모를 따라 올라가서 바탕화면 바로 아래 것).
    GetTopLevelControl() 은 크롬의 숨은 창을 잡는 경우가 있어서 직접 올라감."""
    root = auto.GetRootControl().NativeWindowHandle
    c = ctrl
    for _ in range(80):
        p = c.GetParentControl()
        if p is None or p.NativeWindowHandle == root:
            return c
        c = p
    return c


def _top_handle(ctrl):
    try:
        return _top_ctrl(ctrl).NativeWindowHandle
    except Exception:
        return None


def 맨앞으로(ctrl):
    """ctrl 이 들어있는 창을 맨 앞으로 (다른 창이 가리고 있으면)"""
    try:
        top = _top_ctrl(ctrl)
        top.SetActive()
        time.sleep(0.3)
        if _root_at(*_center(ctrl)) != top.NativeWindowHandle:
            top.SetTopmost(True)   # 잠깐 맨 위로 올렸다가
            time.sleep(0.2)
            top.SetTopmost(False)  # 다시 원래대로 (팝업 창이 뒤로 숨지 않게)
            top.SetActive()
            time.sleep(0.3)
    except Exception:
        pass


def _center(ctrl):
    r = ctrl.BoundingRectangle
    return r.xcenter(), r.ycenter()


def 가림_확인(ctrl, x=None, y=None):
    """(x,y) 자리에 실제로 ctrl 의 창이 보이는지. 가려져 있으면 맨 앞으로 가져오고, 그래도 안 되면 멈춤"""
    if x is None:
        x, y = _center(ctrl)
    want = _top_handle(ctrl)
    if not want:
        return
    for _ in range(3):
        if _root_at(x, y) == want:
            return
        log("다른 창이 가리고 있어서 홈택스를 맨 앞으로 가져옴")
        맨앞으로(ctrl)
    raise 멈춤("다른 창이 홈택스 화면을 가리고 있어서 멈췄어요.\n(엉뚱한 곳을 누르지 않으려고 멈춘 거예요)")


def click(ctrl):
    scroll_into_view(ctrl)
    가림_확인(ctrl)
    r = ctrl.BoundingRectangle
    pyautogui.moveTo(r.xcenter(), r.ycenter(), duration=0.25)
    pyautogui.click()


class _CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("flags", ctypes.c_uint),
                ("hCursor", ctypes.c_void_p), ("x", ctypes.c_long), ("y", ctypes.c_long)]


_HAND = ctypes.windll.user32.LoadCursorW(None, 32649)  # 손가락(검지) 커서


def cursor_is_hand():
    ci = _CURSORINFO()
    ci.cbSize = ctypes.sizeof(_CURSORINFO)
    ctypes.windll.user32.GetCursorInfo(ctypes.byref(ci))
    return ci.hCursor == _HAND


def click_hand(ctrl):
    """버튼 안에서 마우스가 손가락 모양으로 바뀌는 곳을 찾아서 클릭
    (홈택스 카드 버튼은 가운데 그림/글자 위는 안 눌리고 빈 곳을 눌러야 함)"""
    scroll_into_view(ctrl)
    r = ctrl.BoundingRectangle
    cx, cy = r.xcenter(), r.ycenter()
    w, h = r.width(), r.height()
    spots = [
        (cx, r.bottom - 10),            # 아래쪽 빈 곳
        (cx, r.top + 10),               # 위쪽 빈 곳
        (r.left + 15, cy),              # 왼쪽
        (r.right - 15, cy),             # 오른쪽
        (cx - w // 3, r.bottom - 10),
        (cx + w // 3, r.bottom - 10),
        (cx, cy),
    ]
    가림_확인(ctrl)
    for x, y in spots:
        pyautogui.moveTo(x, y, duration=0.15)
        time.sleep(0.25)
        if cursor_is_hand():
            pyautogui.click()
            return True
    pyautogui.moveTo(cx, r.bottom - 10, duration=0.15)  # 그래도 없으면 아래쪽 빈 곳
    pyautogui.click()
    return False


def click_name(name, types=None, exact=True, startswith=False, timeout=15, win_key=None, after=1.0):
    c = find(name, types, exact, startswith, timeout, win_key)
    if not c:
        raise 멈춤(f"'{name}' 버튼을 못 찾았어요.")
    log(f"'{name}' 클릭")
    click(c)
    time.sleep(after)
    return c


def _들어간값(ctrl):
    try:
        return ctrl.GetValuePattern().Value
    except Exception:
        return None


def _맞게들어갔나(ctrl, text):
    v = _들어간값(ctrl)
    if v is None:
        return True  # 값을 못 읽는 칸은 확인 불가 → 통과
    if v and set(v) <= set("•●*·"):  # 비밀번호처럼 가려진 칸은 글자 수로 확인
        return len(v) == len(text)
    a, b = norm(v), norm(text)
    if a == b:
        return True
    d1, d2 = "".join(ch for ch in a if ch.isdigit()), "".join(ch for ch in b if ch.isdigit())
    return bool(d2) and d1 == d2 and len(d2) >= len(b) - 1  # 숫자칸은 콤마·하이픈 자동으로 붙는 것 허용


def type_into(ctrl, text):
    """칸에 입력하고 실제로 들어갔는지 확인.
    키보드 보안 등으로 안 들어가면 → 붙여넣기 → 직접 값 넣기 순서로 다시 시도"""
    for how in ("타자", "붙여넣기", "직접"):
        click(ctrl)
        time.sleep(0.2)
        want = _top_handle(ctrl)
        fg = ctypes.windll.user32.GetForegroundWindow()
        if want and fg != want:
            맨앞으로(ctrl)
            click(ctrl)
            time.sleep(0.2)
            if ctypes.windll.user32.GetForegroundWindow() != want:
                raise 멈춤("홈택스 창이 앞에 없어서 글자를 안 넣고 멈췄어요.\n(다른 창에 잘못 입력하지 않으려고 멈춘 거예요)")
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("backspace")   # 크롬 자동완성으로 들어간 값 지우기
        time.sleep(0.1)
        if how == "타자" and text.isascii():
            pyautogui.write(text, interval=0.05)
        elif how in ("타자", "붙여넣기"):
            pyperclip.copy(text)       # 한글은 처음부터 붙여넣기
            pyautogui.hotkey("ctrl", "v")
            pyperclip.copy("")
        else:
            try:
                ctrl.GetValuePattern().SetValue(text)
            except Exception:
                pass
        time.sleep(0.3)
        if _맞게들어갔나(ctrl, text):
            return
        log(f"입력이 안 들어감 ({how}) → 다른 방법으로 다시")
    raise 멈춤(f"'{ctrl.Name}' 칸에 글자가 안 들어가요. (키보드 보안 프로그램 확인 필요)")


def close_autofill(edit):
    """크롬 자동완성 창(칸 밑에 뜨는 목록)이 다음 칸을 덮지 않게
    입력한 칸 왼쪽의 글자(예: '생년월일')를 한 번 눌러서 닫음"""
    r = edit.BoundingRectangle
    pyautogui.moveTo(r.left - 70, r.ycenter(), duration=0.1)
    pyautogui.click()
    time.sleep(0.4)


def read_value(label):
    e = find(label, ["EditControl"], timeout=3, win_key="인증")
    if not e:
        return None
    try:
        return e.GetValuePattern().Value.strip()
    except Exception:
        return None


def use_open_hometax():
    """이미 켜져 있는 크롬에 홈택스가 있으면 (다른 탭이어도) 그 탭으로 가서 바로 진행"""
    for w in chrome_windows():
        tab = None
        try:
            if "홈택스" in w.Name:
                tab = True  # 지금 보이는 탭이 홈택스
            else:
                for c, _ in auto.WalkControl(w, maxDepth=12):
                    if c.ControlTypeName == "TabItemControl" and "홈택스" in (c.Name or ""):
                        tab = c
                        break
        except Exception:
            continue
        if not tab:
            continue
        log("이미 켜져 있는 홈택스로 바로 진행")
        w.SetActive()
        time.sleep(0.3)
        if tab is not True:
            r = tab.BoundingRectangle
            pyautogui.click(r.xcenter(), r.ycenter())
            time.sleep(1)
        try:
            if not w.IsMaximize():
                pyautogui.hotkey("win", "up")
                time.sleep(0.8)
        except Exception:
            pass
        return True
    return False


# ── 1단계: 바탕화면 크롬 더블클릭 ──────────────────────────
def open_chrome():
    before = {w.NativeWindowHandle for w in chrome_windows()}
    log("바탕화면 보이기")
    pyautogui.hotkey("win", "d")
    time.sleep(1.0)

    desktop_list = auto.ListControl(ClassName="SysListView32", searchDepth=3)
    icon = None
    if desktop_list.Exists(3):
        for item in desktop_list.GetChildren():
            if item.Name.strip() in BROWSER_ICON_NAMES[:3]:  # 크롬 먼저
                icon = item
                break
        if not icon:
            for item in desktop_list.GetChildren():
                if item.Name.strip() in BROWSER_ICON_NAMES[3:]:  # 없으면 엣지
                    icon = item
                    break

    if icon:
        log(f"바탕화면 '{icon.Name}' 아이콘 더블클릭")
        r = icon.BoundingRectangle
        pyautogui.moveTo(r.xcenter(), r.ycenter(), duration=0.3)
        pyautogui.doubleClick()
    else:
        log("바탕화면에서 크롬 아이콘을 못 찾음 → 크롬 직접 실행")
        exe = next((p for p in CHROME_EXE_CANDIDATES if os.path.exists(p)), None)
        if not exe:
            raise 멈춤("크롬이 설치돼 있지 않아요.")
        subprocess.Popen([exe])

    log("크롬 창 뜨기 기다리는 중...")
    win = wait_for(
        lambda: next((w for w in chrome_windows() if w.NativeWindowHandle not in before), None),
        timeout=12,
    )
    if not win:
        # 크롬이 이미 켜져 있으면 새 창 대신 기존 창에 새 탭을 여는 경우가 있음 → 맨 앞 크롬 창 사용
        ws = chrome_windows()
        if not ws:
            raise 멈춤("크롬 창이 안 떴어요.")
        win = ws[0]
        log("새 창 대신 기존 크롬 창을 씀")
    time.sleep(1.5)
    win.SetActive()
    time.sleep(0.3)
    if not win.IsMaximize():
        pyautogui.hotkey("win", "up")  # 전체화면으로 키우기
    time.sleep(0.8)
    return win


# ── 2단계: 검색 → 맨 위 '홈택스' 클릭 ─────────────────────
def search_hometax(win):
    log("맨 위 검색창 클릭")
    bar = win.EditControl(searchDepth=12)
    if bar.Exists(3):
        r = bar.BoundingRectangle
        pyautogui.click(r.xcenter(), r.ycenter())
    else:
        pyautogui.hotkey("ctrl", "l")
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    log("'홈택스' 입력 후 엔터")
    pyperclip.copy("홈택스")
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)
    pyautogui.press("enter")


def find_hometax_title_ocr():
    """예비용: 화면 글자를 읽어서 파란 '홈택스' 제목 찾기"""
    img = pyautogui.screenshot()
    res = winocr.recognize_pil_sync(img, "ko")
    hits = []
    for line in res["lines"]:
        if line["text"].replace(" ", "") != "홈택스":
            continue
        bs = [wd["bounding_rect"] for wd in line["words"]]
        x = int(min(b["x"] for b in bs))
        y = int(min(b["y"] for b in bs))
        w = int(max(b["x"] + b["width"] for b in bs)) - x
        h = int(max(b["y"] + b["height"] for b in bs)) - y
        crop = img.crop((x, y, x + w, y + h)).convert("RGB")
        blue = sum(1 for r, g, b in crop.getdata() if b > 120 and b > r + 40 and b > g + 40)
        hits.append((y, x, w, h, blue >= 5))
    if not hits:
        return None
    hits.sort()
    blue_hits = [hh for hh in hits if hh[4]]
    y, x, w, h, _ = blue_hits[0] if blue_hits else hits[-1]
    return x + w // 2, y + h // 2


def click_first_hometax(win):
    log("검색결과에서 맨 위 '홈택스' 찾는 중...")
    win.SetActive()
    link = wait_for(
        lambda: find_in(win, "홈택스", ["HyperlinkControl"], exact=False, startswith=True),
        timeout=10, interval=1.0,
    )
    if link:
        log("'홈택스' 클릭")
        click(link)
        return
    pos = wait_for(find_hometax_title_ocr, timeout=6, interval=1.5)
    if pos:
        log("'홈택스' 클릭 (글자인식)")
        pyautogui.moveTo(*pos, duration=0.3)
        pyautogui.click()
        return
    # 검색 사이트가 달라서(네이버 등) 못 찾으면 → 홈택스 주소로 바로 이동
    log("검색결과에서 못 찾음 → 홈택스 주소로 바로 이동")
    win.SetActive()
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.3)
    pyperclip.copy(HOMETAX_URL)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.2)
    pyautogui.press("enter")


# ── 3단계: 아이디 로그인 + 2차인증 ──────────────────────
def fill_id_pw():
    """아이디·비밀번호 칸이 비어 있으면 설정.json 값으로 채움 (크롬에 저장된 PC면 그대로 둠)"""
    w = hometax_win()
    id_e = pw_e = None
    for c, _ in auto.WalkControl(w, maxDepth=80):
        try:
            if c.ControlTypeName != "EditControl" or c.BoundingRectangle.width() <= 0:
                continue
            n = c.Name or ""
            if id_e is None and "아이디" in n:
                id_e = c
            elif pw_e is None and "비밀번호" in n:
                pw_e = c
        except Exception:
            continue
    uid, pw = 설정.get("아이디", ""), 설정.get("비밀번호", "")
    if id_e is not None and not (_들어간값(id_e) or "").strip():
        if uid:
            log("아이디 입력 (설정 값)")
            type_into(id_e, uid)
        else:
            log("설정에 아이디가 없어서 크롬에 저장된 값으로 진행")
    if pw_e is not None and not (_들어간값(pw_e) or "") and pw:
        log("비밀번호 입력 (설정 값)")
        type_into(pw_e, pw)


def login():
    log("홈택스 화면 뜨기 기다리는 중...")
    if not find("홈택스", exact=False, timeout=20, win_key="홈택스"):
        raise 멈춤("홈택스 화면이 안 떴어요.")
    time.sleep(1.5)
    scroll_top()  # 아래로 내려가 있으면 '로그아웃'이 안 보임

    if find("로그아웃", ["HyperlinkControl", "ButtonControl"], timeout=2):
        log("이미 로그인돼 있어서 로그인은 건너뜀")
        return

    click_name("로그인", ["HyperlinkControl", "ButtonControl"], after=2.5)
    click_name("아이디 로그인", ["HyperlinkControl", "ButtonControl", "TabItemControl"], after=1.5)
    fill_id_pw()  # 크롬에 저장 안 된 PC면 설정의 아이디·비번 입력
    click_name("로그인", ["ButtonControl"], after=2.5)

    log("2차 인증창 기다리는 중...")
    if not find("아이디 로그인 2차 인증", exact=False, timeout=10):
        raise 멈춤("2차 인증창이 안 떴어요.")
    edits = find_rrn_edits()
    if not edits:
        raise 멈춤("주민등록번호 칸을 못 찾았어요.")
    log("주민등록번호 앞자리 입력")
    type_into(edits[0], 주민번호_앞6)
    type_into(edits[1], 주민번호_뒤1)
    click_name("확인", ["ButtonControl", "HyperlinkControl"], after=3)

    if not find("로그아웃", ["HyperlinkControl", "ButtonControl"], timeout=15):
        raise 멈춤("로그인이 안 됐어요. (2차 인증 확인 필요)")
    log("로그인 완료")


@com_safe()
def find_rrn_edits():
    """2차인증 창의 주민번호 칸 2개 (앞 6자리, 뒤 1자리)"""
    for w in chrome_windows():
        if "홈택스" not in w.Name:
            continue
        edits = []
        for c, _ in auto.WalkControl(w, maxDepth=60):
            if c.ControlTypeName != "EditControl":
                continue
            n = norm(c.Name)
            if "주민" in n or "생년월일" in n or "성별" in n or "뒷자리" in n or "앞자리" in n:
                if c.BoundingRectangle.width() > 0:
                    edits.append(c)
        if len(edits) >= 2:
            edits.sort(key=lambda c: c.BoundingRectangle.left)
            return edits[:2]
    return None


# ── 4단계: 건별발급 메뉴 ──────────────────────────────
def scroll_top():
    """페이지 맨 위로 (메뉴 줄이 보이게)"""
    w = hometax_win()
    w.SetActive()
    a = _visible_area(w)
    pyautogui.moveTo(a.xcenter(), a.ycenter(), duration=0.1)
    for _ in range(15):
        pyautogui.scroll(500)  # 한 번에 너무 크게 굴리면 크롬이 무시함
        time.sleep(0.1)
    time.sleep(0.5)


@com_safe()
def find_top_menu(name):
    """같은 이름이 여러 개면, 지금 화면 위쪽에 보이는 것(맨 위 메뉴줄)을 고름"""
    w = hometax_win()
    a = _visible_area(w)
    best = None
    for c, _ in auto.WalkControl(w, maxDepth=80):
        if norm(name) not in norm(c.Name) or len(norm(c.Name)) > len(norm(name)) + 4:
            continue
        r = c.BoundingRectangle
        if r.width() <= 0 or r.top < a.top or r.bottom > a.top + 400:
            continue
        if best is None or r.top < best.BoundingRectangle.top:
            best = c
    return best


def open_issue_menu():
    scroll_top()
    menu = wait_for(lambda: find_top_menu("계산서ㆍ영수증ㆍ카드"), timeout=10, interval=0.7)
    if not menu:
        raise 멈춤("맨 위 '계산서ㆍ영수증ㆍ카드' 메뉴를 못 찾았어요.")
    log("'계산서ㆍ영수증ㆍ카드' 클릭")
    r = menu.BoundingRectangle
    pyautogui.moveTo(r.xcenter(), r.ycenter(), duration=0.25)  # 스크롤 없이 그 자리 클릭
    pyautogui.click()
    time.sleep(1.5)
    click_name("전자(세금)계산서 건별발급", ["HyperlinkControl", "ButtonControl", "MenuItemControl"],
               exact=False, after=3)


# ── 5단계: 간편인증 (카카오톡) ───────────────────────────
def simple_auth():
    log("인증선택 창 기다리는 중...")
    btn = None
    end = time.time() + 25
    while time.time() < end:
        btn = find("간편 인증", ["ButtonControl", "HyperlinkControl"], timeout=0, win_key="인증")
        if btn:
            break
        if on_issue_screen() or find_dialog_ok():
            log("이미 인증된 상태라서 인증 없이 발급 화면으로 넘어감")
            wait_auth_done(need_auth=False)
            return
        if 팝업_차단됐나():
            raise 멈춤(팝업_안내)
        time.sleep(1)
    if not btn:
        raise 멈춤("인증선택 창이 안 떴어요." + ("\n" + 팝업_안내 if 팝업_차단됐나() else ""))
    time.sleep(2.5)  # 창이 다 준비될 때까지
    kakao = None
    for _ in range(3):  # 안 열리면 다시 누름
        log("'간편 인증' 클릭 (손가락 모양 되는 곳)")
        click_hand(btn)
        kakao = find("카카오톡", ["ButtonControl"], timeout=6, win_key="인증")
        if kakao:
            break
    if not kakao:
        raise 멈춤("'카카오톡' 버튼을 못 찾았어요.")
    kakao_fill_and_request(kakao)


def kakao_fill_and_request(kakao):
    log("'카카오톡' 클릭")
    click_hand(kakao)
    time.sleep(1.5)

    fields = (("이름", 이름), ("생년월일", 생년월일), ("휴대폰 번호", 휴대폰_뒷자리))
    for attempt in range(3):
        for label, value in fields:
            e = find(label, ["EditControl"], timeout=10, win_key="인증")
            if not e:
                raise 멈춤(f"'{label}' 칸을 못 찾았어요.")
            log(f"'{label}' 입력")
            type_into(e, value)
            close_autofill(e)
        wrong = [label for label, value in fields if read_value(label) != value]
        if not wrong:
            break
        log(f"입력이 잘못 들어감 {wrong} → 다시 입력")
    else:
        raise 멈춤("이름/생년월일/휴대폰 번호가 제대로 안 들어가요.")

    chk = find("전체동의", ["CheckBoxControl"], exact=False, timeout=10, win_key="인증")
    if not chk:
        raise 멈춤("'전체동의' 칸을 못 찾았어요.")
    try:
        checked = chk.GetTogglePattern().ToggleState == auto.ToggleState.On
    except Exception:
        checked = False
    if not checked:
        log("'전체동의' 체크")
        click(chk)
        time.sleep(0.8)

    if 인증요청_누르기:
        click_name("인증 요청", ["ButtonControl"], win_key="인증", after=1.0)
        log("카카오톡으로 인증요청 보냈어요. 폰에서 인증해 주세요!")
        wait_auth_done()
    else:
        log("(설정) 인증요청 직전에 멈췄어요.")


# ── 6단계: 인증 완료 후 알림 확인 4번 → 발급 화면 ─────────
@com_safe()
def find_dialog_ok():
    """알림창의 '확인' (같은 줄에 '취소'가 있는 확인만. 화면의 '등록번호 확인'은 제외)"""
    for w in chrome_windows():
        if "홈택스" not in w.Name:
            continue
        oks, cancels = [], []
        for c, _ in auto.WalkControl(w, maxDepth=60):
            if c.ControlTypeName != "ButtonControl":
                continue
            n = (c.Name or "").strip()
            r = c.BoundingRectangle
            if r.width() <= 0:
                continue
            if n == "확인":
                oks.append(c)
            elif n == "취소":
                cancels.append(r)
        for ok in reversed(oks):  # 나중에 뜬(위에 있는) 창부터
            r = ok.BoundingRectangle
            if any(abs(cr.ycenter() - r.ycenter()) < 10 for cr in cancels):
                return ok
    return None


@com_safe()
def on_issue_screen():
    """발급 화면(창 제목과 상관없이 '발급하기' 버튼 + '등록번호' 칸이 보임) + 알림 없음"""
    for w in chrome_windows():
        if "홈택스" not in w.Name:
            continue
        if nth_ctrl(w, "발급하기", ["ButtonControl"]) and nth_ctrl(w, "등록번호", ["EditControl"]):
            return find_dialog_ok() is None
    return False


def 인증창_열림():
    return any("인증" in w.Name and "홈택스" not in w.Name for w in chrome_windows())


def wait_auth_done(timeout=600, need_auth=True):
    if need_auth:
        log("아빠 폰 카톡에서 인증한 다음, 화면의 [인증 완료]를 눌러 주세요. (최대 10분 기다림)")
    else:
        timeout = 60
    end = time.time() + timeout
    clicked = 0
    while time.time() < end:
        ok = find_dialog_ok()
        if ok:
            clicked += 1
            log(f"알림 '확인' 클릭 ({clicked}번째)")
            click(ok)
            time.sleep(3)
            continue
        if (clicked or not need_auth or not 인증창_열림()) and on_issue_screen():
            time.sleep(2)
            if find_dialog_ok() is None:
                log("전자세금계산서 발급 화면 도착!")
                return
        if not clicked and find("공동∙금융 인증", ["ButtonControl"], exact=False, timeout=0, win_key="인증") \
                and not find("인증 완료", ["ButtonControl"], timeout=0, win_key="인증"):
            raise 멈춤("인증이 안 됐어요. (폰 인증 전에 인증 완료를 누르면 처음으로 돌아가요) 다시 실행해 주세요.")
        time.sleep(1.5)
    raise 멈춤("10분 동안 인증이 안 끝났어요.")


# ══════════════════ 세금계산서 발급 ══════════════════
import calendar
import datetime
import re

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
기록파일 = os.path.join(HERE, "발급기록.txt")


def 지난달_말일(today=None):
    today = today or datetime.date.today()
    first = today.replace(day=1)
    return first - datetime.timedelta(days=1)


# ── 한글(.hwp) 거래처 정리 파일 읽기 ──
def hwp_lines(path):
    import olefile
    import struct
    import zlib
    ole = olefile.OleFileIO(path)
    compressed = ole.openstream("FileHeader").read()[36] & 1
    secs = sorted([e for e in ole.listdir() if e[0] == "BodyText"],
                  key=lambda e: int(e[1].replace("Section", "")))
    out = []
    for s in secs:
        data = ole.openstream(s).read()
        if compressed:
            data = zlib.decompress(data, -15)
        i = 0
        while i < len(data):
            hd = struct.unpack_from("<I", data, i)[0]
            tag, size = hd & 0x3FF, (hd >> 20) & 0xFFF
            i += 4
            if size == 0xFFF:
                size = struct.unpack_from("<I", data, i)[0]
                i += 4
            rec = data[i:i + size]
            i += size
            if tag != 67:
                continue
            txt, j = [], 0
            while j < len(rec):
                c = struct.unpack_from("<H", rec, j)[0]
                if c < 32:
                    j += 16 if c in (1, 2, 3, 9, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23) else 2
                    continue
                txt.append(chr(c))
                j += 2
            out.append("".join(txt))
    return out


def 거래처_읽기(path):
    """[번호] 블록 → 거래처 목록. 금액이 여러 개면 비고(괄호 안 글자)별로 따로."""
    items, cur = [], None
    for line in hwp_lines(path):
        line = line.strip()
        m = re.fullmatch(r"\[(\d+)\]", line)
        if m:
            cur = {"번호": int(m.group(1)), "금액들": []}
            items.append(cur)
            continue
        if cur is None or ":" not in line:
            continue
        k, v = [x.strip() for x in line.split(":", 1)]
        if k.startswith("금액"):
            memo = re.search(r"\((.*?)\)", k)
            cur["금액들"].append((memo.group(1) if memo else "", int(re.sub(r"[^\d]", "", v))))
        else:
            cur[k] = v
    return items


def 발급할_목록(path):
    out = []
    for it in 거래처_읽기(path):
        if not it.get("사업자번호"):
            log(f"[{it['번호']}] {it.get('거래처명', '')} - 사업자번호 없음 → 패스")
            continue
        for memo, amount in it["금액들"]:
            out.append({**it, "비고": memo, "금액": amount})
    return out


def 기록_읽기():
    done = set()
    if os.path.exists(기록파일):
        for line in open(기록파일, encoding="utf-8"):
            if line.startswith("#") or not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) >= 4:
                done.add((p[0], p[1], p[2], p[3]))
    return done


def 기록_쓰기(date, bizno, memo, amount, name, 승인번호):
    with open(기록파일, "a", encoding="utf-8") as f:
        f.write(f"{date}\t{bizno}\t{memo}\t{amount}\t{name}\t{승인번호}\n")


# ── 발급 화면 조작 도구 ──
def hometax_win():
    for w in chrome_windows():
        if "홈택스" in w.Name:
            return w
    raise 멈춤("홈택스 창이 없어요.")


@com_safe()
def nth_ctrl(win, name, types, n=1):
    k = 0
    for c, _ in auto.WalkControl(win, maxDepth=80):
        if c.ControlTypeName in types and norm(c.Name) == norm(name) and c.BoundingRectangle.width() > 0:
            k += 1
            if k == n:
                return c
    return None


def 값(ctrl):
    try:
        return ctrl.GetValuePattern().Value.strip()
    except Exception:
        return ""


def 칸_넣기(name, value, n=1):
    w = hometax_win()
    e = nth_ctrl(w, name, ["EditControl"], n)
    if not e:
        raise 멈춤(f"'{name}' 칸을 못 찾았어요.")
    type_into(e, value)
    pyautogui.press("tab")
    time.sleep(0.6)
    return e


@com_safe(default=[])
def visible_texts(win):
    out = []
    for c, _ in auto.WalkControl(win, maxDepth=80):
        if c.ControlTypeName == "TextControl":
            r = c.BoundingRectangle
            if r.width() > 0 and r.right > 0 and r.top > 0:
                out.append(((c.Name or "").strip(), r))
    return out


def 알림_기다리기(keys, timeout=10, win_key="홈택스"):
    """keys 중 하나가 들어간 알림 글이 보이면 (글, 그 아래 확인버튼, 취소버튼) 반환"""
    end = time.time() + timeout
    while time.time() < end:
        for w in chrome_windows():
            if win_key not in w.Name:
                continue
            for n, r in visible_texts(w):
                if any(k in n for k in keys):
                    ok = cancel = None
                    for c, _ in auto.WalkControl(w, maxDepth=80):
                        if c.ControlTypeName != "ButtonControl":
                            continue
                        cr = c.BoundingRectangle
                        if cr.width() <= 0 or cr.top < r.top or cr.top - r.bottom > 150:
                            continue
                        nm = (c.Name or "").strip()
                        if nm == "확인" and ok is None:
                            ok = c
                        elif nm == "취소" and cancel is None:
                            cancel = c
                    if ok is not None:  # 확인 버튼이 같이 있어야 진짜 알림 (화면 안내 글자 착각 방지)
                        return n, ok, cancel
        time.sleep(0.5)
    return None, None, None


def 작성일자_달력(target):
    w = hometax_win()
    click(nth_ctrl(w, "달력에서 선택", ["ButtonControl"]))
    time.sleep(1.2)
    reopen = 0
    for _ in range(24):
        w = hometax_win()
        yc = nth_ctrl(w, "연도 선택", ["ComboBoxControl"])
        mc = nth_ctrl(w, "달 선택", ["ComboBoxControl"])
        y = int(re.sub(r"\D", "", 값(yc) if yc else "") or 0)
        m = int(re.sub(r"\D", "", 값(mc) if mc else "") or 0)
        if not y or not m:
            reopen += 1
            if reopen > 3:
                raise 멈춤("달력의 연도/달을 못 읽었어요.")
            log("달력이 닫혀 있어서 다시 엶")
            click(nth_ctrl(w, "달력에서 선택", ["ButtonControl"]))
            time.sleep(1.2)
            continue
        if (y, m) == (target.year, target.month):
            break
        btn = "이전 달" if (y, m) > (target.year, target.month) else "다음 달"
        click(nth_ctrl(w, btn, ["ButtonControl"]))
        time.sleep(0.8)
    else:
        raise 멈춤("달력에서 저번 달로 못 넘어갔어요.")
    grid = nth_ctrl(hometax_win(), "달력", ["DataGridControl"])
    cells = [c for c, _ in auto.WalkControl(grid, maxDepth=4)
             if c.ControlTypeName == "DataItemControl" and (c.Name or "").strip() == str(target.day)]
    if not cells:
        raise 멈춤(f"달력에서 {target.day}일을 못 찾았어요.")
    log(f"달력에서 {target.month}월 {target.day}일 클릭")
    click(cells[-1])  # 앞쪽 지난달 날짜 말고 이번 달 말일
    time.sleep(1.0)
    v = 값(nth_ctrl(hometax_win(), "작성일자", ["EditControl"]))
    if re.sub(r"\D", "", v) != target.strftime("%Y%m%d"):
        raise 멈춤(f"작성일자가 이상해요: {v}")


class 건너뜀(Exception):
    """이 거래처만 건너뛰고 다음으로 (등록번호 잘못 등)"""


def clear_bizno():
    """잘못된 등록번호를 지워서 다음 거래처 입력에 안 섞이게"""
    try:
        e = nth_ctrl(hometax_win(), "등록번호", ["EditControl"])
        if e:
            click(e)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("backspace")
            time.sleep(0.3)
    except Exception:
        pass


def 한건_발급(it, date):
    bizno = re.sub(r"\D", "", it["사업자번호"])
    amount = it["금액"]
    supply = int(round(amount / 1.1))
    tax = amount - supply
    name = it.get("거래처명", "")
    log(f"── [{it['번호']}] {name} {it['비고']} {amount:,}원 (공급가액 {supply:,} / 세액 {tax:,})")

    # 1) 등록번호 → 확인 → '정상적인 사업자번호입니다'
    e = 칸_넣기("등록번호", bizno)
    w = hometax_win()
    er = e.BoundingRectangle
    ok_btn = None
    for c, _ in auto.WalkControl(w, maxDepth=80):
        if c.ControlTypeName == "ButtonControl" and (c.Name or "").strip() == "확인":
            r = c.BoundingRectangle
            if abs(r.ycenter() - er.ycenter()) < 10 and r.left >= er.right - 5:
                ok_btn = c
                break
    if not ok_btn:
        raise 멈춤("등록번호 옆 확인 버튼을 못 찾았어요.")
    click(ok_btn)
    msg, ok, _ = 알림_기다리기(["사업자번호입니다", "사업자번호가", "형식으로 입력하세요",
                              "휴업", "폐업", "등록되지 않은", "존재하지 않", "확인할 수 없"], timeout=10)
    if not msg:
        raise 멈춤("등록번호 확인 결과가 안 떠요.")
    log(f"알림: {msg}")
    if ok:
        click(ok)
        time.sleep(1.5)
    if "정상" not in msg:
        # 아버지가 등록번호를 잘못 적은 경우 → 이 거래처는 건너뛰고 다음 것으로
        clear_bizno()
        raise 건너뜀(msg)

    # 2) 상호/성명 (한글 파일의 정식 이름으로 덮어씀), 있는 정보만 추가 입력
    칸_넣기("상호", name, 2)
    if it.get("대표자"):
        칸_넣기("성명", re.sub(r"\s*\(.*\)\s*$", "", it["대표자"]), 2)
    addr = it.get("등록주소") or it.get("주소")
    if addr:
        칸_넣기("사업장", addr, 2)
    for k in ("업태", "종목"):
        if it.get(k):
            칸_넣기(k, it[k], 2)
    if it.get("이메일") and "@" in it["이메일"]:
        id_, dom = it["이메일"].split("@", 1)
        칸_넣기("이메일", id_, 2)
        칸_넣기("이메일 도메인 입력", dom, 2)

    # 3) 작성일자(달력에서 저번 달 말일) / 일 / 품목 / 공급가액 / 비고
    작성일자_달력(date)
    칸_넣기("1행 일", str(date.day))
    칸_넣기("1행 품목", f"{date.month}월식대")
    칸_넣기("1행 공급가액", str(supply))
    if it["비고"]:
        칸_넣기("1행 비고", it["비고"])
    w = hometax_win()
    got_tax = int(re.sub(r"\D", "", 값(nth_ctrl(w, "1행 세액", ["EditControl"]))) or 0)
    if supply + got_tax != amount:
        log(f"세액 {got_tax:,} → {tax:,} 로 고침 (합계 {amount:,} 맞추기)")
        칸_넣기("1행 세액", str(tax))

    # 4) 입력값 다시 읽어서 확인
    w = hometax_win()
    check = {
        "등록번호": (nth_ctrl(w, "등록번호", ["EditControl"]), bizno),
        "작성일자": (nth_ctrl(w, "작성일자", ["EditControl"]), date.strftime("%Y%m%d")),
        "1행 월": (nth_ctrl(w, "1행 월", ["EditControl"]), str(date.month)),
        "1행 일": (nth_ctrl(w, "1행 일", ["EditControl"]), str(date.day)),
        "1행 공급가액": (nth_ctrl(w, "1행 공급가액", ["EditControl"]), str(supply)),
        "1행 세액": (nth_ctrl(w, "1행 세액", ["EditControl"]), str(tax)),
    }
    for k, (c, want) in check.items():
        if re.sub(r"\D", "", 값(c)) != want:
            raise 멈춤(f"'{k}' 값이 이상해요: {값(c)} (원래 {want})")
    if 값(nth_ctrl(w, "1행 품목", ["EditControl"])) != f"{date.month}월식대":
        raise 멈춤("품목 값이 이상해요.")

    # 5) 발급하기 → (이메일 없으면) 계속 발급? 확인 → 발급 확인창
    click(nth_ctrl(w, "발급하기", ["ButtonControl"]))
    end = time.time() + 15
    layer_btn = None
    while time.time() < end:
        msg, ok, cancel = 알림_기다리기(["계속 발급하겠습니까", "발급보류하시겠습니까"], timeout=1)
        if msg and "발급보류" in msg:
            log("발급보류 알림이 떠서 취소 누름 (보류 안 함)")
            if cancel:
                click(cancel)
                time.sleep(1.5)
            continue
        if msg and ok:
            log(f"알림: {msg} → 확인")
            click(ok)
            time.sleep(1.5)
        layer_btn = find("인증 화면 이동", ["ButtonControl"], exact=False, timeout=1, win_key="홈택스")
        if layer_btn:
            break
    if not layer_btn:
        raise 멈춤("발급 확인창이 안 떠요.")

    # 6) 발급 확인창 내용 확인 (등록번호/상호/성명/작성일자/합계금액)
    texts = " ".join(n for n, _ in visible_texts(hometax_win()))
    want = [f"{bizno[:3]}-{bizno[3:5]}-{bizno[5:]}", name, date.strftime("%Y-%m-%d"), f"{amount:,}"]
    missing = [x for x in want if x not in texts]
    if missing:
        raise 멈춤(f"발급 확인창 내용이 달라요: {missing}")
    log("발급 확인창 내용 확인 → 확인(인증 화면 이동)")
    click(layer_btn)
    time.sleep(2.5)

    # 7) 보안카드 인증
    card_btn = find("보안카드 인증", ["ButtonControl"], timeout=10, win_key="홈택스")
    if not card_btn:
        raise 멈춤("'보안카드 인증' 버튼을 못 찾았어요.")
    log("'보안카드 인증' 클릭")
    click_hand(card_btn)
    보안카드_입력()

    # 8) 완료 → 승인번호 읽고 계속발급
    승인번호 = ""
    end = time.time() + 20
    while time.time() < end and not 승인번호:
        for n, _ in visible_texts(hometax_win()):
            m = re.search(r"승인번호\s*:\s*([\d-]+)", n)
            if m:
                승인번호 = m.group(1)
                break
        time.sleep(0.7)
    if not 승인번호:
        raise 멈춤("발급 완료 화면(승인번호)이 안 보여요. 홈택스 발급목록을 확인해 주세요.")
    log(f"발급 완료! 승인번호 {승인번호}")
    기록_쓰기(date.strftime("%Y-%m-%d"), it["사업자번호"], it["비고"], amount, name, 승인번호)
    click_name("계속발급", ["ButtonControl"], win_key="홈택스", after=3)
    return 승인번호


def 보안카드_표():
    try:
        card = 보안저장.보안카드_읽기(HERE)
    except 보안저장.풀기실패:
        raise 멈춤("보안카드를 이 컴퓨터에서 읽을 수 없어요. (다른 컴퓨터에서 저장한 것)\n"
                 "[⚙ 설정] → [보안카드 입력]에서 다시 넣어 주세요.")
    if len(card) != 30:
        raise 멈춤("보안카드가 입력돼 있지 않아요.\n[⚙ 설정] → [보안카드 입력]에서 30칸을 넣어 주세요.")
    return card


def 보안카드_입력():
    card = 보안카드_표()
    end = time.time() + 15
    edits = []
    while time.time() < end and len(edits) < 2:
        edits = []
        for w in chrome_windows():
            if "보안카드" not in w.Name:
                continue
            for c, _ in auto.WalkControl(w, maxDepth=80):
                n = c.Name or ""
                m = re.search(r"\[(\d+)\]\s*번\s*보안카드번호\s*(앞|뒤)\s*2자리", n)
                if c.ControlTypeName == "EditControl" and m and c.BoundingRectangle.width() > 0:
                    edits.append((c, int(m.group(1)), m.group(2)))
        time.sleep(0.5)
    if len(edits) < 2:
        raise 멈춤("보안카드 입력칸을 못 찾았어요." + ("\n" + 팝업_안내 if 팝업_차단됐나() else ""))
    for c, num, pos in edits:
        v = card[num][0 if pos == "앞" else 1]
        log(f"보안카드 [{num}]번 {pos} 2자리 입력")
        type_into(c, v)
    click_name("확인하기", ["ButtonControl"], win_key="보안카드", after=2.5)
    msg, ok, _ = 알림_기다리기(["인증에 성공", "일치하지", "올바른", "실패", "오류"], timeout=10, win_key="보안카드")
    if not msg or "성공" not in msg:
        raise 멈춤(f"보안카드 인증 실패: {msg}")
    log(f"알림: {msg} → 확인")
    click(ok)
    time.sleep(3)


def 장부_목록():
    """거래처기록\\YYYY년 MM월.xlsx 에서 아직 발급 안 한 것"""
    import 거래처장부 as B
    date = 지난달_말일()
    done = 기록_읽기()
    todo = []
    for r in B.읽기(date.year, date.month):
        bizno = B.등록번호_모양(r.get("등록번호"))
        memo = str(r.get("비고") or "").strip()
        key = (date.strftime("%Y-%m-%d"), bizno, memo, str(int(r["금액"])))
        if r.get("상태") == "발급완료" or key in done:
            continue
        if r.get("상태") == B.확인필요:
            log(f"[{r['번호']}] {r.get('상호')} - 등록번호 확인 필요 (고쳐서 저장하면 다시 발급) → 패스")
            continue
        todo.append({"번호": r["번호"], "거래처명": str(r.get("상호") or "").strip(), "사업자번호": bizno,
                     "대표자": str(r.get("성명") or "").strip(), "비고": memo, "금액": int(r["금액"]),
                     "주소": str(r.get("주소") or "").strip(), "이메일": str(r.get("이메일") or "").strip()})
    return date, todo


def 전체_발급():
    import 거래처장부 as B
    date, todo = 장부_목록()
    log(f"{date.month}월 식대 장부 / 작성일자 {date} / 발급할 것 {len(todo)}건")
    결과, 건너뛴것 = [], []
    for it in todo:
        key = (it["사업자번호"], it["비고"], it["금액"])
        try:
            d = B.숫자만(it["사업자번호"])
            if len(d) != 10 or not B.등록번호_검사(d):  # 홈택스에 넣어보기 전에 걸러냄
                raise 건너뜀("등록번호가 10자리가 아니거나 틀린 번호예요")
            승인번호 = 한건_발급(it, date)
        except 건너뜀 as e:
            log(f"⚠ [{it['번호']}] {it['거래처명']} - 등록번호 잘못됨({e}) → 건너뛰고 다음으로")
            건너뛴것.append(it)
            try:
                B.상태_표시(date.year, date.month, key, B.확인필요, str(e)[:60])
            except PermissionError:
                log("⚠ 장부 엑셀이 열려 있어서 '등록번호 확인 필요' 표시를 못 했어요.")
            continue
        결과.append((it, 승인번호))
        이번에_발급.append(f"{it['거래처명']} {it['금액']:,}원 {it['비고']}".strip())
        try:
            B.발급완료_표시(date.year, date.month, key, 승인번호)
        except PermissionError:
            log("⚠ 장부 엑셀이 열려 있어서 '발급완료' 표시를 못 했어요. (발급기록.txt 에는 적었어요)")
    log(f"이번에 발급한 건수: {len(결과)} / 건너뛴 것: {len(건너뛴것)}")
    저장됨 = 이미지_저장_전체(date)
    완료_알림(date, 결과, 건너뛴것, 저장됨)
    return 결과


# ══════════════════ 발급한 계산서 이미지(JPG)로 저장 ══════════════════
def 이미지_폴더(date):
    p = os.path.join(HERE, f"{date.year}년 {date.month:02d}월 장부")
    os.makedirs(p, exist_ok=True)
    return p


def 이미지_파일명(date, r):
    name = f"{date.month}월_{r['상호']}_{int(r['금액']):,}원" + (f"_{r['비고']}" if r.get("비고") else "")
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def 저장할_이미지_목록(date):
    """장부에서 발급완료인데 아직 이미지가 없는 것 (장부 순서대로)"""
    import 거래처장부 as B
    folder = os.path.join(HERE, f"{date.year}년 {date.month:02d}월 장부")
    out = []
    for r in B.읽기(date.year, date.month):
        if r.get("상태") != "발급완료":
            continue
        if not os.path.exists(os.path.join(folder, 이미지_파일명(date, r) + ".jpg")):
            out.append(r)
    return out


def 다운로드_폴더들():
    dirs = [os.path.join(os.path.expanduser("~"), "Downloads")]
    for prof in (r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Preferences",
                 r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Preferences"):
        try:
            d = json.load(open(os.path.expandvars(prof), encoding="utf-8"))["download"]["default_directory"]
            if d and d not in dirs:
                dirs.insert(0, d)
        except Exception:
            pass
    return [d for d in dirs if os.path.isdir(d)]


def 이미_조회됨(date, 첫줄):
    """조회 기간이 이미 말일~말일이고, 저장할 줄이 목록에 떠 있으면 True"""
    w = hometax_win()
    s = nth_ctrl(w, "조회 시작일 입력", ["EditControl"])
    e = nth_ctrl(w, "조회 종료일 입력", ["EditControl"])
    want = date.strftime("%Y%m%d")
    if not s or not e or re.sub(r"\D", "", 값(s)) != want or re.sub(r"\D", "", 값(e)) != want:
        return False
    return 목록_줄_찾기(첫줄) is not None


def 발급목록_조회(date, 건수, 첫줄=None):
    if 첫줄 is not None and 이미_조회됨(date, 첫줄):
        log(f"이미 {date} 발급목록이 떠 있어서 조회 없이 바로 진행")
        return
    scroll_top()
    if not find("조회 시작일 입력", ["EditControl"], timeout=1, win_key="홈택스"):  # 이미 목록 화면이면 안 누름
        click_name("발급목록 조회", ["ButtonControl"], win_key="홈택스", after=2.5)
    if not find("조회 시작일 입력", ["EditControl"], timeout=15, win_key="홈택스"):
        raise 멈춤("발급목록 조회 화면이 안 떴어요.")
    for nm in ("조회 시작일 입력", "조회 종료일 입력"):
        e = nth_ctrl(hometax_win(), nm, ["EditControl"])
        type_into(e, date.strftime("%Y%m%d"))
        pyautogui.press("tab")
        time.sleep(0.4)
    if 건수 > 10:  # 한 화면에 다 나오게
        try:
            cb = nth_ctrl(hometax_win(), "조회건수 선택", ["ComboBoxControl"])
            cb.GetExpandCollapsePattern().Expand()
            time.sleep(0.6)
            want = next(n for n in ("50", "30", "20") if int(n) >= 건수) if 건수 <= 50 else "50"
            for c, _ in auto.WalkControl(cb, maxDepth=4):
                if c.ControlTypeName == "ListItemControl" and c.Name == want:
                    c.GetSelectionItemPattern().Select()
            cb.GetExpandCollapsePattern().Collapse()
        except Exception:
            pass
    log(f"발급목록 조회: {date} ~ {date}")
    click(nth_ctrl(hometax_win(), "조회", ["ButtonControl"]))
    time.sleep(3)


@com_safe()
def 목록_줄_찾기(r):
    """조회 결과에서 장부 한 줄에 해당하는 줄 (승인번호 → 없으면 등록번호+금액)"""
    import 거래처장부 as B
    no = str(r.get("승인번호") or "")
    biz = B.등록번호_모양(r["등록번호"])
    amt = f"{int(r['금액']):,}"
    w = hometax_win()
    for c, _ in auto.WalkControl(w, maxDepth=90):
        if c.ControlTypeName != "DataItemControl":
            continue
        n = c.Name or ""
        if len(n) < 40:
            continue
        if (re.fullmatch(r"\d{8}-\d{8}-\d{8}", no) and no in n) or (biz in n and f" {amt} " in f" {n} "):
            return c
    return None


def 한장_저장(date, r, folder):
    name = 이미지_파일명(date, r)
    log(f"이미지 저장: {name}")
    row = wait_for(lambda: 목록_줄_찾기(r), timeout=10, interval=1)
    if not row:
        raise 멈춤(f"발급목록에서 '{r['상호']} {int(r['금액']):,}원'을 못 찾았어요.")
    scroll_into_view(row)
    time.sleep(0.4)
    w = hometax_win()
    head = next((c for c, _ in auto.WalkControl(w, maxDepth=90)
                 if c.ControlTypeName == "DataItemControl" and (c.Name or "").strip() == "상호"
                 and c.BoundingRectangle.width() > 0), None)
    x = head.BoundingRectangle.xcenter() if head else row.BoundingRectangle.xcenter()
    y = row.BoundingRectangle.ycenter()
    pyautogui.moveTo(x, y, duration=0.2)
    pyautogui.doubleClick()
    a5 = find("출력(A5)", ["ButtonControl"], timeout=15, win_key="홈택스")
    if not a5:
        raise 멈춤("상세조회 창이 안 떴어요.")
    time.sleep(1)
    before = {d: set(os.listdir(d)) for d in 다운로드_폴더들()}
    click(a5)
    rep = wait_for(lambda: next((x for x in chrome_windows() if x.Name.startswith("Report")
                                 and x.BoundingRectangle.width() > 0), None), timeout=20)
    if not rep:
        raise 멈춤("출력 창(Report)이 안 떴어요." + ("\n" + 팝업_안내 if 팝업_차단됐나() else ""))
    rep.SetActive()
    save = wait_for(lambda: find_in(rep, "저장", ["ButtonControl"]), timeout=20, interval=1)
    if not save:
        raise 멈춤("출력 창의 저장 버튼을 못 찾았어요.")
    time.sleep(1.5)  # 보고서 그려질 때까지
    click(save)
    cb = wait_for(lambda: find_in(rep, "파일형식", ["ComboBoxControl"]), timeout=10, interval=0.5)
    if not cb:
        raise 멈춤("저장 창이 안 떴어요.")
    for _ in range(3):
        try:
            cb.GetExpandCollapsePattern().Expand()
            time.sleep(0.5)
            it = next(c for c, _ in auto.WalkControl(cb, maxDepth=4)
                      if c.ControlTypeName == "ListItemControl" and "JPG" in (c.Name or ""))
            it.GetSelectionItemPattern().Select()
            time.sleep(0.3)
            cb.GetExpandCollapsePattern().Collapse()
        except Exception:
            pass
        time.sleep(0.5)
        if "JPG" in 값(find_in(rep, "파일형식", ["ComboBoxControl"])):
            break
    else:
        raise 멈춤("파일형식을 JPG로 못 바꿨어요.")
    type_into(find_in(rep, "파일명", ["EditControl"]), name)
    ok = next(c for c, _ in auto.WalkControl(rep, maxDepth=90)
              if c.ControlTypeName == "ButtonControl" and (c.Name or "").strip() == "저장"
              and c.BoundingRectangle.top > save.BoundingRectangle.bottom)
    click(ok)

    # 다운로드 기다리기 (크롬이 '다른 이름으로 저장' 창을 띄우면 거기에 바로 경로 입력)
    target = os.path.join(folder, name + ".jpg")
    end = time.time() + 30
    got = None
    while time.time() < end and not got:
        for d, old in before.items():
            new = [f for f in set(os.listdir(d)) - old
                   if f.lower().endswith(".jpg") and not f.endswith((".crdownload", ".tmp"))]
            if new:
                got = os.path.join(d, new[0])
                break
        dlg = auto.WindowControl(searchDepth=1, ClassName="#32770")
        if not got and dlg.Exists(0, 0) and ("저장" in dlg.Name or "Save" in dlg.Name):
            fn = dlg.EditControl(searchDepth=12)
            if fn.Exists(1, 0):
                fn.GetValuePattern().SetValue(target)
                time.sleep(0.3)
                pyautogui.press("enter")
                time.sleep(2)
                if os.path.exists(target):
                    got = target
        time.sleep(0.5)
    if not got:
        raise 멈춤(f"'{name}.jpg' 저장(다운로드)이 안 됐어요.")
    time.sleep(1)  # 다 써질 때까지
    if os.path.abspath(got) != os.path.abspath(target):
        if os.path.exists(target):
            os.remove(target)
        os.replace(got, target)
    log(f"  → {os.path.basename(folder)}\\{name}.jpg")

    # 출력 창 닫고, 상세조회 닫기
    try:
        rep.GetWindowPattern().Close()
    except Exception:
        rep.SetActive()
        pyautogui.hotkey("ctrl", "w")
    time.sleep(1.5)
    w = hometax_win()
    w.SetActive()
    a5 = nth_ctrl(w, "출력(A5)", ["ButtonControl"])
    if a5:
        ay = a5.BoundingRectangle.ycenter()
        close = next((c for c, _ in auto.WalkControl(w, maxDepth=90)
                      if c.ControlTypeName == "ButtonControl" and (c.Name or "").strip() == "닫기"
                      and abs(c.BoundingRectangle.ycenter() - ay) < 10), None)
        if close:
            click(close)
            time.sleep(1.5)
    return target


def 이미지_저장_전체(date):
    """발급완료인데 이미지 없는 것을 장부 순서대로 저장. 저장한 개수 반환"""
    import 거래처장부 as B
    todo = 저장할_이미지_목록(date)
    if not todo:
        log("이미지로 저장할 것 없음 (다 저장돼 있음)")
        return 0
    folder = 이미지_폴더(date)
    log(f"── 발급한 계산서 이미지 저장 {len(todo)}건 → {folder}")
    발급목록_조회(date, len(B.읽기(date.year, date.month)), todo[0])
    n = 0
    for r in todo:
        try:
            한장_저장(date, r, folder)
            n += 1
        except 멈춤 as e:
            log(f"⚠ 이미지 저장 실패: {r['상호']} - {e}")
            for x in chrome_windows():  # 열려 있던 출력 창 정리
                if x.Name.startswith("Report"):
                    try:
                        x.GetWindowPattern().Close()
                    except Exception:
                        pass
    log(f"이미지 저장 완료: {n}/{len(todo)}건")
    return n


def 완료_알림(date, 결과, 건너뛴것, 저장됨=0):
    """다 끝나면 큰 글씨로 '세금계산서 발행 완료' 창"""
    import tkinter as tk
    root = tk.Tk()
    root.title("세금계산서 발행 완료")
    root.configure(bg="white")
    root.attributes("-topmost", True)
    F = "맑은 고딕"
    tk.Label(root, text="✔ 세금계산서 발행 완료", font=(F, 30, "bold"), fg="#006100", bg="white"
             ).pack(padx=50, pady=(30, 10))
    tk.Label(root, text=f"{date.month}월 식대 {len(결과)}건 발행했어요", font=(F, 20), bg="white").pack(pady=(0, 5))
    if 저장됨:
        tk.Label(root, text=f"계산서 이미지 {저장됨}장 → '{date.year}년 {date.month:02d}월 장부' 폴더에 저장",
                 font=(F, 15), fg="#2F5597", bg="white").pack(pady=(0, 15))
    for it, no in 결과[:15]:
        tk.Label(root, text=f"· {it['거래처명']}  {it['금액']:,}원 {it['비고']}", font=(F, 16), bg="white",
                 anchor="w").pack(fill="x", padx=60)
    if 건너뛴것:
        tk.Label(root, text=f"\n✖ 등록번호가 잘못돼서 못 한 것 {len(건너뛴것)}건", font=(F, 20, "bold"),
                 fg="#C00000", bg="white").pack(padx=50)
        for it in 건너뛴것:
            tk.Label(root, text=f"· {it['거래처명']}  ({it['사업자번호']})", font=(F, 16), fg="#C00000",
                     bg="white", anchor="w").pack(fill="x", padx=60)
        tk.Label(root, text="세금계산서 프로그램에서 빨간 줄을 눌러 등록번호를 고친 뒤\n다시 [② 발급하기]를 눌러 주세요.",
                 font=(F, 15), fg="#555", bg="white").pack(padx=50, pady=10)
    tk.Button(root, text="확인", font=(F, 20, "bold"), width=10, bg="#E2EFDA", command=root.destroy
              ).pack(pady=25)
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    root.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{max((root.winfo_screenheight() - h) // 2, 0)}")
    root.mainloop()


def main():
    log("홈택스 자동화 시작 (멈추려면 마우스를 화면 왼쪽 위 구석으로)")
    if capslock_끄기():
        log("Caps Lock 이 켜져 있어서 껐어요")
    date, todo = 장부_목록()
    이미지_남음 = 저장할_이미지_목록(date)
    if 인증요청_누르기 and not todo and not 이미지_남음:
        raise 멈춤(f"{date.month}월 식대 장부에 발급할 게 없어요. (이미지도 다 저장돼 있어요)")
    if not todo and 이미지_남음:
        log(f"발급할 건 없고, 이미지 저장만 {len(이미지_남음)}건 해요")
    for it in todo:
        log(f"  발급 예정: {it['거래처명']} {it['금액']:,}원 {it['비고']}")
    if not use_open_hometax():
        win = open_chrome()
        search_hometax(win)
        time.sleep(2)
        click_first_hometax(win)
    login()
    open_issue_menu()
    simple_auth()
    if 인증요청_누르기:
        전체_발급()
    log("완료!")


def 멈춤_안내(이유, 사용자=False):
    """아버지가 알아볼 수 있는 큰 글씨 안내창"""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title("세금계산서 - 멈췄어요")
        root.configure(bg="white")
        root.attributes("-topmost", True)
        F = "맑은 고딕"
        tk.Label(root, text="⚠ 자동 발급이 멈췄어요", font=(F, 30, "bold"), fg="#C00000", bg="white"
                 ).pack(padx=50, pady=(30, 10))
        if 사용자:
            안내 = "직접 멈추셨어요. 다시 하시려면 [② 발급하기]를 누르세요."
        else:
            안내 = "홈택스 화면이 바뀌었거나 예상과 달라서 멈췄어요.\n이 화면을 사진 찍어서 아들한테 보내 주세요."
        tk.Label(root, text=안내, font=(F, 20), bg="white").pack(padx=40, pady=10)
        if 이번에_발급:
            tk.Label(root, text=f"멈추기 전에 발급된 것 {len(이번에_발급)}건 (장부에 '발급완료'로 표시돼 있어요)",
                     font=(F, 17, "bold"), fg="#006100", bg="white").pack(pady=(10, 0))
            for x in 이번에_발급[:10]:
                tk.Label(root, text="· " + x, font=(F, 15), bg="white").pack()
        else:
            tk.Label(root, text="발급된 것은 없어요.", font=(F, 17, "bold"), fg="#006100", bg="white").pack(pady=10)
        tk.Label(root, text="나머지는 발급 안 됐어요. 같은 계산서가 두 번 발급되지는 않아요.", font=(F, 15),
                 fg="#555", bg="white").pack(pady=(10, 0))
        tk.Label(root, text="(자세한 이유: " + 이유.replace("\n", " ")[:150] + ")", font=(F, 12), fg="#888",
                 bg="white", wraplength=760, justify="left").pack(padx=40, pady=15)
        tk.Button(root, text="확인", font=(F, 20, "bold"), width=10, command=root.destroy).pack(pady=(5, 25))
        root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()
        root.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{max((root.winfo_screenheight() - h) // 2, 0)}")
        root.mainloop()
    except Exception:
        pass


def 점검():
    """아버지 화면의 [점검하기]에서 부름: 화면 크기·배율, 자동 입력 시험"""
    def out(ok, title, detail=""):
        print(f"CHECK\t{1 if ok else 0}\t{title}\t{detail}", flush=True)

    w, h = pyautogui.size()
    try:
        scale = round(ctypes.windll.user32.GetDpiForSystem() / 96 * 100)
    except Exception:
        scale = 100
    out(w >= 1024 and h >= 600, f"화면 {w}×{h}, 배율 {scale}%",
        "" if w >= 1024 and h >= 600 else "화면이 너무 작아요. 해상도를 높여 주세요.")

    if capslock_끄기():
        out(True, "Caps Lock 이 켜져 있어서 껐어요", "켜져 있으면 영어 대소문자가 뒤집혀 들어가요. 프로그램이 알아서 꺼요.")
    # 자동 입력 시험: 작은 창을 띄워 글자를 쳐 보고 그대로 들어가는지 확인
    import tkinter as tk
    root = tk.Tk()
    root.title("자동 입력 시험")
    root.geometry("420x120+200+200")
    root.attributes("-topmost", True)
    e = tk.Entry(root, font=("맑은 고딕", 20))
    e.pack(padx=20, pady=30, fill="x")
    result = {}

    def run():
        root.focus_force()
        e.focus_force()
        root.update()
        x, y = e.winfo_rootx() + 30, e.winfo_rooty() + 15
        pyautogui.click(x, y)
        pyautogui.write("Ab12", interval=0.05)
        pyperclip.copy("가나")
        pyautogui.hotkey("ctrl", "v")
        root.update()
        root.after(400, lambda: (result.update(v=e.get()), root.destroy()))
    root.after(500, run)
    root.after(8000, root.destroy)
    root.mainloop()
    v = result.get("v", "")
    out(v == "Ab12가나", "자동 입력(마우스·키보드) 됨" if v == "Ab12가나" else "자동 입력이 안 돼요",
        "" if v == "Ab12가나" else f"들어간 값: '{v}' - 보안 프로그램이 막는지 확인이 필요해요.")
    try:
        import winrt.windows.globalization as g
        import winrt.windows.media.ocr as o
        ok = o.OcrEngine.is_language_supported(g.Language("ko"))
    except Exception:
        ok = False
    out(True, "한국어 글자인식 " + ("있음" if ok else "없음 (없어도 대부분 괜찮아요)"))


if __name__ == "__main__":
    if "--점검" in sys.argv:
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # 아버지 화면이 utf-8 로 읽음
        except Exception:
            pass
        점검()
        sys.exit(0)
    if "--멈춤" in sys.argv:
        인증요청_누르기 = False
    was_on = screen_reader_flag_get()
    screen_reader_flag(True)
    절전_막기(True)
    code = 0
    try:
        main()
    except 멈춤 as e:
        log("멈춤: " + str(e))
        code = 1
        멈춤_안내(str(e))
    except pyautogui.FailSafeException:
        log("사용자가 멈췄어요.")
        code = 1
        멈춤_안내("마우스를 화면 구석으로 밀어서 멈췄어요.", 사용자=True)
    except Exception as e:  # 예상 못 한 오류도 창이 바로 닫히지 않게
        import traceback
        traceback.print_exc()
        log("멈춤: 예상 못 한 오류 - " + str(e))
        code = 1
        멈춤_안내("예상 못 한 오류: " + str(e)[:120])
    finally:
        절전_막기(False)
        if not was_on:
            screen_reader_flag(False)
    try:
        input("\n엔터를 누르면 이 창이 닫혀요...")
    except Exception:
        pass
    sys.exit(code)

