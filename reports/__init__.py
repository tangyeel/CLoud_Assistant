"""
reports module initialization.
"""
from reports.morning import run_morning_report
from reports.evening import run_evening_report

__all__ = ["run_morning_report", "run_evening_report"]
