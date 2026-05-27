"""Mixin classes used to split MainWindow by feature area."""

from .file_metadata import FileMetadataMixin
from .queue import QueueFlowMixin
from .run_flow import RunFlowMixin
from .shell import ShellMixin
from .templates import TemplateCategoryMixin
from .ui_wiring import UiWiringMixin

__all__ = [
	"FileMetadataMixin",
	"QueueFlowMixin",
	"RunFlowMixin",
	"ShellMixin",
	"TemplateCategoryMixin",
	"UiWiringMixin",
]
