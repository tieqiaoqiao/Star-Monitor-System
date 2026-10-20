import re
import requests
import feedparser
from langchain_core.tools import tool


# ============================================================
# 工具 1：抓取指定 UID 的最新微博
# ============================================================
@tool
def fetch_weibo(uid: str) -> str:
    """根据微博的 UID（一串数字）查询该用户最新的微博动态。"""
    url = f"http://localhost:1200/weibo/user/{uid}"
    try:
        # 请求 RSSHub 提供的微博 RSS 接口
        response = requests.get(url, timeout=10)
        feed = feedparser.parse(response.content)

        # 取前 5 条，并清洗掉 HTML 标签
        weibo_texts = []
        for entry in feed.entries[:5]:
            content = entry.get("summary", "") or entry.get("description", "")
            clean_content = re.sub(r'<[^>]+>', '', content)
            weibo_texts.append(clean_content.strip())

        if not weibo_texts:
            return f"未查到该 UID（{uid}）的微博。"
        return "\n".join(weibo_texts)
    except Exception as e:
        return f"抓取失败：{e}"


# ============================================================
# 工具 2：抓取评论区（当前为模拟数据）
# ============================================================
@tool
def fetch_comments(uid: str) -> str:
    """查询指定 UID 最新微博的评论区内容。（模拟数据）"""
    return f"""
    【该博主的评论区】：
    1. 哥哥太帅了，新歌必听！
    2. 只有我觉得他这次造型很丑吗？吐了。
    3. 期待新单曲，买爆！
    4. 唱得真难听，粉丝别吹了。
    5. 永远支持你！
"""