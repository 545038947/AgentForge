# Profile 系统指南

Profile 系统允许你定义具有不同能力的专家 Agent，并在运行时动态调度它们。

## 快速开始

### 1. 定义 Profile

创建 `profiles.yaml` 文件：

```yaml
security-reviewer:
  description: "代码安全审查专家"
  provider: deepseek
  model: deepseek-reasoner
  temperature: 0.3
  toolsets: [read, terminal]
  system_prompt: |
    你是一位资深安全工程师，专注于代码安全审查。

test-writer:
  description: "测试编写专家"
  provider: openai
  model: gpt-4o
  temperature: 0.5
  toolsets: [read, write, terminal]
  system_prompt: |
    你是一位测试工程师，专注于编写高质量的测试代码。
```

### 2. 配置 Provider 凭证

创建 `providers.yaml` 文件：

```yaml
providers:
  openai:
    api_key: ${OPENAI_API_KEY}

  deepseek:
    api_key: ${DEEPSEEK_API_KEY}
    base_url: https://api.deepseek.com/v1
```

### 3. 使用 Profile

```python
from agentforge import Agent
from agentforge.profiles import ProfileRegistry, ProviderRegistry

# 初始化
provider_registry = ProviderRegistry()
provider_registry.load_from_config("providers.yaml")

profile_registry = ProfileRegistry(
    provider_registry=provider_registry,
    config_paths=["profiles.yaml"],
)

# 创建 Agent
agent = Agent(
    model="gpt-4o",
    profile_registry=profile_registry,
    provider_registry=provider_registry,
)

# 验证 Profile 健康状态
results = agent.validate_profiles()
for name, (errors, warnings) in results.items():
    if errors:
        print(f"Profile '{name}' 有错误: {errors}")
    if warnings:
        print(f"Profile '{name}' 有警告: {warnings}")

# 运行（LLM 自动选择专家）
agent.run("请审查 auth.py 的安全性")
```

## Profile 继承

使用 `extends` 字段实现配置复用：

```yaml
_base-reasoner:
  provider: deepseek
  model: deepseek-reasoner
  temperature: 0.3
  toolsets: [read, terminal]

security-reviewer:
  extends: _base-reasoner
  description: "安全审查专家"
  system_prompt: "你是安全工程师..."

performance-analyzer:
  extends: _base-reasoner
  description: "性能分析专家"
  system_prompt: "你是性能专家..."
```

继承规则：
- 子 Profile 的非 None 值覆盖父 Profile
- 多级继承链会被递归解析
- 解析后 `extends` 字段被清除

## 运行时覆盖

在委托时可以覆盖 Profile 配置：

```python
from agentforge.delegation import TaskSpec

# 通过 TaskSpec 覆盖
task = TaskSpec(
    goal="审查代码",
    agent_profile="security-reviewer",
    temperature=0.1,  # 覆盖 Profile 的 temperature
    system_prompt="重点关注 SQL 注入",  # 追加到 Profile 的 system_prompt
)
```

## 配置优先级

配置按以下优先级合并（高优先级覆盖低优先级）：

1. TaskSpec 参数（运行时覆盖）
2. Profile 配置
3. 父 Agent 配置（回退）

## Provider 凭证优先级

Provider 凭证按以下优先级获取：

1. 运行时覆盖（代码显式传入）
2. 配置文件（providers.yaml）
3. 环境变量（如 `OPENAI_API_KEY`）

## Profile 配置字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | Profile 名称（必需） |
| `description` | str | 描述 |
| `extends` | str | 继承的父 Profile 名称 |
| `provider` | str | Provider 名称 |
| `model` | str | 模型名称 |
| `temperature` | float | 温度参数（0-2） |
| `max_tokens` | int | 最大输出 token |
| `reasoning_effort` | str | 推理深度（low/medium/high/max） |
| `toolsets` | list[str] | 可用工具集列表 |
| `blocked_tools` | list[str] | 禁止的工具列表 |
| `system_prompt` | str | 系统提示 |
| `inherit_memory` | bool | 是否继承父 Agent 记忆（默认 False） |
| `inherit_tools` | bool | 是否继承父 Agent 工具（默认 True） |
| `enabled` | bool | 是否启用（默认 True） |

## API 参考

### AgentProfile

```python
@dataclass
class AgentProfile:
    name: str                    # Profile 名称
    description: str = ""        # 描述
    extends: Optional[str] = None # 继承的父 Profile
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    toolsets: Optional[List[str]] = None
    blocked_tools: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    inherit_memory: bool = False
    inherit_tools: bool = True
    enabled: bool = True

    def to_dict() -> Dict[str, Any]
    def from_dict(data: Dict) -> AgentProfile
    def from_yaml(path: Path) -> AgentProfile
    def resolve(registry: ProfileRegistry) -> AgentProfile
    def validate(provider_registry: ProviderRegistry) -> Tuple[List[str], List[str]]
```

### ProfileRegistry

```python
class ProfileRegistry:
    def __init__(
        provider_registry: Optional[ProviderRegistry] = None,
        config_paths: Optional[List[Path]] = None,
    )

    def register(profile: AgentProfile) -> None
    def get(name: str) -> Optional[AgentProfile]
    def reload(name: Optional[str] = None) -> None
    def validate(name: Optional[str] = None) -> Dict[str, Tuple[List[str], List[str]]]
    def list_profiles() -> List[str]
```

### ProviderRegistry

```python
class ProviderRegistry:
    def register(
        provider: str,
        credentials: ProviderCredentials,
        override: bool = False,
    ) -> None

    def get_credentials(provider: str) -> Optional[ProviderCredentials]
    def is_available(provider: str) -> bool
    def load_from_config(path: Path) -> None
    def list_available() -> List[str]
```

### ProviderCredentials

```python
@dataclass
class ProviderCredentials:
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_mode: Optional[str] = None
    extra_headers: Dict[str, str] = {}
```

## 事件类型

Profile 系统触发以下事件：

| 事件 | 说明 |
|------|------|
| `PROFILE_LOADED` | Profile 成功加载 |
| `PROFILE_INVALID` | Profile 验证失败 |
| `PROFILE_RELOADED` | Profile 热重载完成 |

监听事件：

```python
from agentforge.events import on_event, EventType

@on_event(EventType.PROFILE_LOADED)
def on_profile_loaded(event):
    print(f"Profile 加载: {event.data['profile']}")
```

## 热重载

运行时更新 Profile 配置：

```python
# 重载单个 Profile
profile_registry.reload("security-reviewer")

# 重载所有 Profile
profile_registry.reload()
```

## 验证 Profile

验证 Profile 健康状态：

```python
# 验证单个 Profile
errors, warnings = profile_registry.validate("security-reviewer")

# 验证所有 Profile
results = profile_registry.validate()
for name, (errors, warnings) in results.items():
    print(f"{name}: errors={errors}, warnings={warnings}")
```

常见错误：
- Profile 名称不能为空
- Provider 凭证未配置
- temperature 超出范围 [0, 2]
- reasoning_effort 值无效

常见警告：
- 指定了 provider 但未指定 model