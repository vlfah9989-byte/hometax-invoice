# -*- coding: utf-8 -*-
"""세금계산서 - 아버지용 화면 (거래처 입력 / 발급하기)"""
import datetime
import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import 거래처장부 as B

_BASE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
# 코드가 "소스코드" 폴더에 있으면 장부·설정·기록은 한 단계 위(프로그램 폴더)에 있는 걸 같이 씀
HERE = os.path.dirname(_BASE) if os.path.basename(_BASE) == "소스코드" else _BASE
F = "맑은 고딕"
S = 1.0  # 화면 크기에 맞춘 글씨 배율 (작은 노트북이면 줄어듦)


def fs(n):
    return max(int(round(n * S)), 11)


BIG = MID = SMALL = None


def set_fonts(screen_h):
    global S, BIG, MID, SMALL
    S = max(0.6, min(1.0, screen_h / 1050))
    BIG, MID, SMALL = (F, fs(22)), (F, fs(18)), (F, fs(15))

설정파일 = os.path.join(HERE, "설정.json")
기본설정 = {"아이디": "", "비밀번호": "", "주민번호_앞6": "", "주민번호_뒤1": "",
         "이름": "", "생년월일": "", "휴대폰_뒷자리": "", "상호": ""}  # 실제 값은 설정.json (암호화)

import 보안저장


def 설정_읽기():
    s, 못푼것 = 보안저장.설정_읽기(설정파일, 기본설정)
    s["_못푼것"] = 못푼것
    return s


def 설정_쓰기(s):
    보안저장.설정_쓰기(설정파일, {k: v for k, v in s.items() if not k.startswith("_")})


def 보안카드_상태():
    """(칸 수, 문제 설명)"""
    try:
        card = 보안저장.보안카드_읽기(HERE)
    except 보안저장.풀기실패:
        return 0, "다른 컴퓨터에서 저장한 보안카드라 이 컴퓨터에서는 못 읽어요. 다시 넣어 주세요."
    except Exception as e:
        return 0, f"보안카드를 못 읽었어요 ({str(e)[:40]})"
    return len(card), ""


def 제목():
    상호 = 설정_읽기().get("상호", "").strip()
    return f"{상호} 세금계산서" if 상호 else "세금계산서"


def 발급_명령(*args):
    """exe 로 묶였으면 홈택스발급.exe, 아니면 파이썬으로 홈택스열기.py"""
    exe = os.path.join(HERE, "홈택스발급.exe")
    if getattr(sys, "frozen", False) and os.path.exists(exe):
        return [exe, *args]
    py = sys.executable.replace("pythonw.exe", "python.exe")  # 진행 상황이 보이는 검은 창으로
    return [py, os.path.join(_BASE, "홈택스열기.py"), *args]


def 점검_목록():
    """(괜찮은지, 제목, 설명) 목록"""
    out = []
    # 1) 브라우저
    cands = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")]
    edge = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    if any(os.path.exists(p) for p in cands):
        out.append((True, "크롬 설치됨", ""))
    elif any(os.path.exists(p) for p in edge):
        out.append((True, "크롬은 없지만 엣지로 진행해요", ""))
    else:
        out.append((False, "인터넷 브라우저(크롬)가 없어요", "크롬을 설치해 주세요."))
    # 2) 인터넷 / 홈택스 접속
    try:
        import urllib.request
        urllib.request.urlopen("https://www.hometax.go.kr", timeout=8)
        out.append((True, "홈택스 접속 됨", ""))
    except Exception as e:
        out.append((False, "홈택스에 접속이 안 돼요", f"인터넷 연결을 확인해 주세요. ({str(e)[:60]})"))
    # 3) 설정
    cfg = 설정_읽기()
    if cfg.get("_못푼것"):
        out.append((False, "설정을 이 컴퓨터에서 읽을 수 없어요",
                    "다른 컴퓨터에서 저장한 설정이에요. [⚙ 설정]에서 다시 넣어 주세요."))
    if cfg.get("아이디") and cfg.get("비밀번호"):
        out.append((True, "홈택스 아이디·비밀번호 설정됨", ""))
    else:
        out.append(("주의", "홈택스 아이디·비밀번호가 설정 안 돼 있어요",
                    "크롬에 저장돼 있으면 그대로 돼요. 다른 컴퓨터라면 [⚙ 설정]에서 넣어 주세요."))
    need = [k for k in ("주민번호_앞6", "주민번호_뒤1", "이름", "생년월일", "휴대폰_뒷자리") if not cfg.get(k)]
    out.append((not need, "인증용 정보(주민번호·이름·생년월일·휴대폰)" + (" 설정됨" if not need else " 빠짐"),
                ", ".join(need)))
    # 4) 보안카드
    n, why = 보안카드_상태()
    out.append((n == 30, f"보안카드 {n}/30칸 (암호화 저장)" if n else "보안카드가 입력돼 있지 않아요",
                "" if n == 30 else (why or "[⚙ 설정] → [보안카드 입력]에서 30칸을 넣어 주세요.")))
    # 5) 장부
    by, bm = B.발급할_달()
    rows = B.읽기(by, bm)
    남은 = [r for r in rows if r.get("상태") not in ("발급완료", B.확인필요)]
    out.append((True, f"{bm}월 식대 장부: {len(rows)}건 (발급 전 {len(남은)}건)", ""))
    # 6) 화면 크기·배율 + 자동 입력(키보드) 시험 → 발급 프로그램으로 확인
    try:
        r = subprocess.run(발급_명령("--점검"), cwd=HERE, capture_output=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for line in r.stdout.decode("utf-8", "replace").splitlines():
            if line.startswith("CHECK\t"):
                _, ok, title, detail = (line.split("\t") + ["", "", ""])[:4]
                out.append((ok == "1", title, detail))
    except Exception as e:
        out.append((False, "자동 입력 시험을 못 했어요", str(e)[:80]))
    return out


FIELDS = [  # (이름, 설명, 꼭 써야 함)
    ("상호", "거래처 이름 (몇 글자만 쳐도 예전 거래처가 나와요)", True),
    ("등록번호", "사업자등록번호 숫자 10자리", True),
    ("성명", "대표자 이름", False),
    ("금액", "받은 금액 (부가세 포함)", True),
    ("비고", "2공구 같은 것 (없으면 비워두세요)", False),
    ("주소", "사업장 주소 (모르면 비워두세요)", False),
    ("이메일", "계산서 받을 메일 (모르면 비워두세요)", False),
]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        set_fonts(self.winfo_screenheight())
        self.title(제목())
        self.state("zoomed")
        self.configure(bg="white")
        style = ttk.Style(self)
        style.configure("Treeview", font=SMALL, rowheight=int(36 * S))
        style.configure("Treeview.Heading", font=(F, fs(15), "bold"))
        self.option_add("*TCombobox*Listbox.font", MID)
        self.frame = None
        self.home()
        if getattr(sys, "frozen", False):  # exe 로 켰을 때만
            self.after(1500, self.check_update)

    def switch(self):
        if self.frame:
            self.frame.destroy()
        self.frame = tk.Frame(self, bg="white")
        self.frame.pack(fill="both", expand=True)
        return self.frame

    # ───────────── 처음 화면 ─────────────
    def home(self):
        f = self.switch()
        iy, im = B.입력할_달()
        by, bm = B.발급할_달()
        rows = B.읽기(by, bm)
        남은 = [r for r in rows if r.get("상태") not in ("발급완료", B.확인필요)]
        틀림 = [r for r in rows if r.get("상태") == B.확인필요]
        if (iy, im) != (by, bm):
            틀림 += [r for r in B.읽기(iy, im) if r.get("상태") == B.확인필요]
        tk.Label(f, text=제목(), font=(F, fs(34), "bold"), bg="white").pack(pady=(fs(70), 10))
        try:
            from 버전 import 버전 as _v
        except Exception:
            _v = ""
        tk.Label(f, text=f"v{_v}", font=SMALL, bg="white", fg="#BBB").place(relx=0.99, rely=0.99, anchor="se")
        tk.Label(f, text=datetime.date.today().strftime("오늘: %Y년 %m월 %d일"), font=MID,
                 bg="white", fg="#555").pack(pady=(0, fs(20) if 틀림 else fs(50)))
        if 틀림:
            names = ", ".join(r["상호"] for r in 틀림[:3]) + (" 등" if len(틀림) > 3 else "")
            tk.Label(f, text=f"⚠ 등록번호 확인 필요 {len(틀림)}건: {names}\n"
                             f"①에 들어가서 빨간 줄을 눌러 등록번호를 고쳐 주세요",
                     font=(F, fs(20), "bold"), fg="white", bg="#C00000", padx=20, pady=8
                     ).pack(pady=(0, fs(20)))
        tk.Button(f, text=f"①  거래처 입력하기\n({im}월 식대)", font=(F, fs(28), "bold"), width=28, height=3,
                  bg="#DDEBF7", relief="ridge", command=self.input_screen).pack(pady=fs(15))
        tk.Button(f, text=f"②  세금계산서 발급하기\n({bm}월 식대 · 발급 안 된 것 {len(남은)}건)",
                  font=(F, fs(28), "bold"), width=28, height=3, bg="#E2EFDA", relief="ridge",
                  command=self.issue).pack(pady=fs(15))
        bottom = tk.Frame(f, bg="white")
        bottom.pack(pady=fs(30))
        tk.Button(bottom, text="📁 지난 기록 폴더 열기", font=MID, bg="white", relief="flat", fg="#2F5597",
                  command=lambda: (os.makedirs(B.장부폴더, exist_ok=True), os.startfile(B.장부폴더))
                  ).pack(side="left", padx=20)
        tk.Button(bottom, text="🔍 점검하기", font=MID, bg="white", relief="flat", fg="#2F5597",
                  command=self.check).pack(side="left", padx=20)
        tk.Button(bottom, text="⚙ 설정", font=MID, bg="white", relief="flat", fg="#2F5597",
                  command=self.settings).pack(side="left", padx=20)

    # ───────────── 설정 (홈택스 아이디·비번 등) ─────────────
    def settings(self):
        f = self.switch()
        cfg = 설정_읽기()
        top = tk.Frame(f, bg="white")
        top.pack(fill="x", padx=40, pady=(20, 10))
        tk.Button(top, text="◀ 처음으로", font=MID, command=self.home).pack(side="left")
        tk.Label(top, text="설정", font=(F, fs(32), "bold"), bg="white").pack(side="left", padx=40)
        form = tk.Frame(f, bg="white")
        form.pack(padx=60, pady=10, anchor="w")
        items = [("아이디", "홈택스 아이디", False), ("비밀번호", "홈택스 비밀번호", True),
                 ("주민번호_앞6", "주민번호 앞 6자리 (2차 인증)", False),
                 ("주민번호_뒤1", "주민번호 뒤 첫 자리 (2차 인증)", True),
                 ("이름", "카톡 인증 받을 사람 이름", False), ("생년월일", "생년월일 8자리 (예: 19600101)", False),
                 ("휴대폰_뒷자리", "휴대폰 010 뒤 8자리", False), ("상호", "우리 가게 이름 (화면 제목)", False)]
        ents = {}
        for i, (k, label, secret) in enumerate(items):
            tk.Label(form, text=label + " :", font=MID, bg="white", anchor="e", width=24
                     ).grid(row=i, column=0, sticky="e", pady=6)
            e = tk.Entry(form, font=BIG, width=22, relief="solid", bd=1, show="●" if secret else "")
            e.insert(0, cfg.get(k, ""))
            e.grid(row=i, column=1, sticky="w", padx=10)
            ents[k] = e
        tk.Label(f, text="※ 이 컴퓨터, 이 윈도우 계정에서만 풀리게 암호화해서 저장돼요. 크롬에 아이디·비번이 저장돼 있으면 비워둬도 돼요.",
                 font=SMALL, bg="white", fg="#777").pack(anchor="w", padx=60, pady=10)
        n, _ = 보안카드_상태()
        tk.Button(f, text=f"🔐 보안카드 입력  (지금 {n}/30칸)", font=(F, fs(20), "bold"),
                  bg="#DDEBF7" if n == 30 else "#FFC7CE", command=self.card_screen).pack(pady=(0, 5))

        def save():
            cfg.update({k: e.get().strip() for k, e in ents.items()})
            설정_쓰기(cfg)
            messagebox.showinfo("설정", "저장했어요.")
            self.home()
        tk.Button(f, text="💾 저장", font=(F, fs(24), "bold"), width=12, bg="#FFE699", command=save).pack(pady=20)

    # ───────────── 보안카드 입력 ─────────────
    def card_screen(self):
        f = self.switch()
        top = tk.Frame(f, bg="white")
        top.pack(fill="x", padx=40, pady=(20, 10))
        tk.Button(top, text="◀ 설정으로", font=MID, command=self.settings).pack(side="left")
        tk.Label(top, text="보안카드 입력", font=(F, fs(32), "bold"), bg="white").pack(side="left", padx=40)
        tk.Label(f, text="보안카드를 보면서 칸마다 숫자 4개를 넣어 주세요. (예: 12 34 → 1234)",
                 font=MID, bg="white", fg="#555").pack(pady=(0, 15))
        try:
            card = 보안저장.보안카드_읽기(HERE)
        except Exception:
            card = {}
        grid = tk.Frame(f, bg="white")
        grid.pack()
        ents = {}
        for i in range(30):
            num = i + 1
            row, col = i % 6, i // 6  # 보안카드: 1~6 이 첫 세로줄, 7~12 가 둘째 ...
            tk.Label(grid, text=f"{num}", font=MID, bg="#EEE", width=3, relief="solid", bd=1
                     ).grid(row=row, column=col * 2, padx=(18, 0), pady=6, ipady=4)
            e = tk.Entry(grid, font=BIG, width=6, justify="center", relief="solid", bd=1)
            if num in card:
                e.insert(0, "".join(card[num]))
            e.grid(row=row, column=col * 2 + 1, padx=(0, 6), pady=6)
            ents[num] = e
        order = [n for n in range(1, 31)]
        for idx, num in enumerate(order):  # 4자리 치면 다음 칸으로
            def nxt(ev, idx=idx):
                v = "".join(ch for ch in ents[order[idx]].get() if ch.isdigit())
                if len(v) == 4 and idx + 1 < len(order) and ev.keysym not in ("Tab", "BackSpace"):
                    ents[order[idx + 1]].focus_set()
            ents[num].bind("<KeyRelease>", nxt)

        def save():
            new, bad = {}, []
            for num, e in ents.items():
                v = "".join(ch for ch in e.get() if ch.isdigit())
                if len(v) == 4:
                    new[num] = (v[:2], v[2:])
                    e.config(bg="white")
                else:
                    bad.append(num)
                    e.config(bg="#FFC7CE")
            if bad:
                return messagebox.showwarning("보안카드", f"빨간 칸({', '.join(map(str, bad[:10]))}"
                                              + (" 등" if len(bad) > 10 else "") + ")은 숫자 4개를 넣어 주세요.")
            보안저장.보안카드_쓰기(HERE, new)
            messagebox.showinfo("보안카드", "저장했어요. (이 컴퓨터에서만 풀리게 암호화됐어요)")
            self.settings()
        tk.Button(f, text="💾 저장", font=(F, fs(24), "bold"), width=12, bg="#FFE699", command=save).pack(pady=25)
        ents[1].focus_set()

    # ───────────── 점검하기 ─────────────
    def check(self):
        f = self.switch()
        top = tk.Frame(f, bg="white")
        top.pack(fill="x", padx=40, pady=(20, 10))
        tk.Button(top, text="◀ 처음으로", font=MID, command=self.home).pack(side="left")
        tk.Label(top, text="점검하기", font=(F, fs(32), "bold"), bg="white").pack(side="left", padx=40)
        box = tk.Text(f, font=MID, bg="white", relief="flat", wrap="word")
        box.pack(fill="both", expand=True, padx=60, pady=10)
        box.insert("end", "점검 중이에요. 잠깐만 기다려 주세요... (작은 창이 잠깐 떴다 사라져요)\n")
        self.update()
        results = 점검_목록()
        box.delete("1.0", "end")
        bad = 0
        for ok, title, detail in results:
            if ok == "주의":  # 안 해도 되지만 알아둘 것 (✖ 개수에 안 셈)
                box.insert("end", "⚠ " + title + "\n", "warn")
            else:
                box.insert("end", ("✔ " if ok else "✖ ") + title + "\n", "ok" if ok else "bad")
                bad += (not ok)
            if detail:
                box.insert("end", "     " + detail + "\n", "detail")
        box.insert("end", "\n" + ("모두 괜찮아요. 발급을 시작해도 돼요." if not bad
                                  else f"✖ 표시 {bad}개를 먼저 해결해 주세요."), "ok" if not bad else "bad")
        box.tag_config("ok", foreground="#006100")
        box.tag_config("bad", foreground="#C00000")
        box.tag_config("warn", foreground="#B8860B")
        box.tag_config("detail", foreground="#555", font=SMALL)
        box.config(state="disabled")

    # ───────────── 입력 화면 ─────────────
    def input_screen(self):
        f = self.switch()
        self.y, self.m = B.입력할_달()
        self.rows = B.읽기(self.y, self.m)
        self.known = B.예전_거래처()
        self.editing = None  # 수정 중인 줄 번호(0부터)

        top = tk.Frame(f, bg="white")
        top.pack(fill="x", padx=40, pady=(20, 5))
        tk.Button(top, text="◀ 처음으로", font=MID, command=self.home).pack(side="left")
        red = (F, fs(32), "bold")
        tk.Frame(top, width=40, bg="white").pack(side="left")
        self.ye = tk.Entry(top, font=red, width=5, justify="center", fg="#C00000", relief="solid", bd=1)
        self.ye.insert(0, str(self.y))
        self.ye.pack(side="left")
        tk.Label(top, text="년", font=red, bg="white", fg="#C00000").pack(side="left", padx=(4, 12))
        tk.Button(top, text="◀", font=MID, command=lambda: self.move_month(-1)).pack(side="left")
        self.me = tk.Entry(top, font=red, width=3, justify="center", fg="#C00000", relief="solid", bd=1)
        self.me.insert(0, str(self.m))
        self.me.pack(side="left", padx=4)
        tk.Button(top, text="▶", font=MID, command=lambda: self.move_month(1)).pack(side="left")
        tk.Label(top, text="월 식대 입력", font=red, bg="white", fg="#C00000").pack(side="left", padx=(8, 20))
        tk.Label(top, text="(월을 고치고 엔터)", font=SMALL, bg="white", fg="#777").pack(side="left")
        for e in (self.ye, self.me):
            e.bind("<Return>", self.change_month)
            e.bind("<FocusOut>", self.change_month)

        form = tk.Frame(f, bg="white")
        form.pack(fill="x", padx=60, pady=10)
        self.ent = {}
        for i, (name, hint, must) in enumerate(FIELDS):
            tk.Label(form, text=("★ " if must else "   ") + name + " :", font=BIG, bg="white",
                     anchor="e", width=10).grid(row=i, column=0, sticky="e", pady=6)
            e = tk.Entry(form, font=BIG, width=39, relief="solid", bd=1)
            if name == "상호":
                e.bind("<KeyRelease>", self.on_name_type)
                e.bind("<Down>", self.sugg_focus)
                e.bind("<FocusOut>", lambda ev: self.after(200, self.sugg_hide_if_unfocused))
            e.grid(row=i, column=1, sticky="w", padx=10, pady=6)
            e.bind("<Return>", lambda ev, i=i: self.next_field(i))
            tk.Label(form, text=hint, font=SMALL, bg="white", fg="#777").grid(row=i, column=2, sticky="w")
            self.ent[name] = e
        # 상호 추천 목록 (상호 칸 바로 아래에 뜨고, 커서를 뺏지 않음)
        self.sugg = tk.Listbox(f, font=MID, height=5, bg="#FFFBE6", relief="solid", bd=1,
                               activestyle="none", exportselection=False)
        self.sugg.bind("<ButtonRelease-1>", self.sugg_pick)
        self.sugg.bind("<Return>", self.sugg_pick)
        self.sugg.bind("<Escape>", lambda ev: (self.sugg_hide(), self.ent["상호"].focus_set()))
        self.ent["등록번호"].bind("<FocusOut>", self.on_bizno_out)
        self.ent["등록번호"].bind("<KeyRelease>", self.on_bizno_type)
        self.ent["금액"].bind("<FocusOut>", self.on_amount_out)

        btns = tk.Frame(f, bg="white")
        btns.pack(pady=10)
        self.save_btn = tk.Button(btns, text="💾 저장", font=(F, fs(24), "bold"), width=14, bg="#FFE699",
                                  command=self.save)
        self.save_btn.pack(side="left", padx=12)
        tk.Button(btns, text="새로 입력", font=MID, width=10, command=self.clear).pack(side="left", padx=12)
        tk.Button(btns, text="선택한 줄 삭제", font=MID, width=12, command=self.delete).pack(side="left", padx=12)

        self.count = tk.Label(f, font=MID, bg="white")
        self.count.pack(anchor="w", padx=60)
        cols = ("상호", "등록번호", "성명", "금액", "비고", "상태")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=8)
        for c, w in zip(cols, (330, 190, 190, 160, 110, 150)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="center" if c != "상호" else "w")
        self.tree.pack(fill="both", expand=True, padx=60, pady=(5, 20))
        self.tree.bind("<<TreeviewSelect>>", self.on_pick)
        self.refresh()
        self.ent["상호"].focus_set()

    def move_month(self, step):
        y, m = self.y, self.m + step
        if m < 1:
            y, m = y - 1, 12
        elif m > 12:
            y, m = y + 1, 1
        self.load_month(y, m)

    def change_month(self, ev=None):
        try:
            y = int(B.숫자만(self.ye.get()))
            m = int(B.숫자만(self.me.get()))
        except ValueError:
            y, m = 0, 0
        if not (2000 <= y <= 2100 and 1 <= m <= 12):
            self.ye.delete(0, "end"); self.ye.insert(0, str(self.y))
            self.me.delete(0, "end"); self.me.insert(0, str(self.m))
            if ev and ev.type == tk.EventType.KeyPress:
                messagebox.showwarning("확인해 주세요", "월은 1부터 12까지 적어 주세요.")
            return
        if (y, m) != (self.y, self.m):
            self.load_month(y, m)
        elif ev and ev.type == tk.EventType.KeyPress:
            self.ent["상호"].focus_set()

    def load_month(self, y, m):
        self.y, self.m = y, m
        self.ye.delete(0, "end"); self.ye.insert(0, str(y))
        self.me.delete(0, "end"); self.me.insert(0, str(m))
        self.rows = B.읽기(y, m)
        self.refresh()
        self.clear()

    def next_field(self, i):
        if i + 1 < len(FIELDS):
            self.ent[FIELDS[i + 1][0]].focus_set()
        else:
            self.save()

    def on_name_type(self, ev):
        if ev.keysym in ("Return", "Up", "Down", "Tab", "Escape", "Left", "Right", "Home", "End"):
            return
        # 지울 때나, 이미 저장된 줄을 고칠 때는 추천 안 띄움
        if ev.keysym in ("BackSpace", "Delete") or self.editing is not None:
            self.sugg_hide()
            return
        t = self.ent["상호"].get().replace(" ", "")
        hits = [n for n in self.known if len(t) >= 2 and t in n.replace(" ", "") and n != self.ent["상호"].get()]
        if not hits:
            self.sugg_hide()
            return
        self.sugg.delete(0, "end")
        for n in hits[:8]:
            self.sugg.insert("end", "  " + n)
        e = self.ent["상호"]
        self.sugg.config(height=min(len(hits), 5), width=e.cget("width") + 6)
        self.sugg.place(in_=e, x=0, rely=1.0, relwidth=1.0)
        self.sugg.lift()

    def sugg_focus(self, ev=None):
        if self.sugg.winfo_ismapped():
            self.sugg.focus_set()
            self.sugg.selection_clear(0, "end")
            self.sugg.selection_set(0)
            self.sugg.activate(0)

    def sugg_pick(self, ev=None):
        sel = self.sugg.curselection()
        if not sel:
            return
        name = self.sugg.get(sel[0]).strip()
        self.sugg_hide()
        self.set("상호", name)
        self.fill_known(name)

    def sugg_hide(self):
        self.sugg.place_forget()

    def sugg_hide_if_unfocused(self):
        if self.focus_get() is not self.sugg:
            self.sugg_hide()

    def fill_known(self, name):
        r = self.known.get(name)
        if not r:
            return
        for k in ("등록번호", "성명", "주소", "이메일"):
            self.set(k, r.get(k, ""))
        self.ent["금액"].focus_set()

    def on_bizno_out(self, ev=None):
        v = self.ent["등록번호"].get()
        if B.숫자만(v):
            self.set("등록번호", B.등록번호_모양(v))
            self.fill_by_bizno()

    def on_bizno_type(self, ev=None):
        """등록번호 10자리를 다 치는 순간 예전 거래처 정보 채우기"""
        if len(B.숫자만(self.ent["등록번호"].get())) == 10:
            self.set("등록번호", B.등록번호_모양(self.ent["등록번호"].get()))
            if self.fill_by_bizno():
                self.ent["금액"].focus_set()

    def fill_by_bizno(self):
        """같은 등록번호가 예전 장부에 있으면 상호·성명·주소·이메일 중 빈 칸만 채움"""
        if self.editing is not None:
            return False
        d = B.숫자만(self.ent["등록번호"].get())
        if len(d) != 10:
            return False
        for n, r in self.known.items():
            if B.숫자만(r.get("등록번호")) == d:
                filled = False
                for k, val in (("상호", n), ("성명", r.get("성명", "")),
                               ("주소", r.get("주소", "")), ("이메일", r.get("이메일", ""))):
                    if val and not self.ent[k].get().strip():
                        self.set(k, val)
                        filled = True
                if filled:
                    self.flash("예전 거래처 정보를 채웠어요")
                return True
        return False

    def on_amount_out(self, ev=None):
        d = B.숫자만(self.ent["금액"].get())
        if d:
            self.set("금액", f"{int(d):,}")

    def set(self, k, v):
        e = self.ent[k]
        e.delete(0, "end")
        e.insert(0, str(v or ""))

    def clear(self):
        for k in self.ent:
            self.set(k, "")
        self.editing = None
        self.editing_key = None
        self.ent["등록번호"].config(bg="white")
        self.sugg_hide()
        self.save_btn.config(text="💾 저장")
        self.tree.selection_remove(self.tree.selection())
        self.ent["상호"].focus_set()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.tree.tag_configure("bad", foreground="white", background="#C00000")
        self.tree.tag_configure("done", foreground="#006100")
        for i, r in enumerate(self.rows):
            st = r.get("상태") or "발급 전"
            tag = ("bad",) if st == B.확인필요 else ("done",) if st == "발급완료" else ()
            self.tree.insert("", "end", iid=str(i), tags=tag, values=(
                r["상호"], r["등록번호"], r.get("성명", ""), f"{int(r['금액']):,}", r.get("비고", ""),
                "⚠ 등록번호 확인" if st == B.확인필요 else st))
        bad = [str(i) for i, r in enumerate(self.rows) if r.get("상태") == B.확인필요]
        if bad:
            self.tree.see(bad[0])  # 빨간 줄이 화면 밖이면 거기까지 내려서 보여줌
        total = sum(int(r["금액"]) for r in self.rows)
        self.count.config(text=f"{self.m}월에 입력한 것: {len(self.rows)}건 / 합계 {total:,}원   "
                               f"(줄을 누르면 고칠 수 있어요)")

    def on_pick(self, ev):
        sel = self.tree.selection()
        if not sel:
            return
        i = int(sel[0])
        r = self.rows[i]
        for k, _, _ in FIELDS:
            self.set(k, f"{int(r['금액']):,}" if k == "금액" else r.get(k, ""))
        self.editing = i
        self.editing_key = self.row_key(r)
        self.save_btn.config(text="💾 고친 것 저장")
        if r.get("상태") == B.확인필요:
            self.ent["등록번호"].config(bg="#FFC7CE")
            self.ent["등록번호"].focus_set()
            messagebox.showwarning("등록번호 확인", f"{r['상호']}\n\n홈택스에서 등록번호가 잘못됐다고 나왔어요.\n"
                                   f"({r.get('승인번호', '')})\n\n등록번호를 고친 뒤 [고친 것 저장]을 눌러 주세요.")

    @staticmethod
    def row_key(r):
        return (B.숫자만(r.get("등록번호")), str(r.get("비고") or ""), int(r.get("금액") or 0),
                str(r.get("상호") or ""), str(r.get("입력한 날") or ""))

    def reload_rows(self):
        """발급 프로그램이 그사이 장부를 바꿨을 수 있으니 저장·삭제 직전에 새로 읽음"""
        self.rows = B.읽기(self.y, self.m)
        if self.editing is not None:
            idx = [i for i, r in enumerate(self.rows) if self.row_key(r) == self.editing_key]
            if not idx:
                self.refresh()
                self.clear()
                self.warn("그사이 목록이 바뀌었어요. 고칠 줄을 다시 눌러 주세요.")
                return False
            self.editing = idx[0]
        return True

    def save(self):
        self.on_bizno_out()
        self.on_amount_out()
        v = {k: self.ent[k].get().strip() for k, _, _ in FIELDS}
        if not v["상호"]:
            return self.warn("상호를 적어 주세요.", "상호")
        if len(B.숫자만(v["등록번호"])) != 10:
            return self.warn("등록번호는 숫자 10자리예요.\n다시 확인해 주세요.", "등록번호")
        if not B.등록번호_검사(v["등록번호"]):
            if not messagebox.askyesno("등록번호 확인", f"{v['등록번호']}\n\n등록번호가 틀린 것 같아요.\n"
                                       "숫자를 다시 한 번 봐 주세요.\n\n그래도 이대로 저장할까요?", icon="warning"):
                self.ent["등록번호"].focus_set()
                return
        amount = int(B.숫자만(v["금액"]) or 0)
        if amount <= 0:
            return self.warn("금액을 적어 주세요.", "금액")
        if v["이메일"] and "@" not in v["이메일"]:
            return self.warn("이메일에 @ 가 없어요.", "이메일")

        row = {**v, "금액": amount, "등록번호": B.등록번호_모양(v["등록번호"])}
        if not self.reload_rows():
            return
        if self.editing is not None:
            old = self.rows[self.editing]
            if old.get("상태") == "발급완료":
                return self.warn("이미 발급한 계산서라 고칠 수 없어요.\n(홈택스에서 수정발급 해야 해요)")
            if old.get("상태") == B.확인필요:  # 고쳐서 저장하면 다시 발급 대상
                row.update({"상태": "", "승인번호": ""})
            old.update(row)
        else:
            for r in self.rows:
                if B.숫자만(r["등록번호"]) == B.숫자만(row["등록번호"]) and str(r.get("비고", "")) == row["비고"] \
                        and int(r["금액"]) == amount:
                    if not messagebox.askyesno("같은 것 있음", "똑같은 거래처·금액이 이미 있어요.\n한 번 더 넣을까요?"):
                        return
            row.update({"입력한 날": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "상태": "", "승인번호": "", "발급한 날": ""})
            self.rows.append(row)
        try:
            B.쓰기(self.y, self.m, self.rows)
        except PermissionError:
            return self.warn("엑셀 파일이 열려 있어서 저장을 못 했어요.\n엑셀을 닫고 다시 눌러 주세요.")
        self.known = B.예전_거래처()
        self.refresh()
        self.clear()
        self.flash("저장했어요 ✔")

    def delete(self):
        sel = self.tree.selection()
        if not sel:
            return self.warn("지울 줄을 아래 목록에서 먼저 눌러 주세요.")
        self.editing_key = self.row_key(self.rows[int(sel[0])])
        self.editing = int(sel[0])
        if not self.reload_rows():
            return
        i = self.editing
        r = self.rows[i]
        if r.get("상태") == "발급완료":
            return self.warn("이미 발급한 계산서는 지울 수 없어요.")
        if messagebox.askyesno("삭제", f"{r['상호']}  {int(r['금액']):,}원\n\n이 줄을 지울까요?"):
            del self.rows[i]
            B.쓰기(self.y, self.m, self.rows)
            self.refresh()
            self.clear()

    def warn(self, msg, focus=None):
        messagebox.showwarning("확인해 주세요", msg)
        if focus:
            self.ent[focus].focus_set()

    def flash(self, msg):
        lab = tk.Label(self.frame, text=msg, font=(F, fs(26), "bold"), bg="#C6EFCE", fg="#006100")
        lab.place(relx=0.5, rely=0.5, anchor="center")
        self.after(1200, lab.destroy)

    # ───────────── 자동 업데이트 ─────────────
    def check_update(self):
        import threading
        import 업데이트 as U
        U.옛날파일_정리(HERE)
        token = ""  # 저장소가 공개라 토큰 없이 받음

        def work():
            try:
                tag, assets = U.새버전_확인(token)
            except Exception:
                return  # 인터넷이 안 되거나 하면 그냥 지금 버전으로
            if tag:
                self.after(0, lambda: self.do_update(tag, assets, token))
        threading.Thread(target=work, daemon=True).start()

    def do_update(self, tag, assets, token):
        import threading
        import 업데이트 as U
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq 홈택스발급.exe"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if "홈택스발급.exe" in r.stdout.decode("cp949", "replace"):
            return  # 발급 중이면 다음에 켤 때 업데이트
        box = tk.Toplevel(self)
        box.title("업데이트")
        box.configure(bg="white")
        box.attributes("-topmost", True)
        box.geometry(f"+{self.winfo_screenwidth() // 2 - 300}+{self.winfo_screenheight() // 2 - 100}")
        tk.Label(box, text=f"새 버전({tag})으로 바꾸는 중이에요", font=(F, fs(24), "bold"), bg="white"
                 ).pack(padx=40, pady=(30, 10))
        msg = tk.Label(box, text="잠깐만 기다려 주세요. 끝나면 다시 켜져요.", font=MID, bg="white", fg="#555")
        msg.pack(padx=40, pady=(0, 30))
        box.grab_set()

        def work():
            try:
                U.받아서_바꾸기(HERE, token, assets, 진행=lambda t: self.after(0, lambda: msg.config(text=t)))
                self.after(0, lambda: (U.다시켜기(HERE), self.destroy()))
            except Exception as e:
                err = str(e)[:80]
                self.after(0, lambda: (box.destroy(), messagebox.showwarning(
                    "업데이트", "업데이트를 못 했어요. 지금 버전으로 계속 쓸 수 있어요.\n(" + err + ")")))
        threading.Thread(target=work, daemon=True).start()

    # ───────────── 발급 ─────────────
    def issue(self):
        by, bm = B.발급할_달()
        남은 = [r for r in B.읽기(by, bm) if r.get("상태") not in ("발급완료", B.확인필요)]
        if not 남은:
            return messagebox.showinfo("발급", f"{bm}월 식대는 발급할 게 없어요.\n(다 발급했거나 입력한 게 없어요)")
        lst = "\n".join(f"  · {r['상호']}  {int(r['금액']):,}원 {r.get('비고', '')}" for r in 남은[:12])
        if not messagebox.askyesno("세금계산서 발급", f"{bm}월 식대 {len(남은)}건을 발급합니다.\n\n{lst}\n\n"
                                   "곧 휴대폰 카카오톡으로 인증 요청이 갑니다.\n시작할까요?"):
            return
        subprocess.Popen(발급_명령(), cwd=HERE,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.iconify()


if __name__ == "__main__":
    App().mainloop()


