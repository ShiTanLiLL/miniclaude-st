"""REPL 入口：python -m mini_claude

你在终端里一问一答的体验由这里提供；
真正的核心逻辑在 loop.py 的 agent_loop 里。
"""

from . import llm
from .loop import agent_loop


def print_last_reply(history: list) -> None:
    """把最后一轮 assistant 回复里的文本块打印出来。"""
    content = history[-1]["content"]
    if isinstance(content, list):
        for block in content:
            if getattr(block, "type", None) == "text":
                print(block.text)


def main() -> None:
    print("mini_claude 第 1 课：Agent Loop")
    print("输入问题回车发送，输入 q 退出。\n")

    client = None
    model = None
    history = []
    while True:
        try:
            query = input("\033[36mmini >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break

        # 首次真正提问时才连 API：随手看看、直接退出都不需要配好 key
        if client is None:
            client = llm.get_client()
            model = llm.get_model()

        history.append({"role": "user", "content": query})
        agent_loop(history, client, model)
        print_last_reply(history)
        print()


if __name__ == "__main__":
    main()
