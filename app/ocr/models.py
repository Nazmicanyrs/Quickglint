"""Data models for structured Optical Character Recognition (OCR)."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Set
from PySide6.QtCore import QRect


class ReadingOrderMode(Enum):
    """Reading order strategy."""
    NATURAL = "natural"  # Top-to-bottom, Left-to-right (single column)
    MULTI_COLUMN = "multi_column"  # Column by column (newspaper / article style)


@dataclass
class OCRWord:
    """Individual recognized word with exact bounding box and confidence."""
    text: str
    confidence: float
    bounding_box: QRect
    word_index: int = 0
    line_index: int = 0
    block_index: int = 0
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"w_{self.block_index}_{self.line_index}_{self.word_index}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "bbox": [
                self.bounding_box.x(),
                self.bounding_box.y(),
                self.bounding_box.width(),
                self.bounding_box.height(),
            ],
            "word_index": self.word_index,
            "line_index": self.line_index,
            "block_index": self.block_index,
        }


@dataclass
class OCRLine:
    """A line of text consisting of one or more OCRWords."""
    words: List[OCRWord] = field(default_factory=list)
    text: str = ""
    confidence: float = 1.0
    bounding_box: QRect = field(default_factory=QRect)
    line_index: int = 0
    block_index: int = 0
    id: str = ""

    def __post_init__(self) -> None:
        if not self.text and self.words:
            self.text = " ".join(w.text for w in self.words if w.text)
        if not self.id:
            self.id = f"l_{self.block_index}_{self.line_index}"
        if self.words and (self.bounding_box.isNull() or self.bounding_box.isEmpty()):
            self._recompute_bounds()

    def _recompute_bounds(self) -> None:
        if not self.words:
            return
        min_x = min(w.bounding_box.left() for w in self.words)
        min_y = min(w.bounding_box.top() for w in self.words)
        max_r = max(w.bounding_box.right() for w in self.words)
        max_b = max(w.bounding_box.bottom() for w in self.words)
        self.bounding_box = QRect(min_x, min_y, max(1, max_r - min_x + 1), max(1, max_b - min_y + 1))
        if self.words:
            self.confidence = sum(w.confidence for w in self.words) / len(self.words)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "bbox": [
                self.bounding_box.x(),
                self.bounding_box.y(),
                self.bounding_box.width(),
                self.bounding_box.height(),
            ],
            "line_index": self.line_index,
            "words": [w.to_dict() for w in self.words],
        }


@dataclass
class OCRParagraph:
    """A cohesive paragraph of text consisting of multiple lines."""
    lines: List[OCRLine] = field(default_factory=list)
    text: str = ""
    confidence: float = 1.0
    bounding_box: QRect = field(default_factory=QRect)
    paragraph_index: int = 0
    block_index: int = 0

    def __post_init__(self) -> None:
        if not self.text and self.lines:
            self.text = "\n".join(line.text for line in self.lines if line.text)
        if self.lines and (self.bounding_box.isNull() or self.bounding_box.isEmpty()):
            self._recompute_bounds()

    def _recompute_bounds(self) -> None:
        if not self.lines:
            return
        min_x = min(l.bounding_box.left() for l in self.lines)
        min_y = min(l.bounding_box.top() for l in self.lines)
        max_r = max(l.bounding_box.right() for l in self.lines)
        max_b = max(l.bounding_box.bottom() for l in self.lines)
        self.bounding_box = QRect(min_x, min_y, max(1, max_r - min_x + 1), max(1, max_b - min_y + 1))
        if self.lines:
            self.confidence = sum(l.confidence for l in self.lines) / len(self.lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "bbox": [
                self.bounding_box.x(),
                self.bounding_box.y(),
                self.bounding_box.width(),
                self.bounding_box.height(),
            ],
            "paragraph_index": self.paragraph_index,
            "lines": [l.to_dict() for l in self.lines],
        }


@dataclass
class OCRBlock:
    """A structural text block (e.g. paragraph block, header, column block)."""
    paragraphs: List[OCRParagraph] = field(default_factory=list)
    text: str = ""
    confidence: float = 1.0
    bounding_box: QRect = field(default_factory=QRect)
    block_index: int = 0
    column_index: int = 0

    def __post_init__(self) -> None:
        if not self.text and self.paragraphs:
            self.text = "\n\n".join(p.text for p in self.paragraphs if p.text)
        if self.paragraphs and (self.bounding_box.isNull() or self.bounding_box.isEmpty()):
            self._recompute_bounds()

    def _recompute_bounds(self) -> None:
        if not self.paragraphs:
            return
        min_x = min(p.bounding_box.left() for p in self.paragraphs)
        min_y = min(p.bounding_box.top() for p in self.paragraphs)
        max_r = max(p.bounding_box.right() for p in self.paragraphs)
        max_b = max(p.bounding_box.bottom() for p in self.paragraphs)
        self.bounding_box = QRect(min_x, min_y, max(1, max_r - min_x + 1), max(1, max_b - min_y + 1))
        if self.paragraphs:
            self.confidence = sum(p.confidence for p in self.paragraphs) / len(self.paragraphs)

    def get_all_words(self) -> List[OCRWord]:
        words = []
        for p in self.paragraphs:
            for l in p.lines:
                words.extend(l.words)
        return words

    def get_all_lines(self) -> List[OCRLine]:
        lines = []
        for p in self.paragraphs:
            lines.extend(p.lines)
        return lines

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "bbox": [
                self.bounding_box.x(),
                self.bounding_box.y(),
                self.bounding_box.width(),
                self.bounding_box.height(),
            ],
            "block_index": self.block_index,
            "column_index": self.column_index,
            "paragraphs": [p.to_dict() for p in self.paragraphs],
        }


@dataclass
class OCRStructuredResult:
    """Complete structured output of an OCR extraction session."""
    blocks: List[OCRBlock] = field(default_factory=list)
    full_text: str = ""
    average_confidence: float = 1.0
    language: str = "tr"
    reading_order: str = "natural"
    image_width: int = 0
    image_height: int = 0
    execution_time_ms: float = 0.0
    is_enhanced: bool = False
    orientation_degrees: int = 0
    provider_name: str = "Local Engine"

    def __post_init__(self) -> None:
        if not self.full_text and self.blocks:
            self.full_text = "\n\n".join(b.text for b in self.blocks if b.text.strip())
        if self.blocks and self.average_confidence == 1.0:
            words = self.get_all_words()
            if words:
                self.average_confidence = sum(w.confidence for w in words) / len(words)

    def get_all_words(self) -> List[OCRWord]:
        words = []
        for b in self.blocks:
            words.extend(b.get_all_words())
        return words

    def get_all_lines(self) -> List[OCRLine]:
        lines = []
        for b in self.blocks:
            lines.extend(b.get_all_lines())
        return lines

    def get_selected_text(self, selected_word_ids: Set[str]) -> str:
        """Construct well-formatted text from only the selected word tokens in natural order."""
        if not selected_word_ids:
            return ""

        result_paras = []
        for b in self.blocks:
            for p in b.paragraphs:
                para_lines = []
                for l in p.lines:
                    line_words = [w.text for w in l.words if w.id in selected_word_ids]
                    if line_words:
                        para_lines.append(" ".join(line_words))
                if para_lines:
                    result_paras.append("\n".join(para_lines))

        return "\n\n".join(result_paras)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.full_text,
            "language": self.language,
            "confidence": round(self.average_confidence, 4),
            "reading_order": self.reading_order,
            "orientation_degrees": self.orientation_degrees,
            "image_size": [self.image_width, self.image_height],
            "execution_time_ms": round(self.execution_time_ms, 2),
            "blocks": [b.to_dict() for b in self.blocks],
        }

