# 깃허브 빌드 때 태그(v1.0.1 등)를 버전.py 에 적음
import sys

tag = sys.argv[1].lstrip("vV")
path = "버전.py"
lines = open(path, encoding="utf-8").read().splitlines()
lines = [f'버전 = "{tag}"' if l.startswith("버전 =") else l for l in lines]
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("version ->", tag)
