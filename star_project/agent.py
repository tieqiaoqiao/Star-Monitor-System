import os
from dotenv import load_dotenv

# ============================================================
# 加载 .env 环境变量（.env 位于项目根目录，即上一级）
# ============================================================
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver

# 导入同目录下的微博抓取工具
from .tools import fetch_weibo, fetch_comments


# ============================================================
# 核心数据结构：AI 分析结果的结构化定义
# ============================================================
class StarMonitorResult(BaseModel):
    weibo_summary: str = Field(description="微博动态的简短摘要")
    has_new_media: bool = Field(description="是否提到了新歌、新剧、新综艺（有则true，无则false）")
    media_name: str = Field(description="新作品的名字，如果没有则为'无'")
    has_haters: bool = Field(description="评论区是否有恶意攻击/黑子言论（有则true）")
    hater_comments: list[str] = Field(description="提取出的恶意评论列表，没有则为空列表")


# ============================================================
# 初始化大模型（DeepSeek）
# ============================================================
model = ChatDeepSeek(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL"),
)


# ============================================================
# 初始化 LangGraph 智能体（内存版 checkpointer + 两个微博工具）
# ============================================================
memory = InMemorySaver()

agent = create_agent(
    model=model,
    tools=[fetch_weibo, fetch_comments],
    checkpointer=memory,
)