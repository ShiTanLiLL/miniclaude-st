"""和大模型 API 打交道的最小封装。

第 1 课只做一件事：从 .env 读配置，造一个 Anthropic 客户端。
真正的对话循环不在这里——见 loop.py。
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv


def get_client() -> Anthropic:
    """读 .env，返回一个可用的模型客户端。

    两处小讲究：
    - 配置读取放在函数里而不是模块顶层，"导入本模块"和"联网"就是两件事，
      离线测试导入它不需要任何环境变量；
    - 用了自定义 BASE_URL 时清掉 AUTH_TOKEN，避免 SDK 优先拿错凭证。
    """
    load_dotenv(override=True)
    if os.getenv("ANTHROPIC_BASE_URL"):
        os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    return Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))


def get_model() -> str:
    """读 .env 里的 MODEL_ID，没配置就给出人话提示并退出。"""
    load_dotenv(override=True)
    try:
        return os.environ["MODEL_ID"]
    except KeyError:
        raise SystemExit("缺少 MODEL_ID：请复制 .env.example 为 .env 并填写（参考教案第 1 课）")
