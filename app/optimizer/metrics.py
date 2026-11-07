"""Quality metrics (SSIM, PSNR, Pixel Identity) using NumPy for local visual assessment."""

import math
import numpy as np
from PIL import Image


def are_pixels_identical(img1: Image.Image, img2: Image.Image) -> bool:
    """Performs exact pixel-by-pixel binary equality verification for lossless testing."""
    if img1.size != img2.size:
        return False

    i1 = img1.convert("RGBA")
    i2 = img2.convert("RGBA")
    arr1 = np.array(i1)
    arr2 = np.array(i2)
    return bool(np.array_equal(arr1, arr2))


def compute_psnr(img1: Image.Image, img2: Image.Image) -> float:
    """Computes Peak Signal-to-Noise Ratio (PSNR) in dB between two images."""
    if img1.size != img2.size:
        img2 = img2.resize(img1.size, Image.Resampling.BICUBIC)

    i1 = img1.convert("RGB")
    i2 = img2.convert("RGB")
    arr1 = np.array(i1, dtype=np.float64)
    arr2 = np.array(i2, dtype=np.float64)

    mse = np.mean((arr1 - arr2) ** 2)
    if mse == 0:
        return 100.0  # Perfect identity
    max_pixel = 255.0
    return float(20 * math.log10(max_pixel / math.sqrt(mse)))


def compute_ssim(img1: Image.Image, img2: Image.Image) -> float:
    """Computes Structural Similarity Index (SSIM) between 0.0 and 1.0."""
    if img1.size != img2.size:
        img2 = img2.resize(img1.size, Image.Resampling.BICUBIC)

    i1 = img1.convert("L")
    i2 = img2.convert("L")
    arr1 = np.array(i1, dtype=np.float64)
    arr2 = np.array(i2, dtype=np.float64)

    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2

    mean1 = np.mean(arr1)
    mean2 = np.mean(arr2)
    var1 = np.var(arr1)
    var2 = np.var(arr2)
    covar = np.mean((arr1 - mean1) * (arr2 - mean2))

    numerator = (2 * mean1 * mean2 + c1) * (2 * covar + c2)
    denominator = (mean1 ** 2 + mean2 ** 2 + c1) * (var1 + var2 + c2)

    ssim = float(numerator / max(1e-6, denominator))
    return max(0.0, min(1.0, ssim))


def classify_quality(ssim: float, psnr: float, is_lossless: bool = False) -> str:
    """Returns a user-friendly quality rating string."""
    if is_lossless or ssim >= 0.999 or psnr >= 50.0:
        return "Mükemmel (Kayıpsız / Excellent)"
    elif ssim >= 0.96 or psnr >= 40.0:
        return "Çok İyi (High Fidelity)"
    elif ssim >= 0.90 or psnr >= 32.0:
        return "İyi (Good / Balanced)"
    elif ssim >= 0.80:
        return "Hafif Kalite Kaybı (Noticeable)"
    else:
        return "Belirgin Kalite Kaybı (Strong Loss)"

