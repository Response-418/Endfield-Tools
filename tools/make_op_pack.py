# -*- coding: utf-8 -*-
"""干员包制作工具 —— 把散装素材打成 EndfieldRotPilot 能导入的 operators_*.zip

用法：双击 D:\\end_supply\\制作干员包.bat
只生成 zip；或点「打包并导入」直接推给正在运行的 RotPilot（走 /api/import_operator）。

输出默认在 D:\\end_supply\\op_packs\\
"""
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile

from tkinter import Tk, ttk, StringVar, BooleanVar, filedialog, messagebox
from tkinter import Frame, Label, Entry, Button, Text, END, DISABLED, NORMAL
from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(BASE, "core")
sys.path.insert(0, CORE)
try:
    import app as core
    ELEMENT_COLORS = core.ELEMENT_COLORS
except Exception:
    ELEMENT_COLORS = {
        "寒冷": (32, 192, 208), "自然": (192, 224, 80), "电磁": (240, 192, 0),
        "灼热": (240, 96, 64), "物理": (110, 114, 120),
    }

OUT_DIR = r"D:\end_supply\op_packs"
KINDS = (("avatar", "头像/立绘  avatar.png"),
         ("skill", "战技符号  skill.png"),
         ("link", "连携符号  link.png"),
         ("ult", "终结符号  ult.png"))
ELEMENTS = list(ELEMENT_COLORS.keys())
CLASSES = sorted(
    os.path.splitext(f)[0]
    for f in os.listdir(os.path.join(CORE, "classes"))
    if f.lower().endswith(".png")
)


def roster():
    p = os.path.join(CORE, "operators", "roster.json")
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def find_port():
    """扫 8777-8800，找活着的 RotPilot 实例。"""
    for port in range(8777, 8801):
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/whoami" % port, timeout=0.12) as r:
                if r.status == 200:
                    return port
        except Exception:
            pass
    return None


def safe_name(name):
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "operator"


class Maker(Tk):
    def __init__(self):
        super().__init__()
        self.title("干员包制作工具 · EndfieldRotPilot")
        self.geometry("760x690")
        self.minsize(700, 640)
        self.img_paths = {k: StringVar() for k, _ in KINDS}
        self.img_info = {}
        self.override = {k: StringVar(value="") for k in ("skill", "link", "ult")}
        self.name = StringVar()
        self.element = StringVar()
        self.cls = StringVar()
        self.outdir = StringVar(value=OUT_DIR)
        self._build()
        self.log("准备就绪。先填名字和属性，再挑素材图。")

    # ---------- UI ----------
    def _build(self):
        top = Frame(self, padx=12, pady=10)
        top.pack(fill="x")
        Label(top, text="干员名：", font=("Microsoft YaHei UI", 10)).grid(row=0, column=0, sticky="w", pady=4)
        Entry(top, textvariable=self.name, width=22, font=("Microsoft YaHei UI", 10)).grid(row=0, column=1, sticky="w", pady=4)
        Label(top, text="  属性：", font=("Microsoft YaHei UI", 10)).grid(row=0, column=2, sticky="w", pady=4)
        ttk.Combobox(top, textvariable=self.element, values=ELEMENTS, width=10,
                     font=("Microsoft YaHei UI", 10)).grid(row=0, column=3, sticky="w", pady=4)
        Label(top, text="  职业：", font=("Microsoft YaHei UI", 10)).grid(row=0, column=4, sticky="w", pady=4)
        ttk.Combobox(top, textvariable=self.cls, values=CLASSES, width=10,
                     font=("Microsoft YaHei UI", 10)).grid(row=0, column=5, sticky="w", pady=4)
        Label(top, text="属性/职业可直接输入新值", foreground="#666",
              font=("Microsoft YaHei UI", 9)).grid(row=1, column=1, columnspan=5, sticky="w")

        imgs = Frame(self, padx=12, pady=2)
        imgs.pack(fill="x")
        Label(imgs, text="素材图（avatar 必须有，其余可留空用通用符号）",
              font=("Microsoft YaHei UI", 10, "bold")).grid(
                  row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        for i, (kind, label) in enumerate(KINDS):
            Label(imgs, text=label, font=("Microsoft YaHei UI", 9),
                  anchor="w").grid(row=i + 1, column=0, sticky="w", padx=(0, 8), pady=3)
            Entry(imgs, textvariable=self.img_paths[kind], width=54,
                  font=("Microsoft YaHei UI", 9)).grid(row=i + 1, column=1, sticky="w", padx=(0, 6), pady=3)
            Button(imgs, text="浏览…", command=lambda k=kind: self._pick(k),
                   font=("Microsoft YaHei UI", 9)).grid(row=i + 1, column=2, pady=3)
            info = Label(imgs, text="未选", foreground="#999", font=("Microsoft YaHei UI", 9))
            info.grid(row=i + 1, column=3, sticky="w", padx=(8, 0))
            self.img_info[kind] = info

        ov = Frame(self, padx=12, pady=8)
        ov.pack(fill="x")
        Label(ov, text="技能单独配色（留空 = 跟本体属性）",
              font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        row = Frame(ov)
        row.pack(anchor="w", pady=4)
        for k, label in (("skill", "战技"), ("link", "连携"), ("ult", "终结")):
            Label(row, text=label + "：", font=("Microsoft YaHei UI", 9)).pack(side="left")
            ttk.Combobox(row, textvariable=self.override[k], values=[""] + ELEMENTS,
                         width=9, state="normal", font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(0, 14))

        out = Frame(self, padx=12, pady=2)
        out.pack(fill="x")
        Label(out, text="输出目录：", font=("Microsoft YaHei UI", 9)).pack(side="left")
        Entry(out, textvariable=self.outdir, width=64, font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(0, 6))
        Button(out, text="…", command=self._pick_out, width=3).pack(side="left")

        btns = Frame(self, padx=12, pady=10)
        btns.pack(fill="x")
        Button(btns, text="生成干员包 zip", command=lambda: self._build_pack(False),
               font=("Microsoft YaHei UI", 10, "bold"), height=1).pack(side="left", padx=(0, 8))
        Button(btns, text="打包并导入到 RotPilot", command=lambda: self._build_pack(True),
               font=("Microsoft YaHei UI", 10, "bold"), height=1).pack(side="left", padx=(0, 8))
        Button(btns, text="打开输出目录", command=self._open_out,
               font=("Microsoft YaHei UI", 9)).pack(side="left")

        lg = Frame(self, padx=12, pady=4)
        lg.pack(fill="both", expand=True)
        self.console = Text(lg, height=12, font=("Consolas", 9))
        self.console.pack(fill="both", expand=True, side="left")
        sc = ttk.Scrollbar(lg, command=self.console.yview)
        sc.pack(fill="y", side="right")
        self.console.configure(yscrollcommand=sc.set)

    def log(self, s):
        self.console.insert(END, s + "\n")
        self.console.see(END)
        self.update_idletasks()

    def _pick(self, kind):
        p = filedialog.askopenfilename(
            title="选择 " + dict(KINDS)[kind],
            filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")])
        if not p:
            return
        try:
            im = Image.open(p)
            w, h, mode = im.size[0], im.size[1], im.mode
            im.verify()
            self.img_paths[kind].set(p)
            self.img_info[kind].config(
                text="%d×%d %s" % (w, h, mode), foreground="#2a7d2a")
            self.log("选中 %s: %s" % (kind, p))
        except Exception as e:
            messagebox.showerror("图片无效", "%s\n%s" % (p, e))

    def _pick_out(self):
        p = filedialog.askdirectory(title="选择输出目录", initialdir=self.outdir.get())
        if p:
            self.outdir.set(p)

    def _open_out(self):
        d = self.outdir.get()
        os.makedirs(d, exist_ok=True)
        try:
            os.startfile(d)
        except Exception as e:
            self.log("打不开目录: %s" % e)

    # ---------- 打包 ----------
    def _validate(self):
        name = self.name.get().strip()
        el = self.element.get().strip()
        if not name:
            messagebox.showerror("缺字段", "请填干员名")
            return None
        if not el:
            messagebox.showerror("缺字段", "请填属性（可输入新属性名）")
            return None
        if "/" in name or "\\" in name:
            messagebox.showerror("名字非法", "干员名不能包含斜杠")
            return None
        if not self.img_paths["avatar"].get():
            messagebox.showerror("缺素材", "必须有 avatar.png（头像/立绘），否则卡面和图标角标会失败")
            return None
        for kind, _ in KINDS:
            p = self.img_paths[kind].get()
            if p and not os.path.isfile(p):
                messagebox.showerror("文件不存在", p)
                return None

        existing = roster()
        if name in existing.values():
            if not messagebox.askyesno(
                    "同名角色", "「%s」已在干员名单中。继续会覆盖它的素材（位置不变）。\n确定继续？" % name):
                return None

        if el not in ELEMENT_COLORS:
            self.log("⚠ 新属性「%s」不在 ELEMENT_COLORS 中，图标会用物理灰。"
                     "需手动在 core/app.py 加颜色映射。" % el)
        cls = self.cls.get().strip()
        if cls and not os.path.isfile(os.path.join(CORE, "classes", cls + ".png")):
            self.log("⚠ 新职业「%s」没有 core/classes/%s.png，卡面职业框会空白。" % (cls, cls))
        return name, el, cls

    def _make_zip(self, name, el, cls):
        meta = {"name": name, "element": el}
        if cls:
            meta["class"] = cls
        over = {k: v.get().strip() for k, v in self.override.items()}
        over = {k: v for k, v in over.items() if v}
        if over:
            meta["elements"] = over

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("operator.json",
                       json.dumps(meta, ensure_ascii=False, indent=2))
            for kind, _ in KINDS:
                p = self.img_paths[kind].get()
                if not p:
                    continue
                im = Image.open(p).convert("RGBA")
                b = io.BytesIO()
                im.save(b, "PNG")
                z.writestr("%s.png" % kind, b.getvalue())
        return buf.getvalue(), meta

    def _build_pack(self, install):
        v = self._validate()
        if not v:
            return
        name, el, cls = v
        try:
            data, meta = self._make_zip(name, el, cls)
        except Exception as e:
            messagebox.showerror("打包失败", str(e))
            return

        d = self.outdir.get()
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as e:
            messagebox.showerror("输出目录不可用", str(e))
            return
        fn = "operators_%s.zip" % safe_name(name)
        path = os.path.join(d, fn)
        with open(path, "wb") as f:
            f.write(data)
        self.log("✓ 已生成 %s（%d 字节）" % (path, len(data)))
        self.log("  operator.json: %s" % json.dumps(meta, ensure_ascii=False))

        if install:
            self._import(data, fn)

    def _import(self, data, fn):
        port = find_port()
        if not port:
            messagebox.showwarning(
                "没找到运行中的程序",
                "8777-8800 上没检测到 RotPilot。\n"
                "zip 已生成，可以先启动 RotPilot，再用界面里的「添加干员」选它。")
            return
        url = "http://127.0.0.1:%d/api/import_operator" % port
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/zip",
                     "X-Filename": urllib.parse.quote(fn)})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)
        except Exception as e:
            messagebox.showerror("导入失败", "%s\n\nzip 已生成，可手动导入。" % e)
            return
        if res.get("ok"):
            self.log("✓ 导入成功：%s（slot %s, %s %s）" % (
                res.get("name"), res.get("slot"), res.get("element"), res.get("class")))
            messagebox.showinfo("导入成功", "已加入干员：%s\n位置 %s" % (
                res.get("name"), res.get("slot")))
        else:
            self.log("✗ 导入失败：%s" % res.get("error"))
            messagebox.showerror("导入失败", str(res.get("error")))


if __name__ == "__main__":
    Maker().mainloop()
