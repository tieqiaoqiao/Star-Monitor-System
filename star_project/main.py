import os
import re
import json
import sys
import requests
import feedparser

# ============================================================
# 兼容 `python main.py` 直接运行：把项目根目录加入 sys.path
# ============================================================
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "star_project"

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 导入同包下的数据库模块与智能体模块
from .database import (
    init_db, save_message, load_history, load_all_thread_ids,
    upsert_session, get_session, load_all_sessions, delete_session,
)
from .agent import agent, model, StarMonitorResult


# ============================================================
# 初始化 FastAPI 应用并开启跨域
# ============================================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 应用启动时自动建表
@app.on_event("startup")
def on_startup():
    init_db()


# ============================================================
# 通过 UID 解析明星名字：读取微博 RSS 的 feed.title 并清洗后缀
# 解析失败返回 None，标题退化为 "{uid} 的微博监控"
# ============================================================
def fetch_star_name(uid: str):
    try:
        url = f"http://localhost:1200/weibo/user/{uid}"
        resp = requests.get(url, timeout=10)
        feed = feedparser.parse(resp.content)
        raw_title = (feed.feed.get("title") or "").strip()
        if not raw_title:
            return None
        name = re.sub(r"(的)?(微博|新浪微博)$", "", raw_title).strip()
        name = name.rstrip("的").strip()
        return name or None
    except Exception:
        return None


# 聊天接口的请求体
class ChatRequest(BaseModel):
    uid: str
    thread_id: str


# ============================================================
# 核心接口：/chat
# 流程：存用户消息 → 解析明星名字 → 写入会话标题 → 调 Agent → 结构化提取 → 落库返回
# ============================================================
@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    uid = req.uid.strip()
    thread_id = req.thread_id.strip()

    if not uid or not thread_id:
        raise HTTPException(status_code=400, detail="uid 和 thread_id 不能为空")

    save_message(thread_id, "user", uid)

    # 用明星名字生成会话标题
    star_name = fetch_star_name(uid)
    title = f"{star_name}的微博监控" if star_name else f"{uid} 的微博监控"

    # 维护 sessions 表：首次写入标题；已有默认标题时升级，不覆盖用户已有自定义
    existing = get_session(thread_id)
    if not existing:
        upsert_session(thread_id, title, uid=uid)
    else:
        if existing["title"].startswith("分析会话") or existing["title"].endswith(f"{existing['uid']} 的微博监控"):
            upsert_session(thread_id, title, uid=uid)
        elif not existing["uid"]:
            upsert_session(thread_id, existing["title"], uid=uid)

    # 调用 LangGraph 智能体（thread_id 隔离多轮记忆）
    config = {"configurable": {"thread_id": thread_id}}
    query = f"用户输入的是：{uid}。如果这是纯数字，请把它当UID查询微博并分析评论区；如果是其他问题，请结合之前的对话回答。"

    try:
        response = agent.invoke({"messages": [("user", query)]}, config=config)
        raw_text = response["messages"][-1].content

        # 用结构化输出把自由文本解析成 StarMonitorResult
        extractor = model.with_structured_output(StarMonitorResult)
        final_result = extractor.invoke(f"请从以下内容中提取信息：\n{raw_text}")

        save_message(thread_id, "assistant", final_result.model_dump())

        # 标题一起返回，前端用来更新左右两侧标题
        result = final_result.model_dump()
        result["thread_title"] = title
        return result

    except Exception as e:
        error_data = {"error": str(e), "stage": "agent_invoke"}
        save_message(thread_id, "assistant", error_data)
        raise HTTPException(status_code=500, detail=f"Agent 调用失败: {e}")


# ============================================================
# 接口：/history/{thread_id} —— 返回某个会话的全部消息
# ============================================================
@app.get("/history/{thread_id}")
def get_history(thread_id: str):
    rows = load_history(thread_id)
    messages = []
    for row in rows:
        content = row["content"]
        # assistant 存的是 JSON 字符串，尝试反序列化回对象
        if row["role"] == "assistant":
            try:
                content = json.loads(content)
            except:
                pass
        messages.append({
            "id": row["id"],
            "role": row["role"],
            "content": content,
            "created_at": row["created_at"],
        })
    return {"thread_id": thread_id, "messages": messages}


# ============================================================
# 接口：/threads —— 返回所有历史会话（优先 sessions 表，回退 messages 表）
# ============================================================
@app.get("/threads")
def get_all_threads():
    sessions = load_all_sessions()
    if sessions:
        return {"threads": [
            {"thread_id": s["thread_id"], "title": s["title"], "uid": s["uid"]}
            for s in sessions
        ]}

    thread_ids = load_all_thread_ids()
    return {"threads": [
        {"thread_id": tid, "title": f"分析会话 {tid[-4:]}", "uid": None}
        for tid in thread_ids
    ]}


# ============================================================
# 接口：DELETE /thread/{thread_id} —— 删除会话（messages + sessions）
# ============================================================
@app.delete("/thread/{thread_id}")
def delete_thread(thread_id: str):
    delete_session(thread_id)
    return {"ok": True, "thread_id": thread_id}


# ============================================================
# 本地开发启动入口
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)