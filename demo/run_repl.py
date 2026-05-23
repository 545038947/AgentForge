"""AgentForge Demo - 交互式 REPL。

主交互界面，支持：
- 多轮对话
- 流式响应
- 内置命令
- 工具调用
- MCP Server 集成
- 配置文件支持
"""

import argparse
import sys
from pathlib import Path

# Windows 终端编码设置
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentforge import Agent
from agentforge.providers.builtins.ollama import OllamaProvider
from demo.config import get_config, reload_config, DemoConfig
from demo.tools import get_all_demo_tools


def check_ollama(base_url: str) -> bool:
    """检查 Ollama 服务是否可用。"""
    import requests

    # 提取基础 URL（去掉 /v1）
    check_url = base_url.rstrip("/v1")
    try:
        response = requests.get(f"{check_url}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def list_available_models(base_url: str) -> list:
    """列出可用模型。"""
    import requests

    check_url = base_url.rstrip("/v1")
    try:
        response = requests.get(f"{check_url}/api/tags", timeout=5)
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
        "/mcp": "显示 MCP Server 状态",
        "/clear": "清空对话历史",
        "/info": "显示 Agent 信息",
        "/config": "显示当前配置",
        "/quit": "退出 REPL",
    }

    def __init__(self, agent: Agent, config: DemoConfig):
        self.agent = agent
        self.config = config
        self.tools = get_all_demo_tools()

    def show_welcome(self):
        """显示欢迎信息。"""
        print("\n" + "=" * 50)
        print("🤖 AgentForge Demo REPL")
        print("=" * 50)
        print(f"\n📦 模型: {self.config.ollama.model}")
        print(f"🌐 服务: {self.config.ollama.base_url}")
        print(f"🔧 内置工具数量: {len(self.tools)}")

        # MCP 状态
        mcp_manager = self.agent.get_mcp_manager()
        if mcp_manager and mcp_manager.is_initialized():
            mcp_tools = self.agent.get_mcp_tools()
            servers = mcp_manager.get_server_names()
            print(f"🔌 MCP Servers: {len(servers)} 个已连接")
            print(f"   MCP 工具数量: {len(mcp_tools)}")

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

        # 内置工具
        print("\n  [内置工具]")
        for tool in self.tools:
            print(f"\n  📦 {tool.name}")
            desc = tool.description.split("\n")[0]
            print(f"     {desc[:60]}...")

        # MCP 工具
        mcp_tools = self.agent.get_mcp_tools()
        if mcp_tools:
            print("\n  [MCP 工具]")
            for tool in mcp_tools:
                print(f"\n  🌐 {tool.name}")
                desc = tool.description.split("\n")[0] if tool.description else ""
                print(f"     {desc[:60]}...")

        print()

    def show_mcp(self):
        """显示 MCP Server 状态。"""
        mcp_manager = self.agent.get_mcp_manager()

        if not mcp_manager or not mcp_manager.is_initialized():
            print("\n🔌 MCP: 未启用或未初始化")
            print("   在配置文件中设置 mcp.enabled: true 并指定 config_path")
            print()

            if self.config.mcp.config_path:
                print(f"   配置文件路径: {self.config.mcp.config_path}")
                print("   使用命令 /reload_mcp 尝试加载")
            return

        servers = mcp_manager.get_server_names()
        print(f"\n🔌 MCP Servers ({len(servers)} 个已连接):")

        for server_name in servers:
            connected = mcp_manager.is_server_connected(server_name)
            status = "✅" if connected else "❌"
            tools = mcp_manager.get_tools_for_server(server_name)
            print(f"\n   {status} {server_name}")
            print(f"      工具数量: {len(tools)}")
            for tool in tools[:3]:
                print(f"      - {tool.name}")
            if len(tools) > 3:
                print(f"      - ... 还有 {len(tools) - 3} 个工具")

        print()

    def show_info(self):
        """显示 Agent 信息。"""
        print("\n📊 Agent 信息:")
        print(f"  模型: {self.config.ollama.model}")
        print(f"  服务地址: {self.config.ollama.base_url}")
        print(f"  内置工具数量: {len(self.tools)}")

        # MCP 信息
        mcp_manager = self.agent.get_mcp_manager()
        if mcp_manager and mcp_manager.is_initialized():
            mcp_tools = self.agent.get_mcp_tools()
            print(f"  MCP 工具数量: {len(mcp_tools)}")

        print(f"  温度: {self.config.agent.temperature}")
        print(f"  最大 Token: {self.config.agent.max_tokens}")

        # 消息数量
        if hasattr(self.agent, "_message_manager"):
            msg_count = len(self.agent._message_manager)
            print(f"  消息数量: {msg_count}")

        print()

    def show_config(self):
        """显示当前配置。"""
        print("\n⚙️  当前配置:")
        print(f"\n[Ollama]")
        print(f"  base_url: {self.config.ollama.base_url}")
        print(f"  model: {self.config.ollama.model}")
        print(f"  timeout: {self.config.ollama.timeout}s")
        print(f"\n[Agent]")
        print(f"  temperature: {self.config.agent.temperature}")
        print(f"  max_tokens: {self.config.agent.max_tokens}")
        print(f"\n[Memory]")
        print(f"  store_path: {self.config.memory.store_path}")
        print(f"\n[Delegation]")
        print(f"  max_concurrent: {self.config.delegation.max_concurrent}")
        print(f"  max_depth: {self.config.delegation.max_depth}")
        print(f"\n[MCP]")
        print(f"  enabled: {self.config.mcp.enabled}")
        print(f"  config_path: {self.config.mcp.config_path}")
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
        elif cmd == "/mcp":
            self.show_mcp()
        elif cmd == "/clear":
            self.clear_history()
        elif cmd == "/info":
            self.show_info()
        elif cmd == "/config":
            self.show_config()
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


def load_mcp_servers(agent: Agent, config: DemoConfig) -> None:
    """加载 MCP Servers。"""
    if not config.mcp.enabled:
        return

    if not config.mcp.config_path:
        print("⚠️  MCP 已启用但未指定配置文件路径")
        return

    config_path = Path(config.mcp.config_path)
    if not config_path.exists():
        # 尝试相对于 demo 目录查找
        demo_dir = Path(__file__).parent
        config_path = demo_dir / config.mcp.config_path

    if config_path.exists():
        print(f"🔌 加载 MCP 配置: {config_path}")
        try:
            agent.add_mcp_servers(str(config_path))
            mcp_tools = agent.get_mcp_tools()
            mcp_manager = agent.get_mcp_manager()
            if mcp_manager:
                servers = mcp_manager.get_server_names()
                print(f"   ✅ 已连接 {len(servers)} 个 MCP Server")
                print(f"   ✅ 已注册 {len(mcp_tools)} 个 MCP 工具")
        except Exception as e:
            print(f"   ❌ 加载 MCP 失败: {e}")
    else:
        print(f"⚠️  MCP 配置文件不存在: {config.mcp.config_path}")


def main():
    """主函数。"""
    parser = argparse.ArgumentParser(description="AgentForge Demo REPL")
    parser.add_argument(
        "--config",
        default=None,
        help="配置文件路径 (默认: demo/config.yaml)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="覆盖配置中的模型名称",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="覆盖配置中的 Ollama 服务地址",
    )
    parser.add_argument(
        "--mcp-config",
        default=None,
        help="MCP 配置文件路径",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="禁用 MCP",
    )
    args = parser.parse_args()

    # 加载配置
    config = reload_config(args.config)

    # 命令行参数覆盖配置文件
    if args.model:
        config.ollama.model = args.model
    if args.base_url:
        config.ollama.base_url = args.base_url
    if args.mcp_config:
        config.mcp.config_path = args.mcp_config
        config.mcp.enabled = True
    if args.no_mcp:
        config.mcp.enabled = False

    # 检查 Ollama
    if not check_ollama(config.ollama.base_url):
        print("\n❌ 错误: Ollama 服务未运行")
        print(f"   检查地址: {config.ollama.base_url.rstrip('/v1')}")
        print("\n请先启动 Ollama:")
        print("  ollama serve")
        sys.exit(1)

    # 列出可用模型
    models = list_available_models(config.ollama.base_url)
    model_name = config.ollama.model.split(":")[0]
    if models and model_name not in [m.split(":")[0] for m in models]:
        print(f"\n⚠️  警告: 模型 '{config.ollama.model}' 可能未安装")
        print("可用模型:")
        for m in models[:5]:
            print(f"  - {m}")
        print()

    # 创建 Provider 和 Agent
    provider = OllamaProvider(
        model=config.ollama.model,
        base_url=config.ollama.base_url,
        timeout=config.ollama.timeout,
    )
    tools = get_all_demo_tools()
    agent = Agent(provider=provider, tools=tools)

    # 加载 MCP Servers
    load_mcp_servers(agent, config)

    # 运行 REPL
    repl = REPL(agent, config)
    repl.run()

    # 关闭 Agent
    agent.shutdown()


if __name__ == "__main__":
    main()
