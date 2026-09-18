"""Raporlama katmanı — 11.7 / 15: şablon her zaman çalışır; LLM yalnızca kanıta bağlı özet üretir (ADR-002)."""

from ztp.reporting.llm import LLMReporter
from ztp.reporting.template import TemplateReporter, describe_hit, deterministic_summary

__all__ = ["LLMReporter", "TemplateReporter", "describe_hit", "deterministic_summary"]
