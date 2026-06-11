"""
QA Generator Package - 基于Source Frame的问答对生成器
"""
from .generator import QAGenerator, QAPair
from .templates import QATemplates
from .config import QA_CONFIG
from . import cypher_generator

__all__ = ['QAGenerator', 'QAPair', 'QATemplates', 'QA_CONFIG', 'cypher_generator']
