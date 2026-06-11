"""
QA Generator V2 - 基于NuScenesQA风格的问答生成器
"""

from .config import *
from .camera_mapper import CameraMapper
from .template_library import get_template_library, TemplateLibrary, TemplateEntry
from .template_filler import TemplateFiller, GeneratedQA
from .coverage_driven_template_generator import CoverageDrivenTemplateGenerator, CoverageGoal

__version__ = "2.1.0"
