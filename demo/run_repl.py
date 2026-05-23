"""AgentForge Demo - 交互式 REPL。

主交互界面，支持：
- 多轮对话
- 流式响应
- 内置命令
- 工具调用
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentforge import Agent
from agentforge.providers.builtins.ollama import OllamaProvider
from demo.tools import get_all_demo_tools


def check_ollama(base_url: str = "http://localhost:11434") -> bool:
    """检查 Ollama 服务是否可用。"""
    import requests

    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def list_available_models(base_url: str = "http://localhost:11434") -> list:
    """列出可用模型。"""
    import requests

    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        pass
    return []


class REPL:
    """交互式 REPL。"""

    COMMANDS = {
        "/help": "显示帮助信息",
        "/tools": "列出可用工具",
        "/clear": "清空对话历史",
        "/info": "显示 Agent 信息",
        "/quit": "退出 REPL",
    }

    def __init__(self, agent: Agent, model: str):
        self.agent = agent
        self.model = model
        self.tools = get_all_demo_tools()

    def show_welcome(self):
        """显示欢迎信息。"""
        print("\n" + "=" * 50)
        print("🤖 AgentForge Demo REPL")
        print("=" * 50)
        print(f"\n📦 模型: {self.model}")
        print(f"🔧 工具数量: {len(self.tools)}")
        print("\n输入 /help 查看可用命令")
        print("输入消息开始对话\n")

    def show_help(self):
        """显示帮助信息。"""
        print("\n📖 可用命令:")
        for cmd, desc in self.COMMANDS.items():
            print(f"  {cmd:<10} - {desc}")
        print()

    def show_tools(self):
        """显示工具列表。"""
        print("\n🔧 已注册工具:")
        for tool in self.tools:
            print(f"\n  📦 {tool.name}")
            desc = tool.description.split("\n")[0]
            print(f"     {desc[:60]}...")
        print()

    def show_info(self):
        """显示 Agent 信息。"""
        print("\n📊 Agent 信息:")
        print(f"  模型: {self.model}")
        print(f"  工具数量: {len(self.tools)}")

        # 消息数量
        if hasattr(self.agent, "_message_manager"):
            msg_count = len(self.agent._message_manager)
            print(f"  消息数量: {msg_count}")

        print()

    def clear_history(self):
        """清空对话历史。"""
        self.agent.clear()
        print("\n✅ 对话历史已清空\n")

    def process_command(self, user_input: str) -> bool:
        """处理命令。

        Returns:
            True 表示继续，False 表示退出
        """
        cmd = user_input.strip().lower()

        if cmd == "/help":
            self.show_help()
        elif cmd == "/tools":
            self.show_tools()
        elif cmd == "/clear":
            self.clear_history()
        elif cmd == "/info":
            self.show_info()
        elif cmd == "/quit":
            print("\n👋 再见！\n")
            return False
        else:
            print(f"\n❌ 未知命令: {cmd}")
            print("输入 /help 查看可用命令\n")

        return True

    def chat(self, user_input: str):
        """进行对话。"""
        print("\n🤖 Agent: ", end="", flush=True)

        try:
            # 使用流式响应
            for chunk in self.agent.stream(user_input):
                if chunk.content:
                    print(chunk.content, end="", flush=True)

            print("\n")

        except Exception as e:
            print(f"\n❌ 错误: {e}\n")

    def run(self):
        """运行 REPL。"""
        self.show_welcome()

        while True:
            try:
                user_input = input("👤 你: ").strip()

                if not user_input:
                    continue

                # 处理命令
                if user_input.startswith("/"):
                    if not self.process_command(user_input):
                        break
                else:
                    # 对话
                    self.chat(user_input)

            except KeyboardInterrupt:
                print("\n\n👋 再见！\n")
                break
            except EOFError:
                print("\n\n👋 再见！\n")
                break


def main():
    """主函数。"""
    parser = argparse.ArgumentParser(description="AgentForge Demo REPL")
    parser.add_argument(
        "--model",
        default="llama3.2",
        help="Ollama 模型名称 (默认: llama3.2)",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:11434/v1",
        help="Ollama 服务地址 (默认: http://localhost:11434/v1)",
    )
    args = parser.parse_args()

    # 提取基础 URL（去掉 /v1）
    base_url = args.base_url
    if base_url.endswith("/v1"):
        check_url = base_url[:-3]
    else:
        check_url = base_url

    # 检查 Ollama
    if not check_ollama(check_url):
        print("\n❌ 错误: Ollama 服务未运行")
        print(f"   检查地址: {check_url}")
        print("\n请先启动 Ollama:")
        print("  ollama serve")
        sys.exit(1)

    # 列出可用模型
    models = list_available_models(check_url)
    if models and args.model not in [m.split(":")[0] for m in models]:
        print(f"\n⚠️  警告: 模型 '{args.model}' 可能未安装")
        print("可用模型:")
        for m in models[:5]:
            print(f"  - {m}")
        print()

    # 创建 Agent
    provider = OllamaProvider(model=args.model, base_url=args.base_url)
    tools = get_all_demo_tools()
    agent = Agent(provider=provider, tools=tools)

    # 运行 REPL
    repl = REPL(agent, args.model)
    repl.run()


if __name__ == "__main__":
    main()
