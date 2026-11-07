"""Immutable dataclass model and payload parser for detected QR codes."""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from PySide6.QtCore import QRect


class QRDataType(Enum):
    """Supported semantic classifications for QR code payloads."""
    URL = "url"
    TEXT = "text"
    WIFI = "wifi"
    EMAIL = "email"
    PHONE = "phone"
    VCARD = "vcard"
    CALENDAR = "calendar"
    OTP = "otp"
    SMS = "sms"
    GEO = "geo"
    UNKNOWN = "unknown"


# Safe allowed web schemes for opening directly in browser
ALLOWED_URL_SCHEMES = {"http", "https"}

# Potentially malicious / dangerous executable or internal schemes
DISALLOWED_URL_SCHEMES = {
    "javascript",
    "data",
    "file",
    "vbscript",
    "cmd",
    "powershell",
    "ms-settings",
    "ms-windows-store",
    "shell",
    "about",
    "chrome",
    "edge",
    "opera",
    "brave",
    "view-source",
    "ws",
    "wss",
    "jar",
}


def sanitize_url(raw_text: str) -> tuple[bool, Optional[str]]:
    """
    Validate and normalize URL safely.
    Returns (is_safe_url, normalized_url).
    Rejects dangerous/executable schemes (e.g. javascript:, data:, file:).
    """
    text = raw_text.strip()
    if not text:
        return False, None

    # Check for scheme prefix
    lower_text = text.lower()

    for dangerous_scheme in DISALLOWED_URL_SCHEMES:
        if lower_text.startswith(f"{dangerous_scheme}:"):
            return False, None

    # Normalize URLs without scheme (e.g. "www.example.com" or "example.com/login")
    test_url = text
    if not (lower_text.startswith("http://") or lower_text.startswith("https://")):
        # Check if it looks like a domain name with TLD
        domain_pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(?::\d+)?(?:/.*)?$"
        if re.match(domain_pattern, text):
            test_url = f"https://{text}"
        else:
            return False, None

    try:
        parsed = urlparse(test_url)
        if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
            return False, None

        if not parsed.netloc or "." not in parsed.netloc:
            # Must have a valid domain / host with at least one dot or localhost
            if parsed.netloc.lower() not in ("localhost", "127.0.0.1"):
                return False, None

        return True, test_url
    except Exception:
        return False, None


def parse_qr_payload(raw_text: str) -> tuple[QRDataType, bool, Optional[str], Dict[str, Any]]:
    """
    Classify raw QR code string into semantic types and extract structured details.
    Returns (data_type, is_url, normalized_url, parsed_details).
    """
    text = raw_text.strip()
    details: Dict[str, Any] = {}

    if not text:
        return QRDataType.UNKNOWN, False, None, details

    # 1. Check for Wi-Fi configuration (WIFI:T:WPA;S:MyNet;P:pass;H:false;;)
    if text.upper().startswith("WIFI:"):
        details = _parse_wifi_payload(text)
        return QRDataType.WIFI, False, None, details

    # 2. Check for OTP / 2FA (otpauth://totp/...?secret=...)
    if text.lower().startswith("otpauth://"):
        details = _parse_otp_payload(text)
        return QRDataType.OTP, False, None, details

    # 3. Check for Email (mailto:... or MATMSG:...)
    if text.lower().startswith("mailto:") or text.upper().startswith("MATMSG:"):
        details = _parse_email_payload(text)
        return QRDataType.EMAIL, False, None, details

    # 4. Check for Phone (tel:... or TEL:...)
    if text.lower().startswith("tel:"):
        phone_num = text[4:].strip()
        return QRDataType.PHONE, False, None, {"phone": phone_num}

    # 5. Check for SMS (sms:... or SMSTO:...)
    if text.lower().startswith("sms:") or text.upper().startswith("SMSTO:"):
        details = _parse_sms_payload(text)
        return QRDataType.SMS, False, None, details

    # 6. Check for vCard contact (BEGIN:VCARD ... END:VCARD)
    if "BEGIN:VCARD" in text.upper():
        details = _parse_vcard_payload(text)
        return QRDataType.VCARD, False, None, details

    # 7. Check for Calendar Event (BEGIN:VEVENT ... END:VEVENT)
    if "BEGIN:VEVENT" in text.upper() or "BEGIN:VCALENDAR" in text.upper():
        details = _parse_calendar_payload(text)
        return QRDataType.CALENDAR, False, None, details

    # 8. Check for Geolocation (geo:lat,lon or geo:...)
    if text.lower().startswith("geo:"):
        return QRDataType.GEO, False, None, {"geo": text[4:].strip()}

    # 9. Check for HTTP / HTTPS URL
    is_safe, norm_url = sanitize_url(text)
    if is_safe and norm_url:
        return QRDataType.URL, True, norm_url, {"url": norm_url}

    # Default to plain text
    return QRDataType.TEXT, False, None, {"text": text}


def _parse_wifi_payload(text: str) -> Dict[str, Any]:
    """Parse WIFI:T:WPA;S:MyNetwork;P:MyPassword;H:false;;"""
    data = text[5:]
    details: Dict[str, Any] = {
        "auth_type": "nopass",
        "ssid": "",
        "hidden": False,
        "has_password": False,
    }

    parts = data.split(";")
    for part in parts:
        if not part:
            continue
        if part.startswith("T:") or part.startswith("t:"):
            details["auth_type"] = part[2:]
        elif part.startswith("S:") or part.startswith("s:"):
            details["ssid"] = part[2:]
        elif part.startswith("P:") or part.startswith("p:"):
            details["has_password"] = bool(part[2:])
            # Store password masked for security
            details["password"] = part[2:]
        elif part.startswith("H:") or part.startswith("h:"):
            details["hidden"] = part[2:].lower() in ("true", "1")

    return details


def _parse_otp_payload(text: str) -> Dict[str, Any]:
    """Parse otpauth://totp/Example:alice@google.com?secret=JBSWY3DPEHPK3PXP&issuer=Example"""
    details: Dict[str, Any] = {"raw_uri": text}
    try:
        parsed = urlparse(text)
        details["otp_type"] = parsed.netloc.upper()  # TOTP or HOTP
        label = parsed.path.strip("/")
        if ":" in label:
            issuer, account = label.split(":", 1)
            details["issuer"] = issuer.strip()
            details["account"] = account.strip()
        else:
            details["account"] = label
    except Exception:
        pass
    return details


def _parse_email_payload(text: str) -> Dict[str, Any]:
    """Parse mailto:user@example.com?subject=Hi or MATMSG:TO:user@example.com;SUB:Hi;BODY:Hello;;"""
    details: Dict[str, Any] = {}
    if text.lower().startswith("mailto:"):
        mailto_body = text[7:]
        if "?" in mailto_body:
            email, query = mailto_body.split("?", 1)
            details["email"] = email
            for q in query.split("&"):
                if "=" in q:
                    k, v = q.split("=", 1)
                    if k.lower() == "subject":
                        details["subject"] = v
                    elif k.lower() == "body":
                        details["body"] = v
        else:
            details["email"] = mailto_body
    elif text.upper().startswith("MATMSG:"):
        body = text[7:]
        for part in body.split(";"):
            if part.startswith("TO:"):
                details["email"] = part[3:]
            elif part.startswith("SUB:"):
                details["subject"] = part[4:]
            elif part.startswith("BODY:"):
                details["body"] = part[5:]
    return details


def _parse_sms_payload(text: str) -> Dict[str, Any]:
    """Parse sms:+123456789?body=Hello or SMSTO:+123456789:Hello"""
    details: Dict[str, Any] = {}
    if text.lower().startswith("sms:"):
        body = text[4:]
        if "?" in body:
            phone, q = body.split("?", 1)
            details["phone"] = phone
            if "body=" in q.lower():
                details["message"] = q.split("=", 1)[1]
        else:
            details["phone"] = body
    elif text.upper().startswith("SMSTO:"):
        body = text[6:]
        if ":" in body:
            phone, msg = body.split(":", 1)
            details["phone"] = phone
            details["message"] = msg
        else:
            details["phone"] = body
    return details


def _parse_vcard_payload(text: str) -> Dict[str, Any]:
    """Parse simple vCard fields."""
    details: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("FN:") or line.startswith("fn:"):
            details["name"] = line[3:].strip()
        elif (line.startswith("TEL:") or line.startswith("tel:")) and "phone" not in details:
            details["phone"] = line[4:].strip()
        elif (line.startswith("EMAIL:") or line.startswith("email:")) and "email" not in details:
            details["email"] = line[6:].strip()
        elif line.startswith("ORG:") or line.startswith("org:"):
            details["org"] = line[4:].strip()
        elif line.startswith("TITLE:") or line.startswith("title:"):
            details["title"] = line[6:].strip()
    return details


def _parse_calendar_payload(text: str) -> Dict[str, Any]:
    """Parse calendar event fields."""
    details: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("SUMMARY:"):
            details["summary"] = line[8:].strip()
        elif line.startswith("LOCATION:"):
            details["location"] = line[9:].strip()
        elif line.startswith("DTSTART:"):
            details["dtstart"] = line[8:].strip()
        elif line.startswith("DTEND:"):
            details["dtend"] = line[6:].strip()
    return details


@dataclass(frozen=True)
class QRResult:
    """Immutable representation of a detected and decoded QR code."""
    data: str
    type: QRDataType
    bounding_box: QRect
    is_url: bool
    normalized_url: Optional[str] = None
    confidence: float = 1.0
    index: int = 0
    parsed_details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        data: str,
        bounding_box: QRect,
        confidence: float = 1.0,
        index: int = 0,
    ) -> "QRResult":
        """Factory method that automatically parses payload and validates URL."""
        data_type, is_url, norm_url, details = parse_qr_payload(data)
        return cls(
            data=data,
            type=data_type,
            bounding_box=bounding_box,
            is_url=is_url,
            normalized_url=norm_url,
            confidence=confidence,
            index=index,
            parsed_details=details,
        )

    def get_display_title(self) -> str:
        """User-friendly title for the QR result card."""
        titles = {
            QRDataType.URL: "Web Bağlantısı",
            QRDataType.WIFI: "Wi-Fi Yapılandırması",
            QRDataType.EMAIL: "E-posta",
            QRDataType.PHONE: "Telefon Numarası",
            QRDataType.VCARD: "Kişi Kartı (vCard)",
            QRDataType.CALENDAR: "Takvim Etkinliği",
            QRDataType.OTP: "İki Adımlı Doğrulama (2FA / OTP)",
            QRDataType.SMS: "Kısa Mesaj (SMS)",
            QRDataType.GEO: "Coğrafi Konum",
            QRDataType.TEXT: "Metin",
            QRDataType.UNKNOWN: "QR Kod",
        }
        return titles.get(self.type, "QR Kod")

    def get_display_preview(self, max_length: int = 120) -> str:
        """Formatted preview string for display in the notification panel."""
        if self.type == QRDataType.WIFI:
            ssid = self.parsed_details.get("ssid", "Bilinmeyen Ağ")
            auth = self.parsed_details.get("auth_type", "WPA")
            return f"Ağ Adı (SSID): {ssid}  •  Güvenlik: {auth}"

        if self.type == QRDataType.URL and self.normalized_url:
            return self.normalized_url

        if self.type == QRDataType.VCARD:
            name = self.parsed_details.get("name", "")
            phone = self.parsed_details.get("phone", "")
            email = self.parsed_details.get("email", "")
            parts = [p for p in [name, phone, email] if p]
            return " • ".join(parts) if parts else self.data[:max_length]

        if self.type == QRDataType.EMAIL:
            email = self.parsed_details.get("email", self.data)
            subj = self.parsed_details.get("subject", "")
            return f"{email} (Konu: {subj})" if subj else email

        if self.type == QRDataType.PHONE:
            return self.parsed_details.get("phone", self.data)

        if self.type == QRDataType.OTP:
            account = self.parsed_details.get("account", "OTP Auth")
            issuer = self.parsed_details.get("issuer", "")
            return f"{issuer} ({account})" if issuer else account

        # Plain text or fallback
        preview = self.data.replace("\r", " ").replace("\n", " ").strip()
        if len(preview) > max_length:
            return preview[:max_length] + "..."
        return preview

