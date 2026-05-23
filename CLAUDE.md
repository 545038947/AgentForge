# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述
本项目 HAI-Agent 是一个独立、可复用的 Agent 框架库，从 hermes-agent 的成熟架构中提取并重构，为其他应用提供：

- **便捷的高层 API**：应用开发者可快速构建 Agent 应用
- **灵活的扩展点**：框架开发者可定制 Provider、Tool、Memory 等组件
- **中国大模型友好**：内置支持 Kimi、通义千问、DeepSeek 等国产大模型
- **跨平台兼容**：支持 Windows、Linux、macOS

## 项目语言规范

请严格遵守以下规则：
1. 所有对话、解释、建议必须使用**简体中文**。
2. 代码注释必须使用中文。
3. 生成的 Commit Message 必须使用中文。
4. 严禁出现大段未翻译的英文技术名词（保留专业术语如 API、SDK 除外）。