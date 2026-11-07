"""Modular sensitive data detector aggregating specialized category detectors."""

import re
from abc import ABC, abstractmethod
from typing import List, Optional
from PySide6.QtCore import QRect

from app.privacy.detection_result import DetectionResult, PrivacyAction, SensitiveType
from app.privacy.ocr import OCRResult
from app.privacy.patterns import (
    API_KEY_PATTERNS,
    CREDIT_CARD_CANDIDATE_REGEX,
    CREDIT_CARD_EXPIRY_REGEX,
    CREDIT_CARD_FORMATTED_REGEX,
    CVV_REGEX,
    EMAIL_REGEX,
    FILE_PATH_REGEX,
    IBAN_REGEX,
    IPV4_REGEX,
    IPV6_REGEX,
    JWT_REGEX,
    PHONE_REGEXES,
    SENSITIVE_URL_PARAM_REGEX,
    TCKN_REGEX,
    URL_REGEX,
    validate_iban,
    validate_luhn,
    validate_tckn,
)
from app.utils.logger import logger


class BaseDetector(ABC):
    """Abstract base detector for a sensitive data type."""

    @abstractmethod
    def detect(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        """Detect instances of sensitive data within OCR text tokens."""
        pass


class EmailDetector(BaseDetector):
    """Detects emails with high precision and OCR error tolerance."""

    def detect(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        detections: List[DetectionResult] = []

        for item in ocr_results:
            text = item.text.strip()
            # Clean OCR common spaces in email (e.g. user @ domain . com)
            clean_email_text = re.sub(r"\s*@\s*", "@", text)
            clean_email_text = re.sub(r"@([A-Za-z0-9.-]+)\s*\.\s*([A-Za-z]{2,})", r"@\1.\2", clean_email_text)

            match = EMAIL_REGEX.search(text) or EMAIL_REGEX.search(clean_email_text)
            if match:
                detections.append(
                    DetectionResult(
                        type=SensitiveType.EMAIL,
                        text=match.group(0),
                        confidence=0.98,
                        bounding_box=item.bounding_box,
                        reason="Email Address",
                        action=PrivacyAction.PIXELATE,
                    )
                )

        return detections


class IPDetector(BaseDetector):
    """Detects IPv4 and IPv6 addresses."""

    def detect(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        detections: List[DetectionResult] = []

        for item in ocr_results:
            text = item.text.strip()
            clean_text = re.sub(r"\s+", "", text)

            v4_match = IPV4_REGEX.search(text) or IPV4_REGEX.search(clean_text)
            if v4_match:
                ip = v4_match.group(0)
                is_private = ip.startswith(("10.", "192.168.", "172.16.", "127."))
                detections.append(
                    DetectionResult(
                        type=SensitiveType.IP_ADDRESS,
                        text=ip,
                        confidence=0.98,
                        bounding_box=item.bounding_box,
                        reason=f"IPv4 Address ({'Private/Local' if is_private else 'Public'})",
                        action=PrivacyAction.PIXELATE,
                    )
                )
                continue

            v6_match = IPV6_REGEX.search(text) or IPV6_REGEX.search(clean_text)
            if v6_match and len(v6_match.group(0)) > 6:
                detections.append(
                    DetectionResult(
                        type=SensitiveType.IP_ADDRESS,
                        text=v6_match.group(0),
                        confidence=0.92,
                        bounding_box=item.bounding_box,
                        reason="IPv6 Address",
                        action=PrivacyAction.PIXELATE,
                    )
                )

        return detections


class URLDetector(BaseDetector):
    """Detects URLs containing sensitive access credentials and query tokens."""

    def detect(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        detections: List[DetectionResult] = []

        for item in ocr_results:
            text = item.text.strip()
            url_match = URL_REGEX.search(text)
            if url_match:
                url_str = url_match.group(0)
                param_match = SENSITIVE_URL_PARAM_REGEX.search(url_str)
                if param_match:
                    detections.append(
                        DetectionResult(
                            type=SensitiveType.URL,
                            text=url_str,
                            confidence=0.95,
                            bounding_box=item.bounding_box,
                            reason=f"URL with sensitive query param '{param_match.group(1)}'",
                            action=PrivacyAction.PIXELATE,
                        )
                    )

        return detections


class APIKeyDetector(BaseDetector):
    """Detects API keys, bearer tokens, passwords, and universal credentials."""

    def detect(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        detections: List[DetectionResult] = []

        for item in ocr_results:
            text = item.text.strip()

            for pattern, reason_label in API_KEY_PATTERNS:
                m = pattern.search(text)
                if m:
                    detections.append(
                        DetectionResult(
                            type=SensitiveType.API_KEY,
                            text=m.group(0),
                            confidence=0.96,
                            bounding_box=item.bounding_box,
                            reason=reason_label,
                            action=PrivacyAction.BLACKOUT,
                        )
                    )
                    break

        return detections


class JWTDetector(BaseDetector):
    """Detects JSON Web Tokens (JWT)."""

    def detect(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        detections: List[DetectionResult] = []

        for item in ocr_results:
            text = item.text.strip()
            m = JWT_REGEX.search(text)
            if m:
                detections.append(
                    DetectionResult(
                        type=SensitiveType.JWT,
                        text=m.group(0),
                        confidence=0.99,
                        bounding_box=item.bounding_box,
                        reason="JSON Web Token (JWT)",
                        action=PrivacyAction.BLACKOUT,
                    )
                )

        return detections


class CreditCardDetector(BaseDetector):
    """Detects credit card numbers (formatted or Luhn-validated), Expiry dates, and CVVs."""

    def detect(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        detections: List[DetectionResult] = []

        for item in ocr_results:
            text = item.text.strip()
            if text.startswith("+"):
                continue

            # 1. Formatted 16-digit card number (e.g. 5555 5555 5555 5555 or 1111-1111-1111-1111)
            formatted_matches = CREDIT_CARD_FORMATTED_REGEX.findall(text)
            for f_match in formatted_matches:
                detections.append(
                    DetectionResult(
                        type=SensitiveType.CREDIT_CARD,
                        text=f_match,
                        confidence=0.98,
                        bounding_box=item.bounding_box,
                        reason="Credit Card Number (Formatted)",
                        action=PrivacyAction.BLACKOUT,
                    )
                )

            # 2. Luhn-validated card numbers
            candidates = CREDIT_CARD_CANDIDATE_REGEX.findall(text)
            for cand in candidates:
                cand_clean = re.sub(r"[\s-]", "", cand)
                if validate_luhn(cand_clean):
                    detections.append(
                        DetectionResult(
                            type=SensitiveType.CREDIT_CARD,
                            text=cand,
                            confidence=0.99,
                            bounding_box=item.bounding_box,
                            reason="Credit Card (Luhn Validated)",
                            action=PrivacyAction.BLACKOUT,
                        )
                    )

            # 3. Expiry Date (e.g. 13/13, 05/29)
            expiry_match = CREDIT_CARD_EXPIRY_REGEX.search(text)
            if expiry_match:
                detections.append(
                    DetectionResult(
                        type=SensitiveType.CREDIT_CARD,
                        text=expiry_match.group(0),
                        confidence=0.95,
                        bounding_box=item.bounding_box,
                        reason="Card Expiry Date",
                        action=PrivacyAction.BLACKOUT,
                    )
                )

            # 4. CVV / CVC Security Code (e.g. CVV: 111, CVV 123)
            cvv_match = CVV_REGEX.search(text)
            if cvv_match:
                detections.append(
                    DetectionResult(
                        type=SensitiveType.CREDIT_CARD,
                        text=cvv_match.group(0),
                        confidence=0.95,
                        bounding_box=item.bounding_box,
                        reason="Card CVV/CVC Code",
                        action=PrivacyAction.BLACKOUT,
                    )
                )

        return detections


class IBANDetector(BaseDetector):
    """Detects IBAN codes verified with ISO 7064 Mod-97 checksum."""

    def detect(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        detections: List[DetectionResult] = []

        for item in ocr_results:
            text = item.text.strip()
            candidates = IBAN_REGEX.findall(text)

            for cand in candidates:
                if validate_iban(cand):
                    detections.append(
                        DetectionResult(
                            type=SensitiveType.IBAN,
                            text=cand,
                            confidence=0.98,
                            bounding_box=item.bounding_box,
                            reason="IBAN (Mod-97 Checksum Validated)",
                            action=PrivacyAction.PIXELATE,
                        )
                    )

        return detections


class FilePathDetector(BaseDetector):
    """Detects local Windows / POSIX file system paths containing usernames."""

    def detect(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        detections: List[DetectionResult] = []

        for item in ocr_results:
            text = item.text.strip()
            match = FILE_PATH_REGEX.search(text)
            if match:
                path_str = match.group(0)
                detections.append(
                    DetectionResult(
                        type=SensitiveType.FILE_PATH,
                        text=path_str,
                        confidence=0.88,
                        bounding_box=item.bounding_box,
                        reason="Local File / Directory Path",
                        action=PrivacyAction.PIXELATE,
                    )
                )

        return detections


class PhoneDetector(BaseDetector):
    """Detects international and national phone numbers using phonenumbers and regular expressions."""

    def detect(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        detections: List[DetectionResult] = []

        for item in ocr_results:
            text = item.text.strip()

            # 1. Direct Regex Matcher
            for p_regex in PHONE_REGEXES:
                m = p_regex.search(text)
                if m:
                    match_str = m.group(0)
                    detections.append(
                        DetectionResult(
                            type=SensitiveType.PHONE,
                            text=match_str,
                            confidence=0.95,
                            bounding_box=item.bounding_box,
                            reason="Phone Number Pattern",
                            action=PrivacyAction.PIXELATE,
                        )
                    )
                    break

            # 2. Google phonenumbers library matcher
            try:
                import phonenumbers

                for match in phonenumbers.PhoneNumberMatcher(text, "TR"):
                    phone_str = match.raw_string
                    detections.append(
                        DetectionResult(
                            type=SensitiveType.PHONE,
                            text=phone_str,
                            confidence=0.98,
                            bounding_box=item.bounding_box,
                            reason=f"Phone Number ({match.number.country_code})",
                            action=PrivacyAction.PIXELATE,
                        )
                    )
            except Exception:
                pass

        return detections


class TCKNDetector(BaseDetector):
    """Detects validated Turkish Republic ID numbers (T.C. Kimlik No)."""

    def detect(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        detections: List[DetectionResult] = []
        for item in ocr_results:
            for candidate in TCKN_REGEX.findall(item.text.replace(" ", "")):
                if validate_tckn(candidate):
                    detections.append(
                        DetectionResult(
                            type=SensitiveType.TCKN,
                            text=candidate,
                            confidence=0.99,
                            bounding_box=item.bounding_box,
                            reason="T.C. Kimlik Numarası",
                            action=PrivacyAction.BLACKOUT,
                        )
                    )
        return detections


class SensitiveDataDetector:
    """Orchestrates all specialized sensitive data detectors in strict-to-loose priority order."""

    def __init__(self) -> None:
        self.detectors: List[BaseDetector] = [
            URLDetector(),         # Check URLs first
            EmailDetector(),       # Check Emails
            CreditCardDetector(),  # Strict Luhn check
            IBANDetector(),        # Strict Mod-97 check
            JWTDetector(),         # Base64 structure
            APIKeyDetector(),      # High-entropy / known token keys
            IPDetector(),          # IPv4/v6
            FilePathDetector(),    # File paths
            TCKNDetector(),         # Turkish Republic ID number
            PhoneDetector(),       # Phone detector last
        ]

    def scan(self, ocr_results: List[OCRResult]) -> List[DetectionResult]:
        # 1. Sort tokens geometrically: top-to-bottom, left-to-right
        sorted_tokens = sorted(
            ocr_results,
            key=lambda item: (item.bounding_box.top() // 15, item.bounding_box.left()),
        )

        extended_results: List[OCRResult] = list(sorted_tokens)

        # 2. Horizontal N-Gram Grouping (combines 2, 3, 4, 5 tokens on same horizontal row)
        n = len(sorted_tokens)
        for i in range(n):
            curr_box = sorted_tokens[i].bounding_box
            words_collected = [sorted_tokens[i].text]
            union_box = curr_box

            for j in range(i + 1, min(i + 6, n)):
                next_box = sorted_tokens[j].bounding_box
                # Check horizontal row alignment
                y_diff = abs(next_box.center().y() - curr_box.center().y())
                x_gap = next_box.left() - union_box.right()

                if y_diff <= 18 and -10 <= x_gap <= 80:
                    words_collected.append(sorted_tokens[j].text)
                    union_box = union_box.united(next_box)

                    joined_str = " ".join(words_collected)
                    extended_results.append(
                        OCRResult(
                            text=joined_str,
                            confidence=0.98,
                            bounding_box=union_box,
                        )
                    )
                    # Also joined without space (for keys, unbroken card numbers)
                    extended_results.append(
                        OCRResult(
                            text="".join(words_collected),
                            confidence=0.98,
                            bounding_box=union_box,
                        )
                    )
                else:
                    break

        # 3. Vertical Adjacent Line Pairing (for wrapped lines like email@g\nmail.com)
        for i in range(n):
            for j in range(i + 1, min(i + 4, n)):
                item_i = sorted_tokens[i]
                item_j = sorted_tokens[j]
                dy = item_j.bounding_box.top() - item_i.bounding_box.bottom()
                dx = abs(item_j.bounding_box.left() - item_i.bounding_box.left())
                if 0 <= dy <= 30 and dx <= 120:
                    combined_box = item_i.bounding_box.united(item_j.bounding_box)
                    extended_results.append(
                        OCRResult(
                            text=f"{item_i.text}{item_j.text}",
                            confidence=min(item_i.confidence, item_j.confidence),
                            bounding_box=combined_box,
                        )
                    )

        # 4. Form Field Label-Value Proximity Detection
        form_label_keywords = [
            "kart numarası", "card number", "kart no", "pan", "cvv", "cvc",
            "son kullanma", "expiry", "exp", "güvenlik kodu", "security code",
            "şifre", "password", "parola", "tckn", "kimlik no"
        ]

        for i, item_i in enumerate(sorted_tokens):
            lbl_lower = item_i.text.lower()
            if any(kw in lbl_lower for kw in form_label_keywords):
                # Search for input value token below or to the right of label
                for j, item_j in enumerate(sorted_tokens):
                    if i == j:
                        continue
                    # Value directly below label (e.g. input field box)
                    v_gap = item_j.bounding_box.top() - item_i.bounding_box.bottom()
                    h_diff = abs(item_j.bounding_box.left() - item_i.bounding_box.left())
                    # Value directly to the right
                    r_gap = item_j.bounding_box.left() - item_i.bounding_box.right()
                    r_ydiff = abs(item_j.bounding_box.center().y() - item_i.bounding_box.center().y())

                    is_below = 0 <= v_gap <= 65 and h_diff <= 140
                    is_right = 0 <= r_gap <= 100 and r_ydiff <= 18

                    if is_below or is_right:
                        val_text = item_j.text.strip()
                        if val_text and not any(kw in val_text.lower() for kw in form_label_keywords):
                            extended_results.append(
                                OCRResult(
                                    text=f"key={val_text}",
                                    confidence=0.98,
                                    bounding_box=item_j.bounding_box,
                                )
                            )

        all_detections: List[DetectionResult] = []

        for detector in self.detectors:
            try:
                results = detector.detect(extended_results)
                for res in results:
                    if not self._is_box_duplicate(res, all_detections):
                        all_detections.append(res)
            except Exception as exc:
                logger.error("Detector %s raised error: %s", detector.__class__.__name__, exc)

        logger.info(
            "Sensitive data scan complete. Detected %d potential items (Zero raw sensitive data logged).",
            len(all_detections),
        )
        return all_detections

    def _is_box_duplicate(self, res: DetectionResult, existing: List[DetectionResult]) -> bool:
        for ex in existing:
            # Same text detected in intersecting area
            if res.text.strip() == ex.text.strip() and not res.bounding_box.intersected(ex.bounding_box).isEmpty():
                return True
            # Exact box
            if res.bounding_box == ex.bounding_box:
                return True
            # Sub-box or high overlap (>60% of smaller box)
            intersection = res.bounding_box.intersected(ex.bounding_box)
            if not intersection.isEmpty():
                i_area = intersection.width() * intersection.height()
                res_area = res.bounding_box.width() * res.bounding_box.height()
                ex_area = ex.bounding_box.width() * ex.bounding_box.height()
                min_area = min(res_area, ex_area)
                if min_area > 0 and (i_area / min_area) > 0.65:
                    return True
        return False

