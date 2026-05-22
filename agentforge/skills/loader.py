"""技能加载器。

从文件系统加载技能定义，支持：
- 单文件技能（YAML/JSON/Python）
- 技能包（包含 SKILL.yaml 和 handler.py 的目录）
- 目录批量发现
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from agentforge.skills.base import Skill, SkillMetadata, FunctionSkill
from agentforge.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillPackage:
    """技能包。

    表示一个完整的技能包，包含：
    - SKILL.yaml：元数据和配置
    - handler.py：技能处理器（可选）
    - tools/：工具目录（可选）
    """

    def __init__(
        self,
        path: Path,
        name: str,
        metadata: SkillMetadata,
        handler: Optional[Callable] = None,
        tools: Optional[List[Any]] = None,
        prompt_template: Optional[str] = None,
    ):
        """初始化技能包。

        Args:
            path: 技能包路径
            name: 技能名称
            metadata: 元数据
            handler: 处理器函数
            tools: 工具列表
            prompt_template: 提示模板
        """
        self.path = path
        self.name = name
        self.metadata = metadata
        self.handler = handler
        self.tools = tools or []
        self.prompt_template = prompt_template

    def to_skill(self) -> Skill:
        """转换为 Skill 实例。"""
        return FunctionSkill(
            name=self.name,
            tools=self.tools,
            prompt_template=self.prompt_template,
            metadata=self.metadata,
        )


class SkillLoader:
    """技能加载器。

    功能：
    - 从目录加载技能
    - 从 YAML/JSON 文件加载技能定义
    - 从 Python 模块加载技能类
    - 技能包发现（包含 SKILL.yaml 的目录）
    - 自动注册

    使用示例：
        loader = SkillLoader()

        # 加载单个技能包
        skill = loader.load_skill_package("/path/to/skill_dir")

        # 扫描技能目录
        skills = loader.discover_skills("/path/to/skills")

        # 注册到全局注册表
        for skill in skills:
            register_skill(skill)
    """

    # 技能包元数据文件名
    SKILL_MANIFEST_FILES = ["SKILL.yaml", "SKILL.yml", "skill.yaml", "skill.yml"]

    # 技能处理器文件名
    SKILL_HANDLER_FILES = ["handler.py", "skill.py", "__init__.py"]

    def __init__(self, registry: Optional[SkillRegistry] = None):
        """初始化技能加载器。

        Args:
            registry: 技能注册表（可选，默认使用全局注册表）
        """
        self._registry = registry or SkillRegistry()
        self._loaded_packages: Dict[str, SkillPackage] = {}

    def discover_skills(
        self,
        directory: str,
        recursive: bool = True,
        auto_register: bool = False,
    ) -> List[Skill]:
        """发现并加载目录中的所有技能。

        扫描目录，识别技能包和技能文件。

        Args:
            directory: 目录路径
            recursive: 是否递归扫描
            auto_register: 是否自动注册到注册表

        Returns:
            加载的技能列表
        """
        skills = []
        dir_path = Path(directory)

        if not dir_path.exists():
            logger.warning(f"技能目录不存在: {directory}")
            return skills

        # 首先扫描技能包（包含 SKILL.yaml 的目录）
        if recursive:
            for subdir in dir_path.iterdir():
                if subdir.is_dir() and not subdir.name.startswith("_"):
                    skill = self.load_skill_package(subdir)
                    if skill:
                        skills.append(skill)
                        if auto_register:
                            self._registry.register(skill)
        else:
            # 非递归：只检查顶层目录
            skill = self.load_skill_package(dir_path)
            if skill:
                skills.append(skill)
                if auto_register:
                    self._registry.register(skill)

        # 然后扫描单文件技能
        single_file_skills = self._load_single_file_skills(dir_path, recursive)
        for skill in single_file_skills:
            skills.append(skill)
            if auto_register:
                self._registry.register(skill)

        logger.info(f"从 {directory} 发现 {len(skills)} 个技能")
        return skills

    def load_skill_package(self, package_dir: Path) -> Optional[Skill]:
        """加载技能包。

        技能包是一个目录，包含：
        - SKILL.yaml：元数据
        - handler.py：处理器（可选）
        - tools/：工具目录（可选）

        Args:
            package_dir: 技能包目录路径

        Returns:
            Skill 实例
        """
        if not package_dir.is_dir():
            return None

        # 查找元数据文件
        manifest_path = None
        for filename in self.SKILL_MANIFEST_FILES:
            candidate = package_dir / filename
            if candidate.exists():
                manifest_path = candidate
                break

        if manifest_path is None:
            logger.debug(f"目录 {package_dir} 不是技能包（缺少 SKILL.yaml）")
            return None

        try:
            # 加载元数据
            metadata = self._load_manifest(manifest_path)
            if metadata is None:
                return None

            # 加载处理器
            handler = self._load_handler(package_dir)

            # 加载工具
            tools = self._load_tools_from_package(package_dir)

            # 加载提示模板
            prompt_template = self._load_prompt_template(package_dir)

            # 创建技能包
            package = SkillPackage(
                path=package_dir,
                name=metadata.name,
                metadata=metadata,
                handler=handler,
                tools=tools,
                prompt_template=prompt_template,
            )

            self._loaded_packages[metadata.name] = package
            logger.info(f"已加载技能包: {metadata.name} ({package_dir})")

            return package.to_skill()

        except Exception as e:
            logger.error(f"加载技能包 {package_dir} 失败: {e}")
            return None

    def _load_manifest(self, manifest_path: Path) -> Optional[SkillMetadata]:
        """加载技能元数据。"""
        try:
            import yaml
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                return None

            name = data.get("name", manifest_path.parent.name)
            return SkillMetadata(
                name=name,
                description=data.get("description", ""),
                version=data.get("version", "1.0.0"),
                author=data.get("author", ""),
                tags=data.get("tags", []),
                dependencies=data.get("dependencies", []),
            )

        except ImportError:
            logger.warning("yaml 库未安装，无法加载 YAML 技能文件")
            return None
        except Exception as e:
            logger.error(f"加载元数据 {manifest_path} 失败: {e}")
            return None

    def _load_handler(self, package_dir: Path) -> Optional[Callable]:
        """加载技能处理器。"""
        for filename in self.SKILL_HANDLER_FILES:
            handler_path = package_dir / filename
            if handler_path.exists():
                try:
                    return self._load_function_from_file(handler_path, "handle")
                except Exception as e:
                    logger.debug(f"加载处理器 {handler_path} 失败: {e}")

        return None

    def _load_tools_from_package(self, package_dir: Path) -> List[Any]:
        """从技能包加载工具。"""
        tools: List[Any] = []
        tools_dir = package_dir / "tools"

        if not tools_dir.exists():
            return tools

        for tool_file in tools_dir.glob("*.py"):
            if tool_file.name.startswith("_"):
                continue

            try:
                # 尝试加载工具类或函数
                tool = self._load_function_from_file(tool_file, "tool")
                if tool:
                    tools.append(tool)
            except Exception as e:
                logger.debug(f"加载工具 {tool_file} 失败: {e}")

        return tools

    def _load_prompt_template(self, package_dir: Path) -> Optional[str]:
        """加载提示模板。"""
        template_path = package_dir / "prompt.md"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")

        template_path = package_dir / "template.md"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")

        return None

    def _load_function_from_file(
        self,
        file_path: Path,
        function_name: str,
    ) -> Optional[Callable]:
        """从 Python 文件加载指定函数。"""
        module_name = f"skill_{file_path.parent.name}_{file_path.stem}"

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
            return getattr(module, function_name, None)
        except Exception:
            sys.modules.pop(module_name, None)
            raise

    def _load_single_file_skills(
        self,
        directory: Path,
        recursive: bool,
    ) -> List[Skill]:
        """加载单文件技能。"""
        skills = []

        # 技能定义文件模式
        patterns = ["*.skill.yaml", "*.skill.yml", "*.skill.json", "SKILL.md"]
        if recursive:
            patterns = [f"**/{p}" for p in patterns]

        for pattern in patterns:
            for file_path in directory.glob(pattern):
                # 跳过技能包目录中的文件
                if self._is_in_skill_package(file_path):
                    continue

                try:
                    skill = self._load_skill_file(file_path)
                    if skill:
                        skills.append(skill)
                except Exception as e:
                    logger.warning(f"加载技能文件失败 {file_path}: {e}")

        # Python 模块
        py_pattern = "**/*.py" if recursive else "*.py"
        for file_path in directory.glob(py_pattern):
            if file_path.name.startswith("_"):
                continue
            if self._is_in_skill_package(file_path):
                continue

            try:
                skill = self._load_python_module(file_path)
                if skill:
                    skills.append(skill)
            except Exception as e:
                logger.debug(f"加载 Python 模块失败 {file_path}: {e}")

        return skills

    def _is_in_skill_package(self, file_path: Path) -> bool:
        """检查文件是否在技能包目录中。"""
        parent = file_path.parent
        for manifest_file in self.SKILL_MANIFEST_FILES:
            if (parent / manifest_file).exists():
                return True
        return False

    def load_from_directory(
        self,
        directory: str,
        recursive: bool = False,
    ) -> List[Skill]:
        """从目录加载技能（兼容旧接口）。

        Args:
            directory: 目录路径
            recursive: 是否递归加载

        Returns:
            加载的技能列表
        """
        return self.discover_skills(directory, recursive=recursive)

    def _load_skill_file(self, file_path: Path) -> Optional[Skill]:
        """从技能定义文件加载。

        Args:
            file_path: 文件路径

        Returns:
            Skill 实例
        """
        if file_path.suffix in (".yaml", ".yml"):
            return self._load_yaml_skill(file_path)
        elif file_path.suffix == ".json":
            return self._load_json_skill(file_path)
        elif file_path.name == "SKILL.md":
            return self._load_markdown_skill(file_path)

        return None

    def _load_yaml_skill(self, file_path: Path) -> Optional[Skill]:
        """从 YAML 文件加载技能。"""
        try:
            import yaml
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            return self._create_skill_from_dict(data)
        except ImportError:
            logger.warning("yaml 库未安装，无法加载 YAML 技能文件")
            return None

    def _load_json_skill(self, file_path: Path) -> Optional[Skill]:
        """从 JSON 文件加载技能。"""
        import json
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return self._create_skill_from_dict(data)

    def _load_markdown_skill(self, file_path: Path) -> Optional[Skill]:
        """从 Markdown 文件加载技能。"""
        content = file_path.read_text(encoding="utf-8")

        # 提取技能名称（从文件名或内容）
        name = file_path.parent.name

        # 提取描述（从内容）
        lines = content.split("\n")
        description = ""
        for line in lines:
            if line.startswith("#") and not line.startswith("##"):
                description = line.lstrip("#").strip()
                break

        return FunctionSkill(
            name=name,
            description=description,
            prompt_template=content,
        )

    def _create_skill_from_dict(self, data: Dict[str, Any]) -> Optional[Skill]:
        """从字典创建技能。"""
        if not data:
            return None

        name = data.get("name")
        if not name:
            return None

        metadata = SkillMetadata(
            name=name,
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            tags=data.get("tags", []),
        )

        return FunctionSkill(
            name=name,
            description=metadata.description,
            metadata=metadata,
            prompt_template=data.get("prompt_template"),
        )

    def _load_python_module(self, file_path: Path) -> Optional[Skill]:
        """从 Python 模块加载技能。"""
        module_name = file_path.stem

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 查找 Skill 子类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, Skill) and attr is not Skill:
                try:
                    return attr()
                except Exception as e:
                    logger.debug(f"创建技能实例失败 {attr_name}: {e}")

        return None

    def register_loaded_skills(self, skills: List[Skill]) -> None:
        """注册加载的技能。

        Args:
            skills: 技能列表
        """
        for skill in skills:
            self._registry.register(skill)

    def get_loaded_packages(self) -> Dict[str, SkillPackage]:
        """获取已加载的技能包。"""
        return self._loaded_packages.copy()

    def reload_skill_package(self, name: str) -> Optional[Skill]:
        """重新加载技能包。

        Args:
            name: 技能名称

        Returns:
            重新加载的 Skill 实例
        """
        package = self._loaded_packages.get(name)
        if package is None:
            return None

        # 先取消注册
        self._registry.unregister(name)

        # 重新加载
        return self.load_skill_package(package.path)


def discover_and_load_skills(
    directories: List[str],
    recursive: bool = True,
    auto_register: bool = True,
) -> List[Skill]:
    """发现并加载多个目录中的技能。

    Args:
        directories: 目录列表
        recursive: 是否递归扫描
        auto_register: 是否自动注册

    Returns:
        加载的技能列表
    """
    loader = SkillLoader()
    all_skills = []

    for directory in directories:
        skills = loader.discover_skills(directory, recursive, auto_register)
        all_skills.extend(skills)

    return all_skills


class SkillHotReloader:
    """技能热重载器。

    监听技能目录的文件变更，自动重新加载技能。

    使用示例：
        reloader = SkillHotReloader(
            directories=["/path/to/skills"],
            on_reload=lambda skill: print(f"重新加载: {skill.name}"),
        )
        reloader.start()

        # 后台监听...
        reloader.stop()
    """

    def __init__(
        self,
        directories: List[str],
        registry: Optional[SkillRegistry] = None,
        on_reload: Optional[Callable[[Skill], None]] = None,
        on_error: Optional[Callable[[str, Exception], None]] = None,
        debounce_seconds: float = 1.0,
    ):
        """初始化热重载器。

        Args:
            directories: 要监听的目录列表
            registry: 技能注册表（可选）
            on_reload: 重载成功回调
            on_error: 错误回调
            debounce_seconds: 防抖秒数
        """
        self._directories = [Path(d) for d in directories]
        self._registry = registry or SkillRegistry()
        self._on_reload = on_reload
        self._on_error = on_error
        self._debounce_seconds = debounce_seconds

        self._loader = SkillLoader(self._registry)
        self._running = False
        self._observer: Optional[Any] = None
        self._pending_reloads: Dict[str, float] = {}
        self._reload_lock = threading.Lock()
        self._reload_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """开始监听文件变更。"""
        if self._running:
            return

        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileSystemEvent

            class SkillFileHandler(FileSystemEventHandler):
                def __init__(self, reloader: "SkillHotReloader"):
                    self._reloader = reloader

                def on_modified(self, event: FileSystemEvent) -> None:
                    if event.is_directory:
                        return
                    self._reloader._schedule_reload(event.src_path)

                def on_created(self, event: FileSystemEvent) -> None:
                    if event.is_directory:
                        return
                    self._reloader._schedule_reload(event.src_path)

            self._observer = Observer()
            handler = SkillFileHandler(self)

            for directory in self._directories:
                if directory.exists():
                    self._observer.schedule(handler, str(directory), recursive=True)

            self._observer.start()
            self._running = True

            # 启动重载处理线程
            self._reload_thread = threading.Thread(target=self._process_reloads, daemon=True)
            self._reload_thread.start()

            logger.info(f"技能热重载已启动，监听目录: {[str(d) for d in self._directories]}")

        except ImportError:
            logger.warning("watchdog 库未安装，热重载功能不可用。请运行: pip install watchdog")
            self._running = False

    def stop(self) -> None:
        """停止监听。"""
        if not self._running:
            return

        self._running = False

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

        logger.info("技能热重载已停止")

    def _schedule_reload(self, file_path: str) -> None:
        """安排重载任务。

        Args:
            file_path: 变更的文件路径
        """
        path = Path(file_path)

        # 只处理技能相关文件
        if not self._is_skill_file(path):
            return

        with self._reload_lock:
            self._pending_reloads[file_path] = time.time()

    def _is_skill_file(self, path: Path) -> bool:
        """检查文件是否是技能文件。"""
        name = path.name.lower()

        # 技能定义文件
        if name in ["skill.yaml", "skill.yml", "skill.json"]:
            return True

        # Python 文件
        if name.endswith(".py") and not name.startswith("_"):
            return True

        return False

    def _process_reloads(self) -> None:
        """处理待重载任务。"""
        while self._running:
            time.sleep(0.5)

            with self._reload_lock:
                now = time.time()
                to_reload = []

                for file_path, scheduled_time in list(self._pending_reloads.items()):
                    if now - scheduled_time >= self._debounce_seconds:
                        to_reload.append(file_path)
                        del self._pending_reloads[file_path]

            for file_path in to_reload:
                self._reload_skill(file_path)

    def _reload_skill(self, file_path: str) -> None:
        """重新加载技能。

        Args:
            file_path: 文件路径
        """
        path = Path(file_path)
        logger.debug(f"重新加载技能文件: {path}")

        try:
            # 确定技能包目录
            skill_dir = path.parent if path.name.lower() in ["skill.yaml", "skill.yml", "skill.json"] else None

            if skill_dir:
                # 重新加载技能包
                skill = self._loader.load_skill_package(skill_dir)
                if skill:
                    # 先取消注册旧技能
                    self._registry.unregister(skill.name)
                    # 注册新技能
                    self._registry.register(skill)

                    if self._on_reload:
                        self._on_reload(skill)

                    logger.info(f"已重新加载技能包: {skill.name}")

            else:
                # 重新加载单文件技能
                skill = self._loader._load_skill_file(path)
                if skill:
                    self._registry.unregister(skill.name)
                    self._registry.register(skill)

                    if self._on_reload:
                        self._on_reload(skill)

                    logger.info(f"已重新加载技能文件: {skill.name}")

        except Exception as e:
            logger.error(f"重新加载技能失败 {file_path}: {e}")
            if self._on_error:
                self._on_error(file_path, e)

    def force_reload(self, skill_name: str) -> Optional[Skill]:
        """强制重新加载指定技能。

        Args:
            skill_name: 技能名称

        Returns:
            重新加载的技能
        """
        # 查找技能包
        package = self._loader._loaded_packages.get(skill_name)
        if package:
            return self._loader.reload_skill_package(skill_name)

        # 尝试从注册表中找到技能并重新加载
        skill = self._registry.get(skill_name)
        if skill:
            logger.warning(f"无法热重载技能 {skill_name}：未找到技能包路径")
            return None

        return None

    def __enter__(self) -> "SkillHotReloader":
        """上下文管理器入口。"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口。"""
        self.stop()


import time
import threading


__all__ = [
    "SkillLoader",
    "SkillPackage",
    "discover_and_load_skills",
    "SkillHotReloader",
]