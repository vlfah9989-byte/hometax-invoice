# -*- coding: utf-8 -*-
"""깃허브(비공개) 릴리스에서 새 버전을 받아 exe 를 바꿈.
설정.json·장부·보안카드·발급기록은 절대 건드리지 않음 (exe 두 개만 바꿈)."""
import json
import os
import subprocess
import sys
import urllib.request

from 버전 import 버전, 저장소

받을파일 = ("세금계산서.exe", "홈택스발급.exe")


def _ver(s):
    s = str(s).lstrip("vV")
    return tuple(int(x) if x.isdigit() else 0 for x in s.split("."))


def _get(url, token, accept="application/vnd.github+json", timeout=15):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "hometax-invoice-updater"})
    return urllib.request.urlopen(req, timeout=timeout)


def 새버전_확인(token):
    """(새 버전 태그, {파일이름: 다운로드 url}) 또는 (None, None)"""
    if not token:
        return None, None
    with _get(f"https://api.github.com/repos/{저장소}/releases/latest", token) as r:
        rel = json.load(r)
    tag = rel.get("tag_name", "")
    if _ver(tag) <= _ver(버전):
        return None, None
    assets = {a["name"]: a["url"] for a in rel.get("assets", []) if a.get("name") in 받을파일}
    if set(assets) != set(받을파일):
        return None, None
    return tag, assets


def 받아서_바꾸기(here, token, assets, 진행=None):
    """새 exe 를 .new 로 받은 뒤 바꿔 끼움. 지금 켜져 있는 자기 자신은 이름을 .old 로 바꾸고 교체."""
    받은것 = {}
    for name, url in assets.items():
        dst = os.path.join(here, name + ".new")
        if 진행:
            진행(f"{name} 받는 중...")
        with _get(url, token, accept="application/octet-stream", timeout=120) as r, open(dst, "wb") as f:
            while True:
                b = r.read(1024 * 256)
                if not b:
                    break
                f.write(b)
        if os.path.getsize(dst) < 1_000_000:  # 너무 작으면 잘못 받은 것
            raise RuntimeError(f"{name} 다운로드가 이상해요")
        받은것[name] = dst
    me = os.path.abspath(sys.executable)
    for name, new in 받은것.items():
        cur = os.path.join(here, name)
        old = cur + ".old"
        if os.path.exists(old):
            try:
                os.remove(old)
            except OSError:
                pass
        if os.path.exists(cur):
            os.replace(cur, old)  # 켜져 있는 exe 도 이름 바꾸기는 됨
        os.replace(new, cur)
    return me


def 옛날파일_정리(here):
    for name in 받을파일:
        old = os.path.join(here, name + ".old")
        if os.path.exists(old):
            try:
                os.remove(old)
            except OSError:
                pass


def 다시켜기(here):
    subprocess.Popen([os.path.join(here, "세금계산서.exe")], cwd=here)
