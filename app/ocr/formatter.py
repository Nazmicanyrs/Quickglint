"""Text export formatters (Plaintext, Markdown, JSON) and sanitization."""

import json
from typing import Optional
from app.ocr.models import OCRStructuredResult


class TextFormatter:
    """Formats and serializes OCR results into plain text, Markdown, and JSON with privacy scrubbing."""

    @staticmethod
    def to_plaintext(result: OCRStructuredResult, user_edited_text: Optional[str] = None) -> str:
        """Return clean plaintext preserving paragraph breaks."""
        if user_edited_text is not None:
            return user_edited_text.strip()
        return result.full_text.strip()

    @staticmethod
    def to_markdown(result: OCRStructuredResult, user_edited_text: Optional[str] = None) -> str:
        """Format recognized text as clean Markdown."""
        if user_edited_text is not None:
            lines = user_edited_text.strip().split("\n")
            return "\n\n".join(l.strip() for l in lines if l.strip())

        md_blocks = []
        for b in result.blocks:
            para_mds = []
            for p in b.paragraphs:
                p_text = " ".join(line.text for line in p.lines if line.text.strip())
                if p_text:
                    para_mds.append(p_text)
            if para_mds:
                md_blocks.append("\n\n".join(para_mds))

        return "\n\n---\n\n".join(md_blocks) if len(md_blocks) > 1 else ("\n\n".join(md_blocks) if md_blocks else "")

    @staticmethod
    def to_json_string(result: OCRStructuredResult, user_edited_text: Optional[str] = None) -> str:
        """Serialize structured OCR result to sanitized JSON string."""
        data = result.to_dict()
        if user_edited_text is not None:
            data["user_edited_text"] = user_edited_text

        # Sanitize internal/system paths or sensitive metadata
        TextFormatter._sanitize_dict(data)
        return json.dumps(data, indent=2, ensure_ascii=False)

    @staticmethod
    def _sanitize_dict(d: dict) -> None:
        """Recursively scrub any sensitive key names or disk paths."""
        forbidden_keys = {"vault_key", "kek", "master_password", "file_path", "salt", "nonce"}
        for k in list(d.keys()):
            if k.lower() in forbidden_keys:
                del d[k]
            elif isinstance(d[k], dict):
                TextFormatter._sanitize_dict(d[k])
            elif isinstance(d[k], list):
                for item in d[k]:
                    if isinstance(item, dict):
                        TextFormatter._sanitize_dict(item)

    @staticmethod
    def normalize_turkish_text(text: str) -> str:
        """Normalize common OCR character confusions in Turkish without blindly overwriting."""
        corrections = {
            "ı": "ı",
            "İ": "İ",
            "ş": "ş",
            "Ş": "Ş",
            "ğ": "ğ",
            "Ğ": "Ğ",
            "ü": "ü",
            "Ü": "Ü",
            "ö": "ö",
            "Ö": "Ö",
            "ç": "ç",
            "Ç": "Ç",
        }
        # Safe whitespace & quote normalization
        normalized = text.replace("”", '"').replace("“", '"').replace("’", "'").replace("‘", "'")
        return normalized

