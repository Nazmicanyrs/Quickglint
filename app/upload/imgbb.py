"""ImgBB API v1 implementation with strict HTTPS, zero hardcoded keys, expiration, and sanitized filenames."""

import base64
import io
import json
import os
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Callable, List, Optional, Tuple, Union

from PIL import Image

from app.upload.models import IMGBB_MAX_IMAGE_SIZE, IMGBB_UPLOAD_ENDPOINT, UPLOAD_TIMEOUT, UploadRequest, UploadResult
from app.upload.provider import UploadProvider
from app.utils.logger import logger


class ImgBBProvider(UploadProvider):
    """Official ImgBB API v1 provider."""

    @property
    def name(self) -> str:
        return "ImgBB"

    @property
    def max_size_bytes(self) -> int:
        return IMGBB_MAX_IMAGE_SIZE

    @property
    def supported_formats(self) -> List[str]:
        return ["PNG", "JPEG", "JPG", "WEBP", "GIF", "BMP", "TIFF"]

    def upload(
        self,
        image_bytes_or_request: Union[bytes, UploadRequest],
        file_name: str = "screenshot.png",
        api_key: str = "",
        expiration: Optional[int] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> UploadResult:
        """Uploads image binary to ImgBB and returns structured URLs."""

        # 1. Normalize UploadRequest or args
        if isinstance(image_bytes_or_request, UploadRequest):
            req_obj = image_bytes_or_request
            image_bytes = req_obj.image_bytes
            raw_file_name = req_obj.file_name
            clean_key = (req_obj.api_key or "").strip()
            exp_val = req_obj.expiration
        else:
            image_bytes = image_bytes_or_request
            raw_file_name = file_name
            clean_key = (api_key or "").strip()
            exp_val = expiration

        # 2. Check API Key presence
        if not clean_key:
            return UploadResult(
                success=False,
                provider_name=self.name,
                error_msg="ImgBB API key is not configured. Lütfen Ayarlar -> Yükle & Paylaş bölümünden API anahtarınızı girin.",
            )

        # 3. Image Pre-Validation (Decode check, size check, non-zero bytes check)
        if not image_bytes or len(image_bytes) == 0:
            return UploadResult(
                success=False,
                provider_name=self.name,
                error_msg="Invalid image. The selected image cannot be uploaded because it is 0 bytes.",
            )

        if len(image_bytes) > self.max_size_bytes:
            mb = len(image_bytes) / (1024 * 1024)
            return UploadResult(
                success=False,
                provider_name=self.name,
                error_msg=f"Image is too large for ImgBB ({mb:.1f} MB). ImgBB maximum limit is 32 MB.",
            )

        try:
            with Image.open(io.BytesIO(image_bytes)) as test_img:
                w, h = test_img.size
                if w <= 0 or h <= 0:
                    raise ValueError("Image dimensions must be positive.")
        except Exception as exc:
            logger.error("Image decode validation failed: %s", exc)
            return UploadResult(
                success=False,
                provider_name=self.name,
                error_msg="Invalid image. The selected image cannot be uploaded because it could not be decoded.",
            )

        # 4. Sanitize Display Filename (Strip local absolute paths, usernames, passwords, Vault paths/IDs)
        clean_name = self.sanitize_filename(raw_file_name)

        t0 = time.time()
        max_retries = 3
        last_error = ""

        # 5. Build Multipart Request Data
        # (expiration handled below; the key is sent in the request body)
        for attempt in range(1, max_retries + 1):
            if is_cancelled and is_cancelled():
                return UploadResult(success=False, provider_name=self.name, error_msg="Upload cancelled by user.")

            try:
                b64_image = base64.b64encode(image_bytes).decode("ascii")

                query_params = {}
                if exp_val is not None and isinstance(exp_val, int) and 60 <= exp_val <= 15552000:
                    query_params["expiration"] = str(exp_val)

                # API key is sent in the multipart body (never in the URL) so it
                # cannot leak into proxy/server/exception logs.
                endpoint_url = IMGBB_UPLOAD_ENDPOINT
                if query_params:
                    endpoint_url = f"{IMGBB_UPLOAD_ENDPOINT}?{urllib.parse.urlencode(query_params)}"

                # Match official ImgBB curl specification: multipart/form-data with image=base64
                boundary = f"----QuickglintFormBoundary{uuid.uuid4().hex[:16]}"
                lines = [
                    f"--{boundary}".encode("utf-8"),
                    b'Content-Disposition: form-data; name="key"',
                    b"",
                    clean_key.encode("utf-8"),
                    f"--{boundary}".encode("utf-8"),
                    b'Content-Disposition: form-data; name="image"',
                    b"",
                    b64_image.encode("ascii"),
                ]
                if clean_name:
                    lines.extend([
                        f"--{boundary}".encode("utf-8"),
                        b'Content-Disposition: form-data; name="name"',
                        b"",
                        clean_name.encode("utf-8"),
                    ])
                lines.extend([
                    f"--{boundary}--".encode("utf-8"),
                    b"",
                ])
                body_bytes = b"\r\n".join(lines)

                ssl_context = ssl.create_default_context()
                try:
                    import certifi
                    ssl_context.load_verify_locations(cafile=certifi.where())
                except Exception:
                    pass

                req = urllib.request.Request(
                    endpoint_url,
                    data=body_bytes,
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                        "Accept": "application/json",
                    },
                    method="POST",
                )

                with urllib.request.urlopen(req, context=ssl_context, timeout=UPLOAD_TIMEOUT) as resp:
                    status_code = resp.status
                    resp_data = resp.read().decode("utf-8")

                    try:
                        parsed = json.loads(resp_data)
                    except Exception:
                        return UploadResult(
                            success=False,
                            provider_name=self.name,
                            status_code=status_code,
                            error_msg="Malformed API response received from ImgBB.",
                        )

                    # Validate API JSON structure
                    is_api_success = (parsed.get("success") is True) and (parsed.get("status") == 200)
                    if is_api_success and "data" in parsed:
                        data = parsed["data"]
                        direct_url = data.get("url") or (data.get("image", {}).get("url", ""))
                        share_url = data.get("url_viewer") or direct_url
                        delete_url = data.get("delete_url", "")
                        width = int(data.get("width", 0))
                        height = int(data.get("height", 0))
                        elapsed = time.time() - t0

                        if not direct_url and not share_url:
                            return UploadResult(
                                success=False,
                                provider_name=self.name,
                                status_code=status_code,
                                error_msg="Upload completed but the provider did not return a usable image URL.",
                            )

                        logger.info("ImgBB upload successful: %s (direct: %s)", share_url, direct_url)
                        return UploadResult(
                            success=True,
                            direct_url=direct_url,
                            share_url=share_url,
                            delete_url=delete_url,
                            provider_name=self.name,
                            status_code=status_code,
                            file_name=clean_name,
                            size_bytes=len(image_bytes),
                            width=width,
                            height=height,
                            elapsed_sec=elapsed,
                        )
                    else:
                        err_detail = parsed.get("error", {}).get("message", "Bilinmeyen API yanıtı.")
                        return UploadResult(
                            success=False,
                            provider_name=self.name,
                            status_code=status_code,
                            error_msg=f"ImgBB Hatası: {err_detail}",
                        )

            except urllib.error.HTTPError as http_err:
                code = http_err.code
                err_body = ""
                try:
                    err_body = http_err.read().decode("utf-8", errors="ignore")
                    err_json = json.loads(err_body)
                    msg = err_json.get("error", {}).get("message", "")
                except Exception:
                    msg = ""

                if code in (400, 401, 403):
                    detail = msg or "API key is invalid or unauthorized."
                    return UploadResult(
                        success=False,
                        provider_name=self.name,
                        status_code=code,
                        error_msg=f"ImgBB Authorization Failure (HTTP {code}): {detail}",
                    )
                elif code == 429:
                    return UploadResult(
                        success=False,
                        provider_name=self.name,
                        status_code=code,
                        error_msg="ImgBB rate limit reached. Lütfen biraz bekleyin.",
                    )
                else:
                    last_error = f"Server Error (HTTP {code}): {msg or http_err.reason}"
                    if attempt < max_retries:
                        time.sleep(1.0 * attempt)
                        continue

            except urllib.error.URLError as url_err:
                last_error = f"Network Connection Error: {url_err.reason}"
                if attempt < max_retries:
                    time.sleep(1.0 * attempt)
                    continue
            except TimeoutError:
                last_error = "Network request timed out."
                if attempt < max_retries:
                    time.sleep(1.0 * attempt)
                    continue
            except Exception as exc:
                last_error = f"Unexpected Error: {exc}"
                break

        return UploadResult(success=False, provider_name=self.name, error_msg=last_error)

    def validate_api_key(self, api_key: str) -> Tuple[bool, str]:
        """Validates API key by testing with a 1x1 1-byte transparent test probe to ImgBB."""
        clean_key = (api_key or "").strip()
        if not clean_key:
            return False, "API key is not configured."

        # Minimal 1x1 transparent GIF from official ImgBB documentation example
        tiny_gif = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

        res = self.upload(tiny_gif, file_name="Quickglint_key_test.gif", api_key=clean_key)
        if res.success:
            return True, "✅ ImgBB connection successful and API key is valid."
        else:
            return False, f"❌ Connection failed: {res.error_msg}"

    @classmethod
    def sanitize_filename(cls, raw_filename: str) -> str:
        """Sanitizes filename by stripping local absolute paths, user directories, and Vault IDs."""
        if not raw_filename:
            return "Screenshot.png"

        # Extract basename
        name = Path(raw_filename).name

        # Replace invalid path chars
        name = "".join(c for c in name if c.isalnum() or c in ("-", "_", "."))
        if not name or name.startswith("."):
            name = "Screenshot.png"

        # Enforce max length
        if len(name) > 60:
            ext = Path(name).suffix or ".png"
            stem = Path(name).stem[:50]
            name = f"{stem}{ext}"

        return name

    @classmethod
    def _build_multipart_body(
        cls,
        fields: dict,
        file_field: str,
        file_name: str,
        file_bytes: bytes,
        boundary: str,
    ) -> bytes:
        """Constructs multipart/form-data payload without leaking credentials to URL parameters."""
        lines = []

        for name, value in fields.items():
            lines.append(f"--{boundary}".encode("utf-8"))
            lines.append(f'Content-Disposition: form-data; name="{name}"'.encode("utf-8"))
            lines.append(b"")
            lines.append(str(value).encode("utf-8"))

        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"'.encode("utf-8"))
        lines.append(b"Content-Type: application/octet-stream")
        lines.append(b"")
        lines.append(file_bytes)
        lines.append(f"--{boundary}--".encode("utf-8"))
        lines.append(b"")

        return b"\r\n".join(lines)

