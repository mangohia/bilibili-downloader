import os

# 程序根目录（请勿修改）
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
# 文件临时输出目录
TEMP_PATH = os.path.join(BASE_PATH, "temp")
# 视频输出目录
OUTPUT_PATH = os.path.join(BASE_PATH, "output")

# ============================================================
# B 站登录 Cookie
# 1. 浏览器登录 bilibili.com，打开任意视频页
# 2. F12 -> 网络(Network) -> Ctrl+R 刷新 -> 点第一条 document 请求
# 3. 右侧「标头/Headers」->「请求标头」-> 复制 cookie 整行的值
# 4. 粘贴到下面引号内（整行原样，不要换行）
# 有效期内可下载 1080P / 大会员画质；未登录或过期时只能拿 480P / 360P
# ============================================================
COOKIE = ''

# 要下载的视频链接，一行一个
# 普通视频:  https://www.bilibili.com/video/BV1xxxxxxxxx/
# 分P视频:  https://www.bilibili.com/video/BV1xxxxxxxxx/?p=2
# 命令行模式（python main.py）只读这个列表；GUI 模式在界面里粘贴链接即可
URL = [
    # 'https://www.bilibili.com/video/BV1xxxxxxxxx/',
]
