# -*- coding: utf-8 -*-
"""把本地定制补丁应用到 EndfieldRotPilot 的 app_web.py。

用法（在项目根目录）：
    runtime\\python.exe patches\\apply_custom.py            # 自动判定
    runtime\\python.exe patches\\apply_custom.py --force    # 官方新版时，用定制快照覆盖
    runtime\\python.exe patches\\apply_custom.py --reject   # 官方新版时，尽量打补丁，冲突写 .rej

状态判定：
  1) app_web.py 含 LOCAL_CUSTOM_VERSION  -> 已打补丁，跳过
  2) app_web.py 与 v1.4.1 官方基线一致   -> 直接 git apply custom.patch
  3) 其它（多半是官方更新到了新版）      -> 不自动动，按参数提示/覆盖/生成 .rej
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
APP = os.path.join(BASE, "app_web.py")
ORIG = os.path.join(HERE, "app_web.v1.4.1.orig.py")
PATCH = os.path.join(HERE, "custom.patch")
SNAPSHOT = os.path.join(HERE, "app_web.custom.py")
BACKUP = os.path.join(HERE, "app_web.before_patch.py")
MARK = "LOCAL_CUSTOM_VERSION"


def norm(path):
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def sha(data):
    return hashlib.sha256(data).hexdigest()[:12]


def mark_version(data):
    m = re.search(rb'LOCAL_CUSTOM_VERSION\s*=\s*"([^"]+)"', data)
    return m.group(1).decode("utf-8", "ignore") if m else "?"


def main():
    args = sys.argv[1:]
    force = "--force" in args
    reject = "--reject" in args

    for p in (APP, ORIG, PATCH, SNAPSHOT):
        if not os.path.exists(p):
            print("[错误] 缺少文件：%s" % p)
            return 1

    cur = norm(APP)
    if MARK.encode("ascii") in cur:
        print("[跳过] 已打本地补丁 %s，无需操作。" % mark_version(cur))
        return 0

    orig = norm(ORIG)
    target = norm(SNAPSHOT)
    if sha(cur) == sha(orig):
        print("[判定] 当前是 v1.4.1 官方原版，应用补丁...")
    else:
        print("[判定] 当前 app_web.py 与 v1.4.1 基线不同（哈希 %s vs %s），"
              "多半是官方已更新。" % (sha(cur), sha(orig)))
        if reject:
            print("[模式] --reject：尽量打补丁，冲突写入 app_web.py.rej")
        elif force:
            print("[模式] --force：用定制快照覆盖（会丢掉这个官方版本的新改动）")
            shutil.copy2(APP, BACKUP)
            shutil.copy2(SNAPSHOT, APP)
            print("[完成] 已用定制快照覆盖原文件。备份：%s" % BACKUP)
            print("[注意] APP_VERSION 仍是 v1.4.1，官方新版的功能不会保留。")
            return 0
        else:
            print("[停止] 为避免误伤，未改动任何文件。可选：")
            print("   --force   用定制快照覆盖（简单，丢官方新功能）")
            print("   --reject  尽量打补丁，冲突生成 .rej 供手工合并")
            print("   或先对比差异：git diff --no-index %s %s" % (ORIG, APP))
            return 2

    shutil.copy2(APP, BACKUP)
    cmd = ["git", "apply", "--whitespace=nowarn"]
    if reject:
        cmd.append("--reject")
    cmd.append(PATCH)
    try:
        r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True)
    except Exception as e:
        print("[错误] 无法运行 git：%s" % e)
        return 3
    if r.returncode != 0:
        print("[失败] git apply 返回 %d" % r.returncode)
        if r.stderr.strip():
            print(r.stderr.strip())
        print("原文件已备份到：%s" % BACKUP)
        return 3

    after = norm(APP)
    if sha(after) == sha(target):
        print("[完成] 补丁应用成功，内容与定制快照一致（%s）。" % sha(after))
    else:
        print("[警告] 补丁已应用，但结果与定制快照不同（%s vs %s）。"
              % (sha(after), sha(target)))
        print("请检查 app_web.py 与 patches/app_web.custom.py 的差异。")
    print("备份：%s" % BACKUP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
