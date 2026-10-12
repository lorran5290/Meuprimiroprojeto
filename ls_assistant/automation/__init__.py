"""Automação: execução de pedidos em segundo plano, cancelável e com progresso."""

from ls_assistant.automation.runner import BusyError, TaskRunner

__all__ = ["BusyError", "TaskRunner"]
