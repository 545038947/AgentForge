"""P6 阶段单元测试：存储与技能系统。"""

import json
import os
import pytest
import tempfile
from pathlib import Path

from hai_agent.memory import MemoryProvider, InMemoryProvider, FileBasedProvider
from hai_agent.skills import Skill, SkillRegistry, SkillLoader
from hai_agent.skills.base import SkillMetadata, FunctionSkill


# ── Memory 测试 ──────────────────────────────────────────────

class TestInMemoryProvider:
    """InMemoryProvider 测试。"""

    def test_save_and_load(self):
        """测试保存和加载。"""
        memory = InMemoryProvider()

        memory.save("key1", {"data": "value1"})
        result = memory.load("key1")

        assert result == {"data": "value1"}

    def test_load_nonexistent(self):
        """测试加载不存在的键。"""
        memory = InMemoryProvider()

        result = memory.load("nonexistent")
        assert result is None

    def test_delete(self):
        """测试删除。"""
        memory = InMemoryProvider()

        memory.save("key1", "value1")
        result = memory.delete("key1")

        assert result is True
        assert memory.load("key1") is None

    def test_delete_nonexistent(self):
        """测试删除不存在的键。"""
        memory = InMemoryProvider()

        result = memory.delete("nonexistent")
        assert result is False

    def test_exists(self):
        """测试存在检查。"""
        memory = InMemoryProvider()

        memory.save("key1", "value1")

        assert memory.exists("key1")
        assert not memory.exists("key2")

    def test_list_keys(self):
        """测试列出键。"""
        memory = InMemoryProvider()

        memory.save("key1", "value1")
        memory.save("key2", "value2")
        memory.save("prefix_key", "value3")

        keys = memory.list_keys()
        assert len(keys) == 3

        # 前缀过滤
        prefix_keys = memory.list_keys(prefix="prefix")
        assert len(prefix_keys) == 1

    def test_clear(self):
        """测试清空。"""
        memory = InMemoryProvider()

        memory.save("key1", "value1")
        memory.save("key2", "value2")
        memory.clear()

        assert len(memory.list_keys()) == 0

    def test_get_with_default(self):
        """测试带默认值的获取。"""
        memory = InMemoryProvider()

        memory.save("key1", "value1")

        assert memory.get("key1") == "value1"
        assert memory.get("nonexistent", "default") == "default"

    def test_metadata(self):
        """测试元数据。"""
        memory = InMemoryProvider()

        memory.save("key1", "value1", {"author": "test"})

        meta = memory.get_metadata("key1")
        assert meta == {"author": "test"}

    def test_count(self):
        """测试计数。"""
        memory = InMemoryProvider()

        memory.save("key1", "value1")
        memory.save("key2", "value2")

        assert memory.count() == 2


class TestFileBasedProvider:
    """FileBasedProvider 测试。"""

    def test_save_and_load(self):
        """测试保存和加载。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileBasedProvider(tmpdir)

            memory.save("key1", {"data": "value1"})
            result = memory.load("key1")

            assert result == {"data": "value1"}

    def test_load_nonexistent(self):
        """测试加载不存在的键。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileBasedProvider(tmpdir)

            result = memory.load("nonexistent")
            assert result is None

    def test_delete(self):
        """测试删除。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileBasedProvider(tmpdir)

            memory.save("key1", "value1")
            result = memory.delete("key1")

            assert result is True
            assert memory.load("key1") is None

    def test_exists(self):
        """测试存在检查。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileBasedProvider(tmpdir)

            memory.save("key1", "value1")

            assert memory.exists("key1")
            assert not memory.exists("key2")

    def test_list_keys(self):
        """测试列出键。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileBasedProvider(tmpdir)

            memory.save("key1", "value1")
            memory.save("key2", "value2")

            keys = memory.list_keys()
            assert len(keys) == 2

    def test_clear(self):
        """测试清空。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileBasedProvider(tmpdir)

            memory.save("key1", "value1")
            memory.save("key2", "value2")
            memory.clear()

            assert len(memory.list_keys()) == 0

    def test_metadata(self):
        """测试元数据。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileBasedProvider(tmpdir)

            memory.save("key1", "value1", {"author": "test"})

            meta = memory.get_metadata("key1")
            assert meta == {"author": "test"}


# ── Skills 测试 ──────────────────────────────────────────────

class MockSkill(Skill):
    """测试技能。"""

    @property
    def name(self) -> str:
        return "mock_skill"

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="mock_skill",
            description="A mock skill for testing",
            tags=["test"],
        )

    def get_prompt_template(self) -> str:
        return "这是一个测试技能。"


class TestSkillMetadata:
    """SkillMetadata 测试。"""

    def test_create_metadata(self):
        """测试创建元数据。"""
        meta = SkillMetadata(
            name="test",
            description="Test skill",
            version="2.0.0",
            author="test_author",
            tags=["tag1", "tag2"],
        )

        assert meta.name == "test"
        assert meta.version == "2.0.0"
        assert len(meta.tags) == 2


class TestSkill:
    """Skill 测试。"""

    def test_abstract_property(self):
        """测试抽象属性。"""
        with pytest.raises(TypeError):
            Skill()

    def test_mock_skill(self):
        """测试 MockSkill。"""
        skill = MockSkill()

        assert skill.name == "mock_skill"
        assert skill.metadata.description == "A mock skill for testing"
        assert "test" in skill.metadata.tags

    def test_get_tools(self):
        """测试获取工具。"""
        skill = MockSkill()

        tools = skill.get_tools()
        assert tools == []

    def test_to_dict(self):
        """测试转换为字典。"""
        skill = MockSkill()

        d = skill.to_dict()
        assert d["name"] == "mock_skill"
        assert "metadata" in d


class TestFunctionSkill:
    """FunctionSkill 测试。"""

    def test_create_skill(self):
        """测试创建技能。"""
        skill = FunctionSkill(
            name="test_skill",
            description="Test description",
            prompt_template="Test template",
        )

        assert skill.name == "test_skill"
        assert skill.metadata.description == "Test description"

    def test_get_prompt_template(self):
        """测试获取提示模板。"""
        skill = FunctionSkill(
            name="test",
            prompt_template="Template content",
        )

        assert skill.get_prompt_template() == "Template content"


class TestSkillRegistry:
    """SkillRegistry 测试。"""

    def test_register(self):
        """测试注册技能。"""
        registry = SkillRegistry()
        skill = MockSkill()

        registry.register(skill)
        assert "mock_skill" in registry.list()

    def test_unregister(self):
        """测试取消注册。"""
        registry = SkillRegistry()
        skill = MockSkill()

        registry.register(skill)
        result = registry.unregister("mock_skill")

        assert result is True
        assert "mock_skill" not in registry.list()

    def test_get(self):
        """测试获取技能。"""
        registry = SkillRegistry()
        skill = MockSkill()

        registry.register(skill)
        found = registry.get("mock_skill")

        assert found is skill

    def test_get_nonexistent(self):
        """测试获取不存在的技能。"""
        registry = SkillRegistry()

        found = registry.get("nonexistent")
        assert found is None

    def test_find_by_tag(self):
        """测试按标签查找。"""
        registry = SkillRegistry()
        skill = MockSkill()

        registry.register(skill)
        results = registry.find_by_tag("test")

        assert len(results) == 1
        assert results[0] is skill

    def test_find_by_description(self):
        """测试按描述搜索。"""
        registry = SkillRegistry()
        skill = MockSkill()

        registry.register(skill)
        results = registry.find_by_description("mock")

        assert len(results) == 1

    def test_clear(self):
        """测试清空。"""
        registry = SkillRegistry()
        skill = MockSkill()

        registry.register(skill)
        registry.clear()

        assert len(registry.list()) == 0


class TestSkillLoader:
    """SkillLoader 测试。"""

    def test_load_from_nonexistent_directory(self):
        """测试从不存在的目录加载。"""
        loader = SkillLoader()
        skills = loader.load_from_directory("/nonexistent/path")

        assert skills == []

    def test_load_from_empty_directory(self):
        """测试从空目录加载。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = SkillLoader()
            skills = loader.load_from_directory(tmpdir)

            assert skills == []

    def test_load_json_skill(self):
        """测试从 JSON 文件加载。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建技能定义文件
            skill_file = Path(tmpdir) / "test.skill.json"
            skill_data = {
                "name": "test_skill",
                "description": "Test skill from JSON",
                "version": "1.0.0",
                "tags": ["test"],
            }
            with open(skill_file, "w", encoding="utf-8") as f:
                json.dump(skill_data, f)

            loader = SkillLoader()
            skills = loader.load_from_directory(tmpdir)

            assert len(skills) == 1
            assert skills[0].name == "test_skill"


# ── 集成测试 ──────────────────────────────────────────────

class TestP6Integration:
    """P6 阶段集成测试。"""

    def test_memory_and_skills_integration(self):
        """测试存储与技能集成。"""
        # 创建存储
        memory = InMemoryProvider()

        # 创建技能注册表
        registry = SkillRegistry()
        skill = MockSkill()
        registry.register(skill)

        # 存储技能信息
        memory.save("skill:mock_skill", skill.to_dict())

        # 加载并验证
        data = memory.load("skill:mock_skill")
        assert data["name"] == "mock_skill"

        # 清理
        registry.clear()
        memory.clear()