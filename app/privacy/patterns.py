"""Regular expression patterns and checksum validators for sensitive data detection."""

import re
from typing import List, Tuple

# Email Regex (Handles standard format and OCR spaced dots/ats)
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+(?:\s*@\s*|\s*\[at\]\s*)[A-Za-z0-9.-]+(?:\s*\.\s*|\s*\[dot\]\s*)[A-Za-z]{2,}\b",
    re.IGNORECASE,
)

# Phone Numbers (International +, 7-16 digit sequences, local formats, Turkish 05xx)
PHONE_REGEXES = [
    # International with + (e.g. +11111115151, +881111111111, +90 555 123 45 67)
    re.compile(r"\+\d{1,4}(?:[ -]?\d{2,5}){2,4}\b|\+\d{7,16}\b"),
    # Standard 10-11 digit local mobile (e.g. 0555 123 45 67, 555 123 4567)
    re.compile(r"\b0?5\d{2}[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}\b"),
    # 7-digit local phone (e.g. 555 55 11, 555-5511)
    re.compile(r"\b\d{3}[ -]?\d{2}[ -]?\d{2}\b"),
    # North American format (e.g. 1-800-555-0199, (555) 123-4567)
    re.compile(r"\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b"),
]

# Turkish Republic ID number (T.C. Kimlik No): exactly 11 digits and validated below.
TCKN_REGEX = re.compile(r"\b[1-9]\d{10}\b")

# IPv4 & IPv6
IPV4_REGEX = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
)
IPV6_REGEX = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
    r"|\b(?:[0-9a-fA-F]{1,4}:){1,7}:"
    r"|\b:(?::[0-9a-fA-F]{1,4}){1,7}\b"
)

# URL
URL_REGEX = re.compile(
    r"\b(?:https?://|www\.)[A-Za-z0-9.-]+(?::\d+)?(?:/[^\s]*)?\b",
    re.IGNORECASE,
)

# Sensitive Query Parameters in URLs
SENSITIVE_URL_PARAM_REGEX = re.compile(
    r"[?&]([a-z0-9_-]*(?:token|api_key|apikey|key|secret|password|passwd|auth|access_token|client_secret)[a-z0-9_-]*)=([^&\s]+)",
    re.IGNORECASE,
)

# JWT (JSON Web Token: header.payload.signature)
JWT_REGEX = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{15,}\.[A-Za-z0-9._-]{10,}\b"
)

# Universal API Keys, Tokens, Passwords, Secrets, and Credential Keywords
KEY_VALUE_CREDENTIAL_REGEX = re.compile(
    r"\b([a-zA-Z0-9_-]*(?:key|token|secret|pass|passwd|password|auth|jwt|cred|pwd|pin|sign|priv|access|bearer|cert|hash|signature)[a-zA-Z0-9_-]*)\s*[:=F]\s*[\"']?([^\s\"',;]{3,})[\"']?",
    re.IGNORECASE,
)

# Specific Provider Tokens & Patterns
API_KEY_PATTERNS = [
    # OpenAI API Keys (sk-..., sk-proj-...)
    (re.compile(r"\bsk-[A-Za-z0-9_-]{15,}\b"), "OpenAI API Key"),
    # AWS Access Key ID
    (re.compile(r"\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"), "AWS Access Key ID"),
    # GitHub Personal Access Token
    (re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{30,}\b"), "GitHub Token"),
    # Slack Token
    (re.compile(r"\bxox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*\b"), "Slack Token"),
    # Stripe API Key
    (re.compile(r"\b(?:sk|pk)_(?:live|test)_[0-9a-zA-Z]{20,}\b"), "Stripe Key"),
    # Google API Key
    (re.compile(r"\bAIza[0-9A-Za-z\\-_]{35}\b"), "Google API Key"),
    # Universal Key-Value Credential Pattern
    (KEY_VALUE_CREDENTIAL_REGEX, "API Key / Secret Credential"),
]

# Formatted credit-card candidates. OCR engines may insert arbitrary spaces or
# hyphens between groups, so validation below remains mandatory.
CREDIT_CARD_FORMATTED_REGEX = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
CREDIT_CARD_CANDIDATE_REGEX = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")

# Credit Card Expiration Date (MM/YY, MM/YYYY, e.g. 13/13, 05/29)
CREDIT_CARD_EXPIRY_REGEX = re.compile(r"\b\d{1,2}\/\d{2,4}\b")

# CVV / CVC Security Code (e.g. CVV: 111, CVV (3 hane) 111, CVC 123)
CVV_REGEX = re.compile(
    r"\b(?:cvv|cvc|cvv2|cvc2|cid|güvenlik|guvenlik)\b[^\d]{0,15}(\d{3,4})\b",
    re.IGNORECASE,
)

# IBAN Candidate (Flexible spacing between 2-8 char chunks)
IBAN_REGEX = re.compile(
    r"\b[A-Z]{2}\d{2}(?:[ \t\-]?[A-Z0-9]{2,8}){2,8}\b|\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"
)

# File Paths (Windows C:\... and POSIX /home/... /Users/...)
FILE_PATH_REGEX = re.compile(
    r"(?:\b[a-zA-Z]:\\[^/:*?\"<>|\r\n]+|/(?:home|Users|usr|var|etc|opt)/[^\s\"':;]+)"
)


def validate_luhn(card_number_str: str) -> bool:
    """Validate a credit card candidate string using the Luhn Algorithm (Mod-10)."""
    digits_only = re.sub(r"\D", "", card_number_str)
    if not (13 <= len(digits_only) <= 19):
        return False

    checksum = 0
    reverse_digits = digits_only[::-1]

    for idx, char in enumerate(reverse_digits):
        n = int(char)
        if idx % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        checksum += n

    return (checksum % 10) == 0


def validate_iban(iban_str: str) -> bool:
    """Validate an IBAN string using the ISO 7064 Mod-97 checksum algorithm."""
    clean_iban = re.sub(r"[\s-]", "", iban_str).upper()

    if not (15 <= len(clean_iban) <= 34):
        return False

    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$", clean_iban):
        return False

    # Move first 4 chars to end: CountryCode(2) + CheckDigits(2)
    rearranged = clean_iban[4:] + clean_iban[:4]

    # Convert letters to digits: A=10, B=11, ..., Z=35
    num_str = ""
    for ch in rearranged:
        if ch.isdigit():
            num_str += ch
        elif "A" <= ch <= "Z":
            num_str += str(ord(ch) - ord("A") + 10)
        else:
            return False

    try:
        return (int(num_str) % 97) == 1
    except ValueError:
        return False


def validate_tckn(value: str) -> bool:
    """Validate a Turkish Republic ID number using the official checksum rules."""
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11 or digits[0] == "0":
        return False

    nums = [int(d) for d in digits]
    odd_sum = nums[0] + nums[2] + nums[4] + nums[6] + nums[8]
    even_sum = nums[1] + nums[3] + nums[5] + nums[7]
    digit_10 = ((odd_sum * 7) - even_sum) % 10
    digit_11 = sum(nums[:10]) % 10
    return nums[9] == digit_10 and nums[10] == digit_11

