"""Shared pytest fixtures for pet-aes.

pet-aes 共用的 pytest fixture。

Nothing shared is needed yet - each test file defines its own small,
local fixtures (a temp prompt file, a fake tool registry, and so on)
right next to the tests that use them, so this file stays a placeholder
until something is genuinely shared across multiple test modules.
目前还没有需要跨文件共享的东西 —— 每个测试文件都在自己旁边定义了需要的
小型本地 fixture(一个临时提示词文件、一个假的工具 registry 等等),所以
在真正有东西需要跨多个测试模块共享之前,这个文件就先保持这个占位状态。
"""
