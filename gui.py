"""B站视频下载器 · 桌面版（tkinter）

复用项目内的 config.py / strategy / models，不新增第三方依赖。
运行：双击「启动下载器.bat」，或 pythonw gui.py
"""

import os
import re
import sys
import queue
import shutil
import asyncio
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, BASE)

# ffmpeg 位置：优先用 PATH，其次读环境变量 BILI_FFMPEG_DIR（填到 ffmpeg 所在的目录）
_FFMPEG_DIR = os.environ.get("BILI_FFMPEG_DIR", "").strip()
if _FFMPEG_DIR and os.path.isdir(_FFMPEG_DIR):
    if _FFMPEG_DIR.lower() not in os.environ.get("PATH", "").lower():
        os.environ["PATH"] = _FFMPEG_DIR + os.sep + os.environ.get("PATH", "")

import config  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36 Edg/108.0.1462.46")

QUALITY_FALLBACK = {
    127: "8K 超高清", 126: "杜比视界 4K", 125: "HDR 4K", 120: "4K 超清",
    116: "1080P60", 112: "1080P+", 80: "1080P", 74: "720P60",
    64: "720P", 32: "480P", 16: "360P",
}

# 下拉框选项 → 画质 id（None 表示自动取最高可用）
QUALITY_OPTIONS = {
    "自动（最高可用）": None,
    "8K 超高清": 127,
    "杜比视界 4K": 126,
    "4K 超清": 120,
    "1080P60": 116,
    "1080P+": 112,
    "1080P": 80,
    "720P60": 74,
    "720P": 64,
    "480P": 32,
    "360P": 16,
}


def _headers(cookie: str, referer: str = "https://www.bilibili.com/") -> dict:
    return {
        "cookie": cookie,
        "referer": referer,
        "origin": "https://www.bilibili.com",
        "user-agent": UA,
        "accept": "*/*",
    }


def _safe_name(title: str) -> str:
    return re.sub(r'[<>:"\\/|?*]', "", title).strip()


def _part_no(url: str) -> int:
    m = re.search(r"[?&]p=(\d+)", url)
    return int(m.group(1)) if m else 1


def _quality_id_from_label(label: str):
    return QUALITY_OPTIONS.get(label, None)


def choose_stream(streams, want_id):
    """按偏好挑流：优先精确匹配，其次向下兼容，最后退到最低档"""
    if not streams:
        raise ValueError("没有可下载的视频流")
    ids = sorted({s["id"] for s in streams}, reverse=True)
    if want_id is None:
        target = ids[0]
    elif want_id in ids:
        target = want_id
    else:
        lower = [i for i in ids if i <= want_id]
        target = lower[0] if lower else ids[-1]
    picked = [s for s in streams if s["id"] == target]
    # 同档位里优先 AVC（Windows 播放器兼容性更好）
    picked.sort(key=lambda s: 0 if str(s.get("codec", "")).lower().startswith("avc") else 1)
    return picked[0], target


class ItemProgress:
    """按总字节数估算进度，未知长度时按阶段均值退让"""

    def __init__(self, stages: int = 2):
        self.stages = stages
        self.total = {}
        self.got = {}

    def bump(self, stage: str, got: int, total: int) -> int:
        self.got[stage] = got
        if total:
            self.total[stage] = total
        known = sum(v for v in self.total.values() if v)
        if known:
            return min(99, int(sum(self.got.values()) / known * 100))
        return min(99, int(len([k for k in self.got]) / self.stages * 100))


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.items: dict[str, dict] = {}
        self.worker = None
        self.stop_flag = threading.Event()
        self.open_when_done = True
        self.want_qid = None
        self.executor = None

        root.title("B站视频下载器")
        root.geometry("1040x690")
        root.minsize(900, 620)

        style = ttk.Style()
        for theme in ("vista", "winnative", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Hint.TLabel", foreground="#5B6B78")
        style.configure("Ok.TLabel", foreground="#2F6B52")
        style.configure("Bad.TLabel", foreground="#A33")

        self._build()
        self.root.after(120, self._poll)

    # ---------------- 界面 ----------------
    def _build(self):
        pad = {"padx": 10, "pady": 6}

        top = ttk.LabelFrame(self.root, text="账号 Cookie（决定能否下载 1080P 及以上）")
        top.pack(fill="x", **pad)

        row = ttk.Frame(top)
        row.pack(fill="x", padx=10, pady=(8, 4))

        text_wrap = ttk.Frame(row)
        text_wrap.pack(side="left", fill="both", expand=True)
        self.cookie_text = tk.Text(text_wrap, height=4, wrap="char", font=("Consolas", 9),
                                   relief="solid", borderwidth=1, undo=True)
        self.cookie_text.insert("1.0", config.COOKIE)
        csb = ttk.Scrollbar(text_wrap, orient="vertical", command=self.cookie_text.yview)
        self.cookie_text.configure(yscrollcommand=csb.set)
        self.cookie_text.pack(side="left", fill="both", expand=True)
        csb.pack(side="left", fill="y")

        bar = ttk.Frame(row)
        bar.pack(side="left", fill="y", padx=(8, 0))
        ttk.Button(bar, text="粘贴", width=9, command=self.paste_cookie).pack(fill="x")
        ttk.Button(bar, text="保存", width=9, command=self.save_cookie).pack(fill="x", pady=4)
        ttk.Button(bar, text="检查登录", width=9, command=self.check_login).pack(fill="x")

        self.login_label = ttk.Label(top, text="未检查", style="Hint.TLabel")
        self.login_label.pack(anchor="w", padx=12, pady=(0, 8))

        url_box = ttk.LabelFrame(self.root, text="视频链接（一行一个，支持分P，用 ?p=2 指定）")
        url_box.pack(fill="both", expand=False, **pad)

        body = ttk.Frame(url_box)
        body.pack(fill="both", expand=True, padx=10, pady=8)

        self.url_text = tk.Text(body, height=5, wrap="none", font=("Microsoft YaHei UI", 10),
                                relief="solid", borderwidth=1)
        self.url_text.pack(side="left", fill="both", expand=True)
        bar = ttk.Frame(body)
        bar.pack(side="left", fill="y", padx=(8, 0))
        ttk.Button(bar, text="粘贴剪贴板", width=14, command=self.paste_clip).pack(fill="x")
        ttk.Button(bar, text="解析", width=14, command=self.parse_urls).pack(fill="x", pady=4)
        ttk.Button(bar, text="清空链接", width=14, command=lambda: self.url_text.delete("1.0", "end")).pack(fill="x")

        list_box = ttk.LabelFrame(self.root, text="下载队列")
        list_box.pack(fill="both", expand=True, **pad)

        cols = ("title", "quality", "status", "progress")
        self.tree = ttk.Treeview(list_box, columns=cols, show="headings", height=8, selectmode="browse")
        for key, text, width, anchor in (
            ("title", "标题", 520, "w"),
            ("quality", "画质", 110, "center"),
            ("status", "状态", 130, "center"),
            ("progress", "进度", 80, "center"),
        ):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "title"))
        vsb = ttk.Scrollbar(list_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=8)
        vsb.pack(side="left", fill="y", pady=8, padx=(0, 10))

        act = ttk.Frame(self.root)
        act.pack(fill="x", **pad)

        self.start_btn = ttk.Button(act, text="开始下载", width=14, command=self.start_download)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(act, text="停止", width=10, command=self.stop_download, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(act, text="打开输出目录", width=14, command=self.open_output).pack(side="left")
        ttk.Button(act, text="清空队列", width=12, command=self.clear_list).pack(side="left", padx=6)

        ttk.Label(act, text="画质").pack(side="left", padx=(6, 2))
        self.quality_combo = ttk.Combobox(act, values=list(QUALITY_OPTIONS.keys()),
                                          state="readonly", width=16)
        self.quality_combo.current(0)
        self.quality_combo.pack(side="left")

        self.open_after = tk.BooleanVar(value=True)
        ttk.Checkbutton(act, text="完成后打开文件夹", variable=self.open_after).pack(side="left", padx=8)

        self.overall = ttk.Progressbar(act, mode="determinate", maximum=100)
        self.overall.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.pct_label = ttk.Label(act, text="0%", width=6, anchor="e")
        self.pct_label.pack(side="left")

        log_box = ttk.LabelFrame(self.root, text="日志")
        log_box.pack(fill="both", expand=False, **pad)
        self.log_text = tk.Text(log_box, height=7, state="disabled", wrap="word",
                                font=("Consolas", 9), relief="solid", borderwidth=1)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=8)
        self.log_text.tag_config("err", foreground="#A33")
        self.log_text.tag_config("ok", foreground="#2F6B52")

    # ---------------- Cookie ----------------
    def _cookie_value(self):
        raw = self.cookie_text.get("1.0", "end")
        return " ".join(raw.split())

    def paste_cookie(self):
        try:
            clip = " ".join(self.root.clipboard_get().split())
        except tk.TclError:
            return
        if not clip:
            return
        self.cookie_text.delete("1.0", "end")
        self.cookie_text.insert("1.0", clip)
        self._log("已粘贴剪贴板内容，记得点「保存」")

    def save_cookie(self):
        cookie = self._cookie_value()
        if not cookie:
            messagebox.showwarning("提示", "Cookie 不能为空")
            return
        config.COOKIE = cookie
        if self.executor is not None:
            self.executor = self._make_executor()
        try:
            path = os.path.join(BASE, "config.py")
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            escaped = cookie.replace("\\", "\\\\").replace("'", "\\'")
            new_text, n = re.subn(r"^COOKIE = '.*?'$", "COOKIE = '%s'" % escaped, text, count=1, flags=re.M)
            if n != 1:
                raise ValueError("config.py 中没找到 COOKIE 赋值行")
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
            self._log("Cookie 已保存到 config.py，命令行模式也会同步生效")
        except Exception as ex:
            self._log("Cookie 写回 config.py 失败：%s（本次仅内存生效）" % ex, "err")

    def check_login(self):
        cookie = self._cookie_value()
        if not cookie:
            messagebox.showwarning("提示", "Cookie 不能为空")
            return
        if cookie != config.COOKIE:
            config.COOKIE = cookie
            self.executor = None

        def run():
            try:
                import httpx
                r = httpx.get("https://api.bilibili.com/x/web-interface/nav",
                              headers=_headers(cookie), timeout=15).json()
                data = r.get("data") or {}
                if data.get("isLogin"):
                    self.q.put(("login", True, "已登录：%s（%s）" % (data.get("uname"), "大会员" if data.get("vipStatus") else "普通用户")))
                else:
                    self.q.put(("login", False, "未登录（code=%s），最高只能拿 480P" % r.get("code")))
            except Exception as ex:
                self.q.put(("login", False, "检查失败：%s" % ex))

        threading.Thread(target=run, daemon=True).start()

    # ---------------- 解析 ----------------
    def _make_executor(self):
        from strategy.bilibili_executor import BilibiliExecutor
        ex = BilibiliExecutor()
        # 策略在模块导入时已实例化，这里同步最新 cookie
        for strategy in ex._strategies.values():
            if hasattr(strategy, "headers"):
                strategy.headers["cookie"] = config.COOKIE
        return ex

    def paste_clip(self):
        try:
            clip = self.root.clipboard_get()
        except tk.TclError:
            return
        self.url_text.insert("end", clip.strip() + "\n")

    def parse_urls(self):
        urls = self._read_urls()
        if not urls:
            messagebox.showinfo("提示", "请先粘贴至少一个视频链接")
            return
        self._set_busy(True, "解析中")
        threading.Thread(target=self._parse_worker, args=(urls,), daemon=True).start()

    def _read_urls(self):
        raw = self.url_text.get("1.0", "end")
        return [u.strip() for u in raw.splitlines() if u.strip()]

    def _parse_worker(self, urls):
        try:
            for u in urls:
                try:
                    item = self._parse_one(u)
                    self.q.put(("row", u, item, "已解析"))
                except Exception as ex:
                    self.q.put(("row_fail", u, str(ex).splitlines()[0]))
            self.q.put(("busy", False, "解析完成"))
        except Exception as ex:
            self.q.put(("busy", False, "解析失败：%s" % ex))

    def _parse_one(self, url):
        """直接把页面的 __playinfo__ 解开，拿到全部清晰度，而不只是最高那一个"""
        import json
        import httpx
        from bs4 import BeautifulSoup

        r = httpx.get(url, headers=_headers(config.COOKIE), follow_redirects=True, timeout=30)
        r.raise_for_status()
        bs = BeautifulSoup(r.text, "html.parser")
        h1 = bs.find("h1")
        title = h1.get_text().strip() if h1 else url
        pat = re.compile(r"window\.__playinfo__=(.*?)$", re.MULTILINE | re.DOTALL)
        sc = bs.find("script", text=pat)
        if sc is None:
            raise ValueError("页面里没有播放信息（可能未登录/无权限，或不是普通视频）")
        data = json.loads(pat.search(sc.next).group(1))["data"]

        item = {
            "title": _safe_name(title)[:90],
            "part": _part_no(url),
            "streams": [],
            "audios": [],
            "is_durl": False,
        }
        if "dash" in data:
            dash = data["dash"]
            for s in dash.get("video", []):
                item["streams"].append({
                    "id": s.get("id"), "url": s.get("baseUrl"),
                    "codec": s.get("codecs", ""), "height": s.get("height"),
                })
            item["streams"].sort(key=lambda s: (-(s["id"] or 0), 0 if str(s["codec"]).startswith("avc") else 1))
            audios = sorted(dash.get("audio", []), key=lambda a: -(a.get("bandwidth") or 0))
            item["audios"] = [{"id": a.get("id"), "url": a.get("baseUrl")} for a in audios]
            if not item["streams"]:
                raise ValueError("没有可下载的画面流（可能是音频稿或权限不足）")
        elif "durl" in data:
            item["is_durl"] = True
            durl = data["durl"][0]
            qid = data.get("quality", 32)
            item["streams"] = [{"id": qid, "url": durl["url"], "codec": "durl", "height": None}]
        else:
            raise ValueError("未找到视频数据（dash/durl 都没有）")

        item["available"] = sorted({s["id"] for s in item["streams"]}, reverse=True)
        item["best"] = item["available"][0]
        return item

    # ---------------- 下载 ----------------
    def start_download(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.items:
            self.parse_urls()
            return
        self.stop_flag.clear()
        self._set_busy(True, "下载中")
        self.overall["value"] = 0
        # 主线程读控件状态，后台线程只用快照
        self.open_when_done = bool(self.open_after.get())
        self.want_qid = _quality_id_from_label(self.quality_combo.get())
        self.worker = threading.Thread(target=self._download_worker, daemon=True)
        self.worker.start()

    def stop_download(self):
        self.stop_flag.set()
        self._log("已请求停止，当前条目结束后退出")

    def _download_worker(self):
        import httpx
        cookie = config.COOKIE
        tmp = config.TEMP_PATH
        out = config.OUTPUT_PATH
        os.makedirs(tmp, exist_ok=True)
        os.makedirs(out, exist_ok=True)

        todo = [(iid, it) for iid, it in self.items.items() if it.get("streams")]
        total = len(todo)
        ok = fail = 0

        for idx, (iid, it) in enumerate(todo, 1):
            if self.stop_flag.is_set():
                break
            title = it["title"] or "未命名"
            self.q.put(("cell", iid, "status", "下载中"))
            self.q.put(("cell", iid, "progress", "0%"))
            self.q.put(("overall", int((idx - 1) / total * 100), "%d/%d" % (idx - 1, total)))

            name = title
            if it["part"] >= 1:
                name += "_P%d" % it["part"]
            vfile = os.path.join(tmp, name + ".mp4")
            afile = os.path.join(tmp, name + ".mp3")
            final = os.path.join(out, name + ".mp4")

            try:
                stream, qid = choose_stream(it["streams"], self.want_qid)
                label = QUALITY_FALLBACK.get(qid, str(qid))
                if self.want_qid and qid != self.want_qid:
                    label = "%s（所选不可用）" % label
                self.q.put(("cell", iid, "quality", label))

                if it["is_durl"]:
                    self._fetch(stream["url"], vfile, iid, "视频", ItemProgress(1))
                else:
                    if not it["audios"]:
                        raise ValueError("没有可下载的音轨")
                    prog = ItemProgress(2)
                    self._fetch(stream["url"], vfile, iid, "视频", prog)
                    self._fetch(it["audios"][0]["url"], afile, iid, "音频", prog)

                self.q.put(("cell", iid, "status", "合并中"))
                self._merge(vfile, afile, final, it["is_durl"])
                ok += 1
                self.q.put(("cell", iid, "status", "完成"))
                self.q.put(("cell", iid, "progress", "100%"))
                self._clean(tmp)
            except Exception as ex:
                fail += 1
                self.q.put(("cell", iid, "status", "失败"))
                self.q.put(("log", "「%s」下载失败：%s" % (title[:30], ex), "err"))
            self.q.put(("overall", int(idx / total * 100), "%d/%d" % (idx, total)))

        summary = "下载结束：成功 %d，失败 %d" % (ok, fail)
        self.q.put(("busy", False, summary))
        if ok and self.open_when_done:
            self.q.put(("open_dir", None))

    def _fetch(self, url, path, iid, stage, prog):
        import httpx
        with httpx.stream("GET", url, headers=_headers(config.COOKIE), follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            got = 0
            with open(path, "wb") as f:
                for chunk in r.iter_bytes(256 * 1024):
                    if self.stop_flag.is_set():
                        raise RuntimeError("已停止")
                    f.write(chunk)
                    got += len(chunk)
                    self.q.put(("cell", iid, "progress", "%d%%" % prog.bump(stage, got, total)))

    def _merge(self, vfile, afile, final, is_durl):
        ffmpeg = shutil.which("ffmpeg")
        if is_durl or not afile or not os.path.exists(afile):
            shutil.move(vfile, final)
            return
        if ffmpeg:
            r = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                 "-i", vfile, "-i", afile, "-c:v", "copy", "-c:a", "copy",
                 "-movflags", "+faststart", final],
                capture_output=True, text=True
            )
            if r.returncode != 0:
                raise RuntimeError("ffmpeg 合并失败：%s" % (r.stderr.strip().splitlines() or ["未知错误"])[-1])
            return
        # 兜底：moviepy 重编码
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(vfile)
        clip.write_videofile(final, audio=afile, preset="ultrafast", threads=8)
        clip.close()

    @staticmethod
    def _clean(tmp):
        for f in os.listdir(tmp):
            try:
                os.remove(os.path.join(tmp, f))
            except OSError:
                pass

    # ---------------- 队列操作 ----------------
    def clear_list(self):
        for iid in list(self.items):
            self.tree.delete(iid)
        self.items.clear()
        self.overall["value"] = 0
        self.pct_label.configure(text="0%")

    def open_output(self):
        path = config.OUTPUT_PATH
        os.makedirs(path, exist_ok=True)
        os.startfile(path)  # noqa: 仅 Windows

    # ---------------- 消息循环 ----------------
    def _log(self, text, tag=None):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n", tag or ())
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log(msg[1], msg[2] if len(msg) > 2 else None)
                elif kind == "row":
                    self._add_row(msg[1], msg[2], msg[3])
                elif kind == "row_fail":
                    self._log("解析失败：%s（%s）" % (msg[1][:60], msg[2]), "err")
                elif kind == "cell":
                    iid, col, val = msg[1], msg[2], msg[3]
                    if self.tree.exists(iid):
                        self.tree.set(iid, col, val)
                    if col == "progress":
                        self.pct_label.configure(text=val)
                        try:
                            self.overall["value"] = int(val.rstrip("%"))
                        except ValueError:
                            pass
                elif kind == "overall":
                    self.overall["value"] = max(0, msg[1])
                    self.pct_label.configure(text=msg[2])
                elif kind == "login":
                    if msg[1]:
                        self.login_label.configure(text=msg[2], style="Ok.TLabel")
                    else:
                        self.login_label.configure(text=msg[2], style="Bad.TLabel")
                    self._log(msg[2], "ok" if msg[1] else "err")
                elif kind == "busy":
                    self._set_busy(msg[1], msg[2])
                elif kind == "open_dir":
                    self.open_output()
        except queue.Empty:
            pass
        self.root.after(120, self._poll)

    def _add_row(self, url, item, status):
        qids = item.get("available") or []
        best = QUALITY_FALLBACK.get(qids[0], str(qids[0])) if qids else "-"
        iid = self.tree.insert("", "end", values=(item["title"], best, status, "0%"))
        item["url"] = url
        item["status"] = status
        self.items[iid] = item

    def _set_busy(self, busy: bool, text: str = ""):
        self.start_btn.configure(state="disabled" if busy else "normal")
        self.stop_btn.configure(state="normal" if busy else "disabled")
        if text:
            self._log(text, "ok" if not busy else None)


def main():
    root = tk.Tk()
    app = App(root)  # noqa: F841
    if "--check" in sys.argv:
        root.after(900, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
