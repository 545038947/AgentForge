# Agent Profile System 设计文档

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 实现声明式的专家 Agent Profile 系统，支持主 Agent 调度具有不同 Provider/模型/能力的子 Agent。

**架构：** 三层分离（Profile 配置 → ProviderRegistry 认证 → DelegationManager 执行），懒加载缓存，Profile 继承，回退机制。

**技术栈：** Python 3.10+, Pydantic, YAML 配置

---

## 一、架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                      Agent Profile System                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────┐      ┌─────────────────────┐          │
│  │    AgentProfile     │      │   ProviderRegistry   │          │
│  │    (声明式配置)      │      │    (认证信息)        │          │
│  │                     │      │                      │          │
│  │  - name             │      │  - credentials       │          │
│  │  - extends          │──┐   │  - rate_limiters     │          │
│  │  - provider         │  │   │  - priority:         │          │
│  │  - model            │  │   │    代码 > 配置 > ENV │          │
│  │  - temperature      │  │   └─────────────────────┘          │
│  │  - toolsets         │  │               ▲                     │
│  │  - system_prompt    │  │               │                     │
│  │  - inherit_memory   │  │               │                     │
│  └─────────────────────┘  │               │                     │
│           ▲               │               │                     │
│           │               ▼               │                     │
│  ┌────────────────────────────────┐       │                     │
│  │       ProfileRegistry          │       │                     │
│  │       (懒加载 + 缓存)           │       │                     │
│  │                                │       │                     │
│  │  - load(name) → Profile        │       │                     │
│  │  - reload(name)                │       │                     │
│  │  - validate(name) → errors     │       │                     │
│  └────────────────────────────────┘       │                     │
│           │                               │                     │
│           ▼                               │                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  DelegationManager                        │   │
│  │                                                           │   │
│  │  delegate_task(                                           │   │
│  │      goal="审查代码安全",                                  │   │
│  │      agent_profile="security-reviewer"                    │   │
│  │  )                                                        │   │
│  │                                                           │   │
│  │  流程:                                                    │   │
│  │  1. ProfileRegistry.get(profile_name)                     │   │
│  │  2. Profile.validate() → 警告/错误                        │   │
│  │  3. ProviderRegistry.get_credentials(provider)            │   │
│  │  4. 若无效 → 回退到父 Agent 配置                           │   │
│  │  5. 创建隔离的子 Agent                                    │   │
│  │  6. 执行 → 发射事件                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                     Event System                          │   │
│  │                                                           │   │
│  │  PROFILE_LOADED, PROFILE_INVALID,                         │   │
│  │  DELEGATION_START {profile, provider, model},             │   │
│  │  DELEGATION_END {profile, duration, tokens, status}       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、核心组件

### 2.1 AgentProfile

**职责：** 专家 Agent 的声明式配置，不持有敏感信息。

**文件：** `agentforge/profiles/profile.py`

```python
@dataclass
class AgentProfile:
    """专家 Agent 的声明式配置。"""
    
    # 基本信息
    name: str                                    # Profile 名称（必需）
    description: str = ""                        # 描述
    extends: Optional[str] = None               # 继承的父 Profile
    
    # Provider 配置
    provider: Optional[str] = None              # Provider 名称
    model: Optional[str] = None                 # 模型名称
    
    # 模型参数
    temperature: Optional[float] = None         # 温度
    max_tokens: Optional[int] = None            # 最大 token
    reasoning_effort: Optional[str] = None      # 推理深度
    
    # 工具配置
    toolsets: Optional[List[str]] = None        # 可用工具集
    blocked_tools: Optional[List[str]] = None   # 禁止的工具
    
    # 行为配置
    system_prompt: Optional[str] = None         # 系统提示
    inherit_memory: bool = False                # 是否继承父 Agent 记忆
    inherit_tools: bool = True                  # 是否继承父 Agent 工具
    
    # 状态
    enabled: bool = True                        # 是否启用
```

**关键方法：**

- `resolve(registry) -> AgentProfile`：解析继承关系，返回完整配置
- `validate(provider_registry) -> (errors, warnings)`：验证配置有效性
- `to_dict() / from_dict() / from_yaml()`：序列化/反序列化

---

### 2.2 ProviderRegistry

**职责：** Provider 认证信息管理，支持多来源优先级。

**文件：** `agentforge/profiles/provider_registry.py`

**认证优先级（从高到低）：**
1. 运行时覆盖（代码显式传入）
2. 配置文件（providers.yaml）
3. 环境变量

```python
class ProviderRegistry:
    """Provider 认证信息注册表。"""
    
    def get_credentials(self, provider: str) -> Optional[ProviderCredentials]:
        """获取 Provider 凭证（按优先级）。"""
        # 1. 运行时覆盖
        # 2. 配置文件
        # 3. 环境变量
    
    def is_available(self, provider: str) -> bool:
        """检查 Provider 是否可用（有凭证）。"""
    
    def acquire(self, provider: str) -> ContextManager:
        """获取执行槽位（Rate Limit 控制）。"""
```

---

### 2.3 ProfileRegistry

**职责：** Agent Profile 注册表，懒加载 + 缓存 + 热重载。

**文件：** `agentforge/profiles/registry.py`

```python
class ProfileRegistry:
    """Agent Profile 注册表（懒加载 + 缓存）。"""
    
    def get(self, name: str) -> Optional[AgentProfile]:
        """获取 Profile（懒加载）。"""
    
    def reload(self, name: Optional[str] = None) -> None:
        """热重载 Profile。"""
    
    def validate(self, name: Optional[str] = None) -> Dict[str, Tuple[List[str], List[str]]]:
        """验证 Profile 有效性。"""
    
    def _resolve_inheritance(self, profile: AgentProfile) -> AgentProfile:
        """解析继承关系。"""
```

---

### 2.4 扩展 TaskSpec

**文件：** `agentforge/delegation/config.py`

```python
@dataclass
class TaskSpec:
    goal: str
    context: Optional[str] = None
    toolsets: Optional[List[str]] = None
    role: str = "leaf"
    model: Optional[str] = None
    
    # 新增
    agent_profile: Optional[str] = None          # Profile 名称
    temperature: Optional[float] = None          # 运行时覆盖
    max_tokens: Optional[int] = None             # 运行时覆盖
    system_prompt: Optional[str] = None          # 追加到 Profile 的 system_prompt
```

---

### 2.5 扩展 DelegationManager

**文件：** `agentforge/delegation/manager.py`

新增方法：

- `_resolve_profile(profile_name, task) -> Optional[AgentProfile]`：解析并验证 Profile
- `_resolve_child_config(task, profile, system_prompt)`：解析子 Agent 最终配置
- 修改 `_create_child_agent()`：集成 Profile 解析逻辑

**配置优先级：** task 覆盖 > Profile 配置 > 父 Agent 回退

---

### 2.6 扩展 EventType

**文件：** `agentforge/events/types.py`

```python
class EventType(Enum):
    # 新增
    PROFILE_LOADED = "profile.loaded"
    PROFILE_INVALID = "profile.invalid"
    PROFILE_RELOADED = "profile.reloaded"
```

---

## 三、配置文件格式

### 3.1 profiles.yaml

```yaml
# 基础配置（以 _ 开头表示抽象，不直接使用）
_base-reasoner:
  description: "推理任务基础配置"
  provider: deepseek
  model: deepseek-reasoner
  temperature: 0.3
  toolsets: [read, terminal]
  inherit_tools: true
  inherit_memory: false

# 安全审查专家
security-reviewer:
  extends: _base-reasoner
  description: "代码安全审查专家"
  system_prompt: |
    你是一位资深安全工程师，专注于代码安全审查。

# 性能分析专家
performance-analyzer:
  extends: _base-reasoner
  description: "性能分析专家"
  system_prompt: |
    你是一位性能优化专家，专注于代码性能分析。

# 测试编写专家
test-writer:
  provider: openai
  model: gpt-4o
  temperature: 0.5
  description: "测试代码编写专家"
  toolsets: [read, write, terminal]
  system_prompt: |
    你是一位测试工程师，专注于编写高质量的测试代码。
```

### 3.2 providers.yaml

```yaml
providers:
  openai:
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1
  
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
  
  deepseek:
    api_key: ${DEEPSEEK_API_KEY}
    base_url: https://api.deepseek.com/v1
```

---

## 四、隔离边界保证

| 资源 | 隔离策略 |
|------|----------|
| 消息历史 | 子 Agent 独立，不继承父 Agent 历史 |
| 工具状态 | 子 Agent 独立执行，结果以摘要形式返回父 Agent |
| 记忆存储 | 默认不继承；Profile 设置 `inherit_memory=True` 可继承 |
| Provider 凭证 | 共享（从 ProviderRegistry 获取） |
| Session | 子 Agent 可关联父 Session（通过 `parent_session_id`） |

---

## 五、事件数据格式

```python
# DELEGATION_START
{
    "profile": "security-reviewer",
    "provider": "deepseek",
    "model": "deepseek-reasoner",
    "goal": "审查 auth.py 的安全性",
}

# DELEGATION_END
{
    "profile": "security-reviewer",
    "status": "completed",
    "duration_ms": 3500,
    "tokens": {"input": 1200, "output": 800},
    "summary": "发现 3 个潜在安全问题...",
}

# PROFILE_INVALID
{
    "profile": "security-reviewer",
    "errors": ["Provider 'deepseek' 凭证未配置"],
    "warnings": [],
}
```

---

## 六、使用示例

```python
from agentforge import Agent
from agentforge.profiles import ProfileRegistry, ProviderRegistry

# 1. 初始化
provider_registry = ProviderRegistry()
provider_registry.load_from_config("providers.yaml")

profile_registry = ProfileRegistry(
    provider_registry=provider_registry,
    config_paths=["profiles.yaml"],
)

# 2. 创建 Agent
agent = Agent(
    model="gpt-4o",
    profile_registry=profile_registry,
    provider_registry=provider_registry,
)

# 3. 运行（LLM 自动选择专家）
agent.run("""
请对 src/auth.py 进行代码审查：
1. 先用安全专家检查安全问题
2. 再用性能专家检查性能问题
3. 最后让测试专家编写相应的测试
""")

# 4. 验证 Profile 健康状态
results = profile_registry.validate()

# 5. 热重载
profile_registry.reload()
```

---

## 七、实现任务

### Task 1: 创建 AgentProfile 数据类

**文件：** `agentforge/profiles/profile.py`

- [ ] **Step 1: 创建 AgentProfile dataclass**

```python
@dataclass
class AgentProfile:
    name: str
    description: str = ""
    extends: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    reasoning_effort: Optional[str] = None
    toolsets: Optional[List[str]] = None
    blocked_tools: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    inherit_memory: bool = False
    inherit_tools: bool = True
    enabled: bool = True
```

- [ ] **Step 2: 实现 to_dict / from_dict 方法**

- [ ] **Step 3: 实现 from_yaml 方法**

- [ ] **Step 4: 实现 resolve 方法（继承解析）**

- [ ] **Step 5: 实现 validate 方法**

- [ ] **Step 6: 编写单元测试**

---

### Task 2: 创建 ProviderRegistry

**文件：** `agentforge/profiles/provider_registry.py`

- [ ] **Step 1: 创建 ProviderCredentials dataclass**

- [ ] **Step 2: 实现 ProviderRegistry 类框架**

- [ ] **Step 3: 实现认证优先级逻辑**

- [ ] **Step 4: 实现配置文件加载**

- [ ] **Step 5: 实现环境变量加载**

- [ ] **Step 6: 实现 is_available 方法**

- [ ] **Step 7: 编写单元测试**

---

### Task 3: 创建 ProfileRegistry

**文件：** `agentforge/profiles/registry.py`

- [ ] **Step 1: 实现 ProfileRegistry 类框架**

- [ ] **Step 2: 实现懒加载 + 缓存机制**

- [ ] **Step 3: 实现继承解析逻辑**

- [ ] **Step 4: 实现 validate 方法**

- [ ] **Step 5: 实现 reload 热重载**

- [ ] **Step 6: 编写单元测试**

---

### Task 4: 扩展 TaskSpec

**文件：** `agentforge/delegation/config.py`

- [ ] **Step 1: 添加 agent_profile 字段**

- [ ] **Step 2: 添加 temperature, max_tokens, system_prompt 覆盖字段**

- [ ] **Step 3: 更新 to_dict 方法**

- [ ] **Step 4: 编写单元测试**

---

### Task 5: 扩展 DelegationManager

**文件：** `agentforge/delegation/manager.py`

- [ ] **Step 1: 添加 profile_registry 和 provider_registry 参数**

- [ ] **Step 2: 实现 _resolve_profile 方法**

- [ ] **Step 3: 实现 _resolve_child_config 方法**

- [ ] **Step 4: 修改 _create_child_agent 集成 Profile 解析**

- [ ] **Step 5: 添加事件发射**

- [ ] **Step 6: 编写集成测试**

---

### Task 6: 扩展 EventType

**文件：** `agentforge/events/types.py`

- [ ] **Step 1: 添加 PROFILE_LOADED 事件**

- [ ] **Step 2: 添加 PROFILE_INVALID 事件**

- [ ] **Step 3: 添加 PROFILE_RELOADED 事件**

---

### Task 7: 扩展 Agent 类

**文件：** `agentforge/agent.py`

- [ ] **Step 1: 添加 profile_registry 和 provider_registry 参数**

- [ ] **Step 2: 传递给 DelegationManager**

- [ ] **Step 3: 添加 validate_profiles 方法**

---

### Task 8: 创建模块导出

**文件：** `agentforge/profiles/__init__.py`

- [ ] **Step 1: 导出 AgentProfile**

- [ ] **Step 2: 导出 ProviderRegistry**

- [ ] **Step 3: 导出 ProfileRegistry**

- [ ] **Step 4: 导出 ProviderCredentials**

---

### Task 9: 更新主 __init__.py

**文件：** `agentforge/__init__.py`

- [ ] **Step 1: 导出 profiles 模块**

---

### Task 10: 编写文档

**文件：** `docs/user-guide/profiles.md`

- [ ] **Step 1: 编写使用指南**

- [ ] **Step 2: 编写配置文件格式说明**

- [ ] **Step 3: 编写 API 参考**

---

## 八、验证标准

### 单元测试

```bash
pytest tests/test_profiles.py -v
pytest tests/test_provider_registry.py -v
pytest tests/test_profile_registry.py -v
```

### 集成测试

```python
# 测试完整的 Profile 流程
provider_registry = ProviderRegistry()
provider_registry.load_from_config("providers.yaml")

profile_registry = ProfileRegistry(provider_registry, ["profiles.yaml"])

agent = Agent(
    model="gpt-4o",
    profile_registry=profile_registry,
    provider_registry=provider_registry,
)

# 验证 Profile 可用
assert profile_registry.get("security-reviewer") is not None

# 验证回退机制
# 当 deepseek 凭证未配置时，应回退到父 Agent 的 provider
```

---

## 九、后续扩展（Phase 2）

- Rate Limiter：Provider 级别的请求限流
- Credential Pool：凭证轮换，支持多 API Key
- Profile 市场：从远程仓库加载 Profile
- Profile 继承链深度限制
