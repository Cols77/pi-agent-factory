"""Markdown-native course checker: `coherence course check`."""

from __future__ import annotations

from coherence.course.check import CourseReport, check_course
from coherence.course.parser import CourseNote

__all__ = ["CourseNote", "CourseReport", "check_course"]
