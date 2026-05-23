# 记忆系统扩展指南

本文档介绍如何扩展 AgentForge 的记忆系统，包括自定义存储后端、自动记忆提取等高级功能。

## 目录

1. [架构概览](#架构概览)
2. [自定义 MemoryStore](#自定义-memorystore)
3. [多用户记忆存储](#多用户记忆存储)
4. [向量检索存储](#向量检索存储)
5. [自动记忆提取](#自动记忆提取)
6. [元数据和时间衰减](#元数据和时间衰减)

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent                                    │
│                          │                                       │
│                          ▼                                       │
│                   MemoryManager                                  │
│                          │                                       │
│         ┌────────────────┼────────────────┐                     │
│         │                │                │                     │
│         ▼                ▼                ▼                     │
│   MemoryProvider   MemoryStoreBase   MemoryExtractor            │
│   (键值存储)        (长期记忆)        (自动提取)                  │
└─────────────────────────────────────────────────────────────────┘
```

**核心接口：**

- `MemoryProvider` - 通用键值存储抽象
- `MemoryStoreBase` - 长期记忆存储抽象
- `MemoryExtractor` - 自动记忆提取抽象
- `MemoryMetadata` - 记忆元数据结构

---

## 自定义 MemoryStore

### 继承 MemoryStoreBase

```python
from hai_agent.memory import MemoryStoreBase

class MyMemoryStore(MemoryStoreBase):
    """自定义记忆存储。"""

    def __init__(self, custom_path: str, **kwargs):
        self._path = custom_path
        self._memory_entries = []
        self._user_entries = []
        # 初始化...

    def load_from_disk(self) -> tuple[int, int]:
        """从存储加载数据。"""
        # 实现加载逻辑
        return len(self._memory_entries), len(self._user_entries)

    def sync_to_disk(self) -> dict[str, bool]:
        """同步数据到存储。"""
        # 实现同步逻辑
        return {"memory": True, "user": True}

    def add_entry(self, target: str, entry: str, sync: bool = True,
                  check_threats: bool = True) -> bool:
        """添加记忆条目。"""
        entries = self._memory_entries if target == "memory" else self._user_entries
        entries.append(entry)
        return True

    def remove_entry(self, target: str, entry: str, sync: bool = True) -> bool:
        """移除记忆条目。"""
        # 实现移除逻辑
        ...

    def format_for_system_prompt(self, target: str) -> str:
        """获取用于系统提示的记忆块。"""
        # 实现格式化逻辑
        ...

    def refresh_snapshot(self) -> None:
        """刷新冻结快照。"""
        ...

    def scan_for_threats(self, content: str) -> list[str]:
        """扫描安全威胁。"""
        # 可以使用默认实现或自定义
        return []

    def get_stats(self) -> dict:
        """获取统计信息。"""
        return {
            "memory_entries": len(self._memory_entries),
            "user_entries": len(self._user_entries),
        }

    @property
    def memory_entries(self) -> list[str]:
        return self._memory_entries.copy()

    @property
    def user_entries(self) -> list[str]:
        return self._user_entries.copy()
```

### 使用自定义存储

```python
from hai_agent import Agent

# 创建自定义存储
my_store = MyMemoryStore("/custom/path")

# 传入 Agent
agent = Agent(model="gpt-4")
agent._memory_manager.enable_memory_store(store=my_store)

# 正常使用
agent.prefetch()
agent.run("记住我的名字是张三")
agent.sync()
```

---

## 多用户记忆存储

### 实现多用户隔离

```python
from pathlib import Path
from hai_agent.memory import MemoryStore, MemoryStoreBase

class MultiUserMemoryStore(MemoryStore):
    """多用户记忆存储。

    每个用户有独立的存储目录：
        memories/
        ├── user-001/
        │   ├── MEMORY.md
        │   └── USER.md
        └── user-002/
            ├── MEMORY.md
            └── USER.md
    """

    def __init__(self, base_path: str, user_id: str, **kwargs):
        # 用户隔离的存储路径
        user_path = Path(base_path) / user_id
        super().__init__(str(user_path), **kwargs)
        self._user_id = user_id

    @property
    def user_id(self) -> str:
        return self._user_id
```

### 在 Web 应用中使用

```python
from hai_agent import Agent
from hai_agent.memory import MemoryManager

def get_agent_for_user(user_id: str) -> Agent:
    """获取用户专属的 Agent 实例。"""
    agent = Agent(model="gpt-4")

    # 使用多用户存储
    from myapp.memory import MultiUserMemoryStore
    store = MultiUserMemoryStore("./memories", user_id=user_id)

    agent._memory_manager.enable_memory_store(store=store)
    agent.prefetch()

    return agent

# FastAPI 示例
from fastapi import FastAPI, Depends

app = FastAPI()

@app.post("/chat/{user_id}")
async def chat(user_id: str, message: str):
    agent = get_agent_for_user(user_id)
    response = agent.run(message)
    agent.sync()
    return {"response": response.content}
```

---

## 向量检索存储

### 使用 Chroma 实现

```python
from hai_agent.memory import MemoryProvider, MemoryMetadata
from typing import Any, Dict, List, Optional
import chromadb

class VectorMemoryProvider(MemoryProvider):
    """向量记忆存储，支持语义检索。"""

    def __init__(self, collection_name: str = "memories"):
        self.client = chromadb.Client()
        self.collection = self.client.create_collection(collection_name)
        self._data: Dict[str, Any] = {}
        self._metadata: Dict[str, Dict] = {}

    def save(self, key: str, value: Any, metadata: Optional[Dict] = None) -> None:
        """保存记忆，同时生成向量嵌入。"""
        self._data[key] = value
        self._metadata[key] = metadata or {}

        # 向量化存储
        self.collection.add(
            ids=[key],
            documents=[str(value)],
            metadatas=[self._metadata[key]]
        )

    def load(self, key: str) -> Optional[Any]:
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            self.collection.delete(ids=[key])
            return True
        return False

    def exists(self, key: str) -> bool:
        return key in self._data

    def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        keys = list(self._data.keys())
        if prefix:
            keys = [k for k in keys if k.startswith(prefix)]
        return keys

    def clear(self) -> None:
        self._data.clear()
        self._metadata.clear()
        # 重建集合
        name = self.collection.name
        self.client.delete_collection(name)
        self.collection = self.client.create_collection(name)

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """语义搜索记忆。"""
        results = self.collection.query(
            query_texts=[query],
            n_results=limit
        )

        memories = []
        for i, key in enumerate(results["ids"][0]):
            memories.append({
                "key": key,
                "value": self._data.get(key),
                "metadata": self._metadata.get(key),
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })
        return memories
```

### 使用向量存储

```python
from hai_agent import Agent, MemoryManager
from myapp.memory import VectorMemoryProvider

# 创建向量存储
vector_memory = VectorMemoryProvider("user_memories")

# 注册到 MemoryManager
manager = MemoryManager()
manager.register("vector", vector_memory)

agent = Agent(model="gpt-4", memory_manager=manager)

# 存储记忆
manager.save("vector", "user_name", "张三")
manager.save("vector", "user_preference", "喜欢简洁的回答")

# 语义搜索
results = vector_memory.search("用户的称呼")
# 可能返回: [{"key": "user_name", "value": "张三", "distance": 0.15}]
```

---

## 自动记忆提取

### 使用内置规则提取器

```python
from hai_agent import Agent

agent = Agent(model="gpt-4")
agent.enable_memory_store("./memories")

# 启用自动提取（基于规则）
agent._memory_manager.enable_auto_extraction()
agent.prefetch()

# 对话中自动提取
agent.run("我叫张三，我喜欢使用 Python")

# 检查提取的记忆
store = agent._memory_manager.get_memory_store()
print(store.memory_entries)
# 可能输出: ['用户名叫张三', '用户偏好：使用 Python']
```

### 使用 LLM 辅助提取

```python
from hai_agent import Agent
from hai_agent.providers import OpenAIProvider

# 创建 Provider
provider = OpenAIProvider(model="gpt-4")

agent = Agent(provider=provider)
agent.enable_memory_store("./memories")

# 启用 LLM 辅助提取
agent._memory_manager.enable_auto_extraction(
    provider=provider,
    use_llm=True,
)

# 对话中自动提取（更精确）
agent.run("我是一名全栈开发者，目前主要使用 TypeScript")
agent.sync()
```

### 自定义提取器

```python
from hai_agent.memory import MemoryExtractor, ExtractedMemory, MemoryType

class MyExtractor(MemoryExtractor):
    """自定义记忆提取器。"""

    def extract(self, user_message: str, assistant_response: str) -> list[ExtractedMemory]:
        memories = []

        # 自定义提取逻辑
        if "项目" in user_message:
            # 提取项目信息
            import re
            match = re.search(r"项目[叫是为]?([^\s，。]+)", user_message)
            if match:
                memories.append(ExtractedMemory(
                    content=f"用户项目: {match.group(1)}",
                    memory_type=MemoryType.CONTEXT,
                    importance=0.7,
                ))

        return memories

# 使用自定义提取器
agent = Agent(model="gpt-4")
agent.enable_memory_store("./memories")
agent._memory_manager.enable_auto_extraction(extractor=MyExtractor())
```

---

## 元数据和时间衰减

### 使用元数据

```python
from hai_agent.memory import MemoryMetadata, MemorySource, MemoryType

# 创建用户事实记忆
metadata = MemoryMetadata.user_fact(
    importance=0.9,
    tags=["个人信息", "重要"],
)

# 创建 Agent 推断记忆
metadata = MemoryMetadata.agent_inferred(
    confidence=0.7,
    importance=0.5,
)

# 创建用户偏好记忆
metadata = MemoryMetadata.user_preference(
    importance=0.8,
)

# 检查过期
from datetime import datetime, timedelta

metadata = MemoryMetadata(
    expires_at=datetime.now() + timedelta(days=30),
)

if metadata.is_expired():
    print("记忆已过期")
```

### 实现时间衰减

```python
from hai_agent.memory import MemoryMetadata
from datetime import datetime, timedelta

# 创建记忆（10小时前）
old_metadata = MemoryMetadata(
    importance=1.0,
    created_at=datetime.now() - timedelta(hours=10),
)

# 应用衰减
decayed = old_metadata.apply_decay(decay_rate=0.01)
print(f"原重要性: {old_metadata.importance:.2f}")
print(f"衰减后: {decayed.importance:.2f}")
# 输出: 原重要性: 1.00, 衰减后: 0.90

# 访问时提升重要性
touched = decayed.touch()
print(f"访问后: {touched.importance:.2f}")
# 输出: 访问后: 1.00
```

---

## 最佳实践

### 1. 记忆分类

- **FACT**: 客观事实（姓名、职业、技能）
- **PREFERENCE**: 用户偏好（回答风格、语言偏好）
- **CONTEXT**: 上下文信息（当前项目、工作环境）
- **INSTRUCTION**: 用户指令（总是用中文回答）

### 2. 重要性评分

```python
# 高重要性：核心个人信息
MemoryMetadata.user_fact(importance=0.9)  # 姓名

# 中重要性：偏好和习惯
MemoryMetadata.user_preference(importance=0.7)  # 编码风格

# 低重要性：临时上下文
MemoryMetadata(importance=0.3, memory_type=MemoryType.CONTEXT)  # 当前文件
```

### 3. 记忆清理策略

```python
def cleanup_memories(store: MemoryStoreBase, threshold: float = 0.2):
    """清理低重要性的记忆。"""
    for entry in store.memory_entries:
        # 假设存储了元数据
        metadata = get_metadata_for_entry(entry)
        if metadata and metadata.should_decay(threshold):
            store.remove_entry("memory", entry)
    store.sync_to_disk()
```

### 4. 多层记忆协同

```python
from hai_agent import Agent, MemoryManager
from hai_agent.memory import InMemoryProvider

# Session 层：临时会话数据
session = InMemoryProvider()

# 长期层：持久化记忆
agent = Agent(model="gpt-4")
agent._memory_manager.register("session", session)
agent.enable_memory_store("./memories")

# 使用时
agent.prefetch()  # 加载所有层
agent.run("...")  # 对话
agent.sync()      # 同步所有层
```

---

## 参考资源

- [MemoryProvider API](../api/memory.md#memoryprovider)
- [MemoryStoreBase API](../api/memory.md#memorystorebase)
- [MemoryExtractor API](../api/memory.md#memoryextractor)
- [MemoryMetadata API](../api/memory.md#memorymetadata)
