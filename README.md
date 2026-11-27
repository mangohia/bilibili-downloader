# Bilibili 视频下载器

一个能下载 B 站视频的小工具，同时提供**命令行**和**桌面窗口**两种用法。支持选择清晰度、分 P 视频、批量下载、音视频自动合并。

> 仅供个人学习与本地备份使用，请勿用于任何商业用途或二次传播，遵守 B 站用户协议与相关法律法规。

---

## 功能

- B 站普通视频、分 P 视频下载
- 手动选择清晰度（8K / 4K / 1080P60 / 1080P+ / 1080P / 720P60 / 720P / 480P / 360P），也可设为「自动取最高可用」
- 依赖登录 Cookie，可下载 1080P 及以上、大会员画质、充电专属视频
- 音视频分离下载后无损封装合并（`ffmpeg -c copy`，不重编码）
- 异步并发下载，带进度条
- 桌面版：可视化队列、逐条进度、日志、一键打开输出目录

## 目录结构

```
bilibili-downloader/
├─ main.py                     # 命令行入口
├─ gui.py                      # 桌面版入口（tkinter）
├─ config.py                   # Cookie 与链接配置
├─ requirements.txt            # 依赖
├─ 启动下载器.bat              # Windows 双击启动 GUI
├─ models/
│  ├─ category.py              # 视频分类常量
│  └─ video.py                 # 视频对象（标题/画质/直链）
├─ strategy/
│  ├─ bilibili_strategy.py     # 策略基类
│  ├─ bilibili_executor.py     # 解析器 + 下载器 + 音视频合并
│  ├─ default.py               # 普通视频解析（dash / durl）
│  └─ bangumi.py               # 番剧 / 影视解析（未完全验证）
└─ docs/                       # README 配图
```

## 安装

```bash
git clone https://github.com/<your-name>/bilibili-downloader.git
cd bilibili-downloader
pip install -r requirements.txt
```

另外需要 **ffmpeg**（用于音视频封装，不是 Python 包）：

- Windows：`winget install Gyan.FFmpeg`，或从 https://www.gyan.dev/ffmpeg/builds/ 下载后把 `bin` 目录加到 PATH
- macOS：`brew install ffmpeg`
- Linux：`sudo apt install ffmpeg`

没有 ffmpeg 时会退回 moviepy 重编码兜底，速度慢且会损失画质，建议装上。

## 配置 Cookie

登录状态决定你能拿到的最高画质，未登录只能到 480P / 360P。

1. 浏览器登录 https://www.bilibili.com ，打开任意视频页
2. `F12` 打开开发者工具 → **网络 / Network** → `Ctrl+R` 刷新
3. 点击列表里第一条 **document** 请求（名称通常是 `BVxxxx`）
4. 右侧 **标头 / Headers** → **请求标头 / Request Headers** → 复制 `cookie:` 这一行右侧的**完整值**
5. 粘贴到 `config.py` 的 `COOKIE = ''` 引号内（整行原样，不要换行）

Cookie 大约 30 天失效，失效后重新取一次即可。

> 快捷替代方案：在浏览器 **控制台 / Console** 执行 `document.cookie`，右键结果「复制字符串内容」。若结果里没有 `SESSDATA`（被设为 HttpOnly），仍按上面的网络面板方式取。

## 命令行用法

把视频链接填进 `config.py` 的 `URL` 列表（一行一个），然后：

```bash
python main.py
```

下载完成后的文件在 `output/`，失败的链接会写入 `failed_urls.txt`，便于修正后重跑。

## 桌面版用法

Windows 双击 `启动下载器.bat`，或：

```bash
pythonw gui.py
```

窗口里：

1. 顶部粘贴 Cookie → 「保存」→「检查登录」（变绿说明 cookie 有效）
2. 中间粘贴视频链接（一行一个，分 P 用 `?p=2`）→「解析」
3. 底部「画质」下拉选择清晰度 → 「开始下载」
4. 队列里看逐条状态与进度，完成后可「打开输出目录」

如果所选画质当前不可用（例如 cookie 未登录只有 480P），会自动退到最接近的较低档，并在画质列标注「所选不可用」。

## 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| 画质只有 480P / 360P | Cookie 未生效或已过期，重新取 Cookie 并点「检查登录」 |
| `页面里没有播放信息` | 链接不是普通视频（番剧/课程），或视频已下架、需要更高权限 |
| 合并后没有声音 | 检查 ffmpeg 是否在 PATH 中（`ffmpeg -version`） |
| 下载中断 / 卡住 | 网络或 B 站风控，稍后重试；也可换 cookie |
| 文件名带奇怪字符 | 标题中的非法字符会自动清理 |

## 支持情况

- [x] 普通视频 / 分 P 视频
- [x] 充电专属视频（需已购买的 cookie）
- [x] 清晰度手动选择
- [ ] 番剧 / 纪录片（`strategy/bangumi.py` 未完全验证）
- [ ] 代理支持

## 免责声明

本项目仅用于个人学习与技术研究，请勿用于侵犯版权、批量抓取或任何商业用途。下载内容请在 24 小时内删除或仅作个人备份。因使用本项目产生的一切后果由使用者自行承担。

## License

见 [LICENSE](LICENSE)。
