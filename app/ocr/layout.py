"""Layout analysis, reading order, multi-column detection, and paragraph reconstruction."""

from typing import List
from PySide6.QtCore import QRect

from app.ocr.models import (
    OCRBlock,
    OCRLine,
    OCRParagraph,
    OCRStructuredResult,
    OCRWord,
    ReadingOrderMode,
)


class LayoutAnalyzer:
    """Reconstructs reading order, multi-column layouts, and paragraphs from detected tokens."""

    @classmethod
    def structure_tokens(
        cls,
        words: List[OCRWord],
        image_width: int,
        image_height: int,
        language: str = "tr",
        strategy: ReadingOrderMode = ReadingOrderMode.NATURAL,
        provider_name: str = "Local Engine",
    ) -> OCRStructuredResult:
        """Group flat words into lines, paragraphs, and blocks with correct reading order."""
        if not words:
            return OCRStructuredResult(
                blocks=[],
                full_text="",
                average_confidence=1.0,
                language=language,
                reading_order=strategy.value,
                image_width=image_width,
                image_height=image_height,
                provider_name=provider_name,
            )

        # 1. Sort words by (top, left)
        sorted_words = sorted(words, key=lambda w: (w.bounding_box.top(), w.bounding_box.left()))

        # 2. Group into lines based on vertical overlap and horizontal proximity
        raw_lines: List[List[OCRWord]] = []
        for w in sorted_words:
            placed = False
            w_top = w.bounding_box.top()
            w_bottom = w.bounding_box.bottom()
            w_h = max(1, w.bounding_box.height())
            w_left = w.bounding_box.left()
            w_right = w.bounding_box.right()

            for line_words in raw_lines:
                # Compare with the words in the line
                l_top = line_words[0].bounding_box.top()
                l_bottom = line_words[0].bounding_box.bottom()
                l_h = max(1, line_words[0].bounding_box.height())

                # Check if vertical centers or overlaps match (> 40% vertical overlap)
                overlap_top = max(w_top, l_top)
                overlap_bottom = min(w_bottom, l_bottom)
                overlap_h = max(0, overlap_bottom - overlap_top)

                if overlap_h > 0.4 * min(w_h, l_h):
                    # Check horizontal distance: if distance to closest word in this line is > 100px and > 15% image width, keep separate
                    min_h_dist = min(
                        abs(w_left - existing_w.bounding_box.right())
                        if w_left >= existing_w.bounding_box.right()
                        else abs(existing_w.bounding_box.left() - w_right)
                        for existing_w in line_words
                    )
                    max_allowed_gap = max(90, int(image_width * 0.18))
                    if min_h_dist < max_allowed_gap:
                        line_words.append(w)
                        placed = True
                        break

            if not placed:
                raw_lines.append([w])

        # 3. Sort each line's words from left to right and create OCRLine instances
        ocr_lines: List[OCRLine] = []
        for line_idx, line_words in enumerate(raw_lines):
            line_words.sort(key=lambda w: w.bounding_box.left())
            for w_idx, w in enumerate(line_words):
                w.word_index = w_idx
                w.line_index = line_idx

            line_obj = OCRLine(
                words=line_words,
                line_index=line_idx,
            )
            ocr_lines.append(line_obj)

        # 4. Check for Multi-Column Structure
        columns = cls._detect_columns(ocr_lines, image_width)

        blocks: List[OCRBlock] = []
        block_idx = 0

        for col_idx, col_lines in enumerate(columns):
            # Sort lines top-to-bottom within column
            col_lines.sort(key=lambda l: l.bounding_box.top())

            # Group lines into paragraphs based on line spacing
            paragraphs = cls._group_lines_into_paragraphs(col_lines, block_idx)

            for p_idx, p in enumerate(paragraphs):
                p.paragraph_index = p_idx
                p.block_index = block_idx

            block = OCRBlock(
                paragraphs=paragraphs,
                block_index=block_idx,
                column_index=col_idx,
            )
            # Update parent block references in words/lines
            for p in block.paragraphs:
                for l in p.lines:
                    l.block_index = block_idx
                    for w in l.words:
                        w.block_index = block_idx
                        w.id = f"w_{block_idx}_{l.line_index}_{w.word_index}"

            blocks.append(block)
            block_idx += 1

        full_text = "\n\n".join(b.text for b in blocks if b.text.strip())
        all_words = []
        for b in blocks:
            all_words.extend(b.get_all_words())
        avg_conf = sum(w.confidence for w in all_words) / len(all_words) if all_words else 1.0

        return OCRStructuredResult(
            blocks=blocks,
            full_text=full_text,
            average_confidence=avg_conf,
            language=language,
            reading_order="multi_column" if len(columns) > 1 else "natural",
            image_width=image_width,
            image_height=image_height,
            provider_name=provider_name,
        )

    @classmethod
    def _detect_columns(cls, lines: List[OCRLine], image_width: int) -> List[List[OCRLine]]:
        """Detect distinct vertical columns by analyzing horizontal gaps and bounds."""
        if len(lines) < 4:
            return [lines]

        # Check for vertical boundary separating columns
        mid_x = image_width / 2.0
        left_lines = []
        right_lines = []
        spanning_lines = []

        for line in lines:
            cx = line.bounding_box.center().x()
            if line.bounding_box.width() > image_width * 0.7:
                spanning_lines.append(line)
            elif cx < mid_x:
                left_lines.append(line)
            else:
                right_lines.append(line)

        # If both left and right columns have multiple distinct lines
        if len(left_lines) >= 2 and len(right_lines) >= 2 and len(spanning_lines) <= max(1, len(lines) // 3):
            # Two columns detected
            col1 = sorted(left_lines, key=lambda l: l.bounding_box.top())
            col2 = sorted(right_lines, key=lambda l: l.bounding_box.top())
            if spanning_lines:
                top_spanning = [l for l in spanning_lines if l.bounding_box.top() < min(col1[0].bounding_box.top(), col2[0].bounding_box.top())]
                bottom_spanning = [l for l in spanning_lines if l not in top_spanning]
                result = []
                if top_spanning:
                    result.append(top_spanning)
                result.append(col1)
                result.append(col2)
                if bottom_spanning:
                    result.append(bottom_spanning)
                return result
            return [col1, col2]

        return [lines]

    @classmethod
    def _group_lines_into_paragraphs(cls, lines: List[OCRLine], block_index: int) -> List[OCRParagraph]:
        """Group sequential lines into paragraphs based on vertical line spacing."""
        if not lines:
            return []

        paragraphs: List[OCRParagraph] = []
        current_p_lines: List[OCRLine] = [lines[0]]

        for i in range(1, len(lines)):
            prev_line = lines[i - 1]
            curr_line = lines[i]

            prev_h = max(10, prev_line.bounding_box.height())
            v_gap = curr_line.bounding_box.top() - prev_line.bounding_box.bottom()

            # If vertical gap is significantly larger than regular line spacing (e.g. > 1.4x line height), split paragraph
            if v_gap > 1.4 * prev_h:
                para = OCRParagraph(lines=current_p_lines, paragraph_index=len(paragraphs), block_index=block_index)
                paragraphs.append(para)
                current_p_lines = [curr_line]
            else:
                current_p_lines.append(curr_line)

        if current_p_lines:
            para = OCRParagraph(lines=current_p_lines, paragraph_index=len(paragraphs), block_index=block_index)
            paragraphs.append(para)

        return paragraphs

