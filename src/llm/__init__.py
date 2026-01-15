"""LLM module for YandexGPT integration."""
from .yandex import parse_task_with_llm, TaskParseResult

__all__ = ["parse_task_with_llm", "TaskParseResult"]
