"""Metadata cleaning report generator for structured markdown and plain text exports."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from app.metacleaner.models import CleanResult, MetadataCategory, MetadataRiskLevel, MetadataScanReport


class MetadataReportGenerator:
    """Produces detailed textual and markdown reports of metadata scrubbing operations."""

    @classmethod
    def generate_markdown(cls, result: CleanResult) -> str:
        """Generate a GitHub-flavored markdown report of cleaning results."""
        lines = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines.append("# 🛡️ Quickglint — Metadata Temizleme Raporu")
        lines.append("")
        lines.append(f"**Tarih:** `{now_str}`  ")
        if result.input_path:
            lines.append(f"**Giriş Dosyası:** `{result.input_path.name}`  ")
        if result.output_path:
            lines.append(f"**Çıktı Dosyası:** `{result.output_path.name}`  ")
        lines.append(f"**İşlem Süresi:** `{result.elapsed_ms:.1f} ms`  ")
        lines.append(f"**Durum:** `{'✅ Başarılı' if result.success else '❌ Başarısız'}`  ")
        lines.append("")

        if not result.success:
            lines.append(f"> [!WARNING]\n> Hata: {result.error_msg}\n")
            return "\n".join(lines)

        b_rep = result.before_report
        a_rep = result.after_report

        # Summary Table
        lines.append("## 📊 Genel Özet")
        lines.append("")
        lines.append("| Kriter | Temizleme Öncesi | Temizleme Sonrası | Değişim |")
        lines.append("| :--- | :--- | :--- | :--- |")
        b_cnt = b_rep.total_image_fields_count if b_rep else 0
        a_cnt = a_rep.total_image_fields_count if a_rep else 0
        lines.append(f"| **Toplam Metadata Alanı** | `{b_cnt}` | `{a_cnt}` | **-{result.removed_fields_count} kaldırıldı** |")
        
        b_high = b_rep.high_risk_count if b_rep else 0
        a_high = a_rep.high_risk_count if a_rep else 0
        lines.append(f"| 🔴 Yüksek Risk (GPS/Seri No) | `{b_high}` | `{a_high}` | -{b_high - a_high} |")

        b_med = b_rep.medium_risk_count if b_rep else 0
        a_med = a_rep.medium_risk_count if a_rep else 0
        lines.append(f"| 🟡 Orta Risk (Yazar/Tarih) | `{b_med}` | `{a_med}` | -{b_med - a_med} |")

        b_low = b_rep.low_risk_count if b_rep else 0
        a_low = a_rep.low_risk_count if a_rep else 0
        lines.append(f"| 🔵 Düşük Risk (ICC/Boyut) | `{b_low}` | `{a_low}` | -{b_low - a_low} |")
        lines.append("")

        # Category Breakdown
        lines.append("## 📂 Kategori Ayrımı")
        lines.append("")
        categories = [
            MetadataCategory.EXIF,
            MetadataCategory.GPS,
            MetadataCategory.XMP,
            MetadataCategory.IPTC,
            MetadataCategory.PNG_CHUNKS,
            MetadataCategory.ICC,
        ]

        lines.append("| Kategori | Bulunan | Kalan | Durum |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for cat in categories:
            b_cat = len(b_rep.get_fields_by_category(cat)) if b_rep else 0
            a_cat = len(a_rep.get_fields_by_category(cat)) if a_rep else 0
            if b_cat > 0 or a_cat > 0:
                status = "✅ Temizlendi" if a_cat == 0 else ("🛡️ Korundu" if cat == MetadataCategory.ICC else f"⚠️ {a_cat} Kalan")
                lines.append(f"| **{cat.value}** | `{b_cat}` | `{a_cat}` | {status} |")
        lines.append("")

        # Removed Fields List
        if b_rep and b_rep.image_metadata_fields:
            lines.append("## 🔍 Tespit Edilen & Temizlenen Detaylı Alanlar")
            lines.append("")
            for f in b_rep.image_metadata_fields:
                risk_icon = "🔴" if f.risk_level == MetadataRiskLevel.HIGH else ("🟡" if f.risk_level == MetadataRiskLevel.MEDIUM else "🔵")
                lines.append(f"- {risk_icon} **{f.human_name}** (`{f.tag_name}`): {f.display_value}")
            lines.append("")

        lines.append("---")
        lines.append("*Quickglint Privacy & Security Engine ile güvenle oluşturulmuştur.*")
        return "\n".join(lines)

    @classmethod
    def generate_plaintext(cls, result: CleanResult) -> str:
        """Generate a concise plain text report."""
        lines = []
        lines.append("=" * 60)
        lines.append("QUICKGLINT — METADATA TEMIZLEME RAPORU")
        lines.append("=" * 60)
        lines.append(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if result.input_path:
            lines.append(f"Giris Dosyasi: {result.input_path.name}")
        if result.output_path:
            lines.append(f"Cikti Dosyasi: {result.output_path.name}")
        lines.append(f"Islem Suresi: {result.elapsed_ms:.1f} ms")
        lines.append("-" * 60)

        b_cnt = result.before_report.total_image_fields_count if result.before_report else 0
        a_cnt = result.after_report.total_image_fields_count if result.after_report else 0
        lines.append(f"Toplam Bulunan Metadata: {b_cnt}")
        lines.append(f"Temizlenen Alan Sayisi:  {result.removed_fields_count}")
        lines.append(f"Kalan/Korunan Alanlar:   {a_cnt}")
        lines.append("-" * 60)
        lines.append("DURUM: TEMIZLENDI (LOCAL-FIRST)")
        lines.append("=" * 60)
        return "\n".join(lines)

