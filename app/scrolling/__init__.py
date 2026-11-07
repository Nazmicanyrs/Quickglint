"""Scrolling screenshot module for Quickglint."""

from app.scrolling.controller import ScrollingCaptureController
from app.scrolling.editor_dialog import ScrollingEditorDialog
from app.scrolling.overlap import find_vertical_overlap
from app.scrolling.stitcher import ImageStitcher

__all__ = [
    "ScrollingCaptureController",
    "ScrollingEditorDialog",
    "find_vertical_overlap",
    "ImageStitcher",
]

