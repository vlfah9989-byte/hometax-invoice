# -*- coding: utf-8 -*-
"""월별 거래처 장부 (엑셀) 읽기/쓰기 - 입력 화면과 발급 프로그램이 같이 씀"""
import datetime
import glob
import sys
import os
import re

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

_BASE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
# 코드가 "소스코드" 폴더에 있으면 장부·설정·기록은 한 단계 위(프로그램 폴더)에 있는 걸 같이 씀
HERE = os.path.dirname(_BASE) if os.path.basename(_BASE) == "소스코드" else _BASE
장부폴더 = os.path.join(HERE, "거래처기록")

COLS = ["번호", "상호", "등록번호", "성명", "금액", "비고", "작성일자", "주소", "이메일",
        "입력한 날", "상태", "승인번호", "발급한 날"]
WIDTH = [6, 26, 15, 16, 13, 10, 12, 40, 26, 17, 10, 28, 17]


def 입력할_달(today=None):
    """1~24일 → 저번 달, 25일~말일 → 이번 달"""
    today = today or datetime.date.today()
    if today.day >= 25:
        return today.year, today.month
    prev = today.replace(day=1) - datetime.timedelta(days=1)
    return prev.year, prev.month


def 발급할_달(today=None):
    """발급은 항상 저번 달 (작성일자 = 저번 달 말일)"""
    today = today or datetime.date.today()
    prev = today.replace(day=1) - datetime.timedelta(days=1)
    return prev.year, prev.month


def 말일(year, month):
    import calendar
    return datetime.date(year, month, calendar.monthrange(year, month)[1])


def 날짜_읽기(s, year, month):
    """장부의 '작성일자' 칸 → date. 비어 있으면 None(= 그달 말일).
    '11/1', '11.1', '1101', '2026-11-01', '20261101', '1'(그달 1일) 다 알아들음.
    이상하면 ValueError (아버지 화면에 보여줄 설명)"""
    if isinstance(s, datetime.datetime):
        s = s.date()
    if isinstance(s, datetime.date):
        d = s
    else:
        t = str(s or "").strip()
        if not t:
            return None
        parts = [int(x) for x in re.findall(r"\d+", t)]
        try:
            if len(parts) == 3:
                y, m, dd = parts
                d = datetime.date(y + 2000 if y < 100 else y, m, dd)
            elif len(parts) == 2:
                d = _가까운_해(parts[0], parts[1], year, month)
            elif len(parts) == 1:
                x = str(parts[0]) if not t.isdigit() else t
                if len(x) <= 2:
                    d = datetime.date(year, month, int(x))
                elif len(x) in (3, 4):
                    d = _가까운_해(int(x[:-2]), int(x[-2:]), year, month)
                elif len(x) == 8:
                    d = datetime.date(int(x[:4]), int(x[4:6]), int(x[6:]))
                else:
                    raise ValueError
            else:
                raise ValueError
        except ValueError:
            raise ValueError(f"날짜를 못 알아봤어요: {t}" + "\n" + "(예: 11/1 처럼 월/일로 적어 주세요)")
    기준 = 말일(year, month)
    if not (-40 <= (d - 기준).days <= 62):
        raise ValueError(f"날짜가 {month}월 장부와 너무 떨어져 있어요: {d.month}월 {d.day}일" + "\n" + "다시 확인해 주세요.")
    return d


def _가까운_해(m, dd, year, month):
    """월/일만 있으면 장부 달에 제일 가까운 해로 (12월 장부에 1/5 → 다음 해)"""
    기준 = 말일(year, month)
    cands = []
    for y in (year - 1, year, year + 1):
        try:
            cands.append(datetime.date(y, m, dd))
        except ValueError:
            pass
    if not cands:
        raise ValueError
    return min(cands, key=lambda d: abs((d - 기준).days))


def 작성일(row, year, month):
    """그 줄의 작성일자 (비어 있으면 그달 말일)"""
    return 날짜_읽기(row.get("작성일자"), year, month) or 말일(year, month)


def 날짜_저장값(s, year, month):
    """입력 화면에서 받은 날짜 → 장부에 적을 값. 말일과 같거나 비었으면 '' (기본)"""
    d = 날짜_읽기(s, year, month)
    return "" if d is None or d == 말일(year, month) else d.strftime("%Y-%m-%d")


def 장부_경로(year, month):
    return os.path.join(장부폴더, f"{year}년 {month:02d}월.xlsx")


def 숫자만(s):
    return re.sub(r"\D", "", str(s or ""))


def 등록번호_모양(s):
    d = 숫자만(s)
    return f"{d[:3]}-{d[3:5]}-{d[5:]}" if len(d) == 10 else str(s or "").strip()


def 등록번호_검사(s):
    """사업자등록번호 끝자리 검증 (오타 찾기)"""
    d = [int(x) for x in 숫자만(s)]
    if len(d) != 10:
        return False
    w = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    total = sum(a * b for a, b in zip(d[:9], w)) + (d[8] * 5) // 10
    return (10 - total % 10) % 10 == d[9]


def 읽기(year, month):
    path = 장부_경로(year, month)
    if not os.path.exists(path):
        return []
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    head = [c.value for c in ws[1]]
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not any(r):
            continue
        row = {h: ("" if v is None else v) for h, v in zip(head, r)}
        row["금액"] = int(숫자만(row.get("금액")) or 0)
        rows.append(row)
    return rows


def 쓰기(year, month, rows):
    os.makedirs(장부폴더, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{month}월 식대"
    ws.append(COLS)
    big = Font(size=12)
    for i, c in enumerate(ws[1]):
        c.font = Font(size=12, bold=True)
        c.fill = PatternFill("solid", fgColor="DDEBF7")
        c.alignment = Alignment(horizontal="center")
        ws.column_dimensions[openpyxl.utils.get_column_letter(i + 1)].width = WIDTH[i]
    for n, row in enumerate(rows, 1):
        row["번호"] = n
        ws.append([row.get(h, "") for h in COLS])
        for c in ws[ws.max_row]:
            c.font = big
        ws.cell(ws.max_row, COLS.index("금액") + 1).number_format = "#,##0"
        if row.get("상태") == "발급완료":
            for c in ws[ws.max_row]:
                c.fill = PatternFill("solid", fgColor="E2EFDA")
        elif row.get("상태") == 확인필요:
            for c in ws[ws.max_row]:
                c.fill = PatternFill("solid", fgColor="FFC7CE")
                c.font = Font(size=12, color="C00000", bold=True)
    ws.freeze_panes = "A2"
    path = 장부_경로(year, month)
    wb.save(path)
    return path


확인필요 = "등록번호 확인 필요"


def 상태_표시(year, month, row_key, 상태, 메모=""):
    """row_key = (등록번호, 비고, 금액). 발급완료면 메모=승인번호, 확인필요면 메모=홈택스 알림 내용"""
    rows = 읽기(year, month)
    for r in rows:
        if (등록번호_모양(r["등록번호"]), str(r.get("비고") or "").strip(), int(r["금액"])) == row_key:
            r["상태"] = 상태
            r["승인번호"] = 메모
            r["발급한 날"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M") if 상태 == "발급완료" else ""
    쓰기(year, month, rows)


def 발급완료_표시(year, month, row_key, 승인번호):
    상태_표시(year, month, row_key, "발급완료", 승인번호)


def 예전_거래처():
    """지금까지 장부에 적은 거래처 (최근 것 우선) → 상호로 찾기용"""
    found = {}
    for path in sorted(glob.glob(os.path.join(장부폴더, "*년 *월.xlsx"))):
        m = re.search(r"(\d+)년 (\d+)월", os.path.basename(path))
        for r in 읽기(int(m.group(1)), int(m.group(2))):
            if r.get("상호"):
                found[r["상호"]] = r  # 나중 파일이 덮어씀 = 최신 정보
    return found
