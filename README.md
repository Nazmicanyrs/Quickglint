# Quickglint 📸

**Quickglint**, modern, hafif, gizlilik odaklı ve açık kaynaklı bir Python ekran görüntüsü alma, kaydırmalı ekran yakalama (scrolling screenshot), panorama birleştirme, GIF oluşturma ve görsel düzenleme uygulamasıdır.

Lightshot'ın hızlı ve sezgisel kullanıcı deneyimini alır; **1:1 donanım seviyesi kristal netlik**, **yapay zeka/OCR destekli akıllı hassas bilgi gizleme (Smart Privacy)**, **kesintisiz sayfa kaydırma birleştirme** ve **kare bazlı GIF kaydedici/editörü** ile bir üst seviyeye taşır.

---

## 🌟 Öne Çıkan Özellikler

### 1. 🔒 Smart Privacy (Akıllı Hassas Bilgi Gizleme)
- **OCR Motoru Soyutlaması:** Tesseract, EasyOCR ve Mock OCR motorları ile %100 yerel (offline) metin çözümleme.
- **Gelişmiş Veri Tespiti:**
  - 📧 E-posta adresleri (OCR hata toleranslı)
  - 📱 Uluslararası ve yerel telefon numaraları (`phonenumbers`)
  - 🌐 IPv4 ve IPv6 adresleri
  - 🔗 Hassas parametre içeren URL'ler (`?token=`, `?api_key=`, `?password=`)
  - 🔑 API Anahtarları ve Gizli Token'lar (OpenAI `sk-...`, AWS `AKIA...`, GitHub `ghp_...`, Bearer, şifreler)
  - 💳 Kredi Kartı numaraları (**Luhn Algoritması** doğrulamalı)
  - 🏦 IBAN Numaraları (**ISO 7064 Mod-97** sağlama toplamı doğrulamalı)
  - 📁 Yerel dosya ve kullanıcı yolları (`C:\Users\...`, `/home/...`)
- **Esnek Maskeleme Seçenekleri:** Tek tıkla Mozaik (Pixelate), Bulanıklaştırma (Blur), Siyah Kutu (Blackout) veya Özel Renk Kutusu uygulama.
- **Geri Alınabilir Mimari:** Maskeler doğrudan katman nesnesi olarak eklenir; `Ctrl+Z` ile anında geri alınabilir.

### 2. 📜 Scrolling Screenshot (Kaydırmalı Ekran Görüntüsü)
- **Akıllı Sayfa Kaydırma:** Web sayfalarını, uzun sohbetleri veya kod pencerelerini otomatik kaydırarak tek bir dikey görüntüde birleştirir.
- **Şablon Eşleme & Çakışma Tespiti (Template Matching):** Çerçeveler arasındaki örtüşmeyi piksel hassasiyetinde hesaplar, mükerrer alanları eler.
- **Sayfa Sonu ve Donma Koruması:** Sayfa sonunu ve hareketsizliği algılayarak işlemi güvenle tamamlar.
- **Canlı İlerleme HUD'ı:** Kaydırma sırasında anlık kare sayısını ve toplam yüksekliği gösterir; durdurma ve iptal imkanı sunar.
- **Doğrudan Editöre Aktarma:** Birleştirilmiş uzun görüntü doğrudan çizim, metin ve Smart Privacy araçlarıyla düzenlenebilir.

### 3. 🎥 Ekran GIF Kaydedici & Zaman Çizelgesi Editörü
- **Bölgesel Kayıt:** Ekranın seçilen herhangi bir alanını 10, 15, 20, 24 veya 30 FPS hızında kaydeder.
- **3-2-1 Geri Sayım:** Kayıt başlamadan önce ekranda şık bir geri sayım animasyonu gösterir.
- **İmleç ve Tıklama Efektleri:** Fare imlecini, sarı vurgu halkasını (halo) ve sol/sağ tıklama dalgalarını otomatik olarak karelere işler.
- **İnteraktif GIF Editörü:**
  - ▶️ Oynat / Duraklat / Kare Kare İlerleme
  - ✂️ Başlangıç ve Bitiş Kırpma (Trim Sliders)
  - 🗑️ İstenmeyen kareleri tek tek silme
  - ⇄ Tersine çevirme (Reverse)
  - 🎞️ FPS değiştirme ve renk paleti optimizasyonu (Quantization & Frame Deduplication)
- **Arka Planda Dışa Aktarma:** UI donmadan yüksek kaliteli animasyonlu `.gif` dosyası üretir.

### 4. 🎨 Piksel Seviyesinde Düzenleme Araçları
- ✏️ Serbest Çizim Kalemi (Pen)
- 🖍️ Fosforlu Kalem / Vurgulayıcı (Highlighter)
- ↗️ Vektörel Ok Çizimi (Arrow)
- 📏 Düz Çizgi (Line)
- ⬜ Dikdörtgen & ⭕ Elips
- 🔤 Satır İçi Zengin Metin Ekleme (Inline Text Editor)
- 💧 Ayarlanabilir Bulanıklaştırma (Blur) & 🔲 Mozaik (Pixelate)
- 🎨 Hızlı Renk Paleti ve Özel Renk Seçici
- ↩️ Sınırsız Geri Al (Undo - `Ctrl+Z`) ve İleri Al (Redo - `Ctrl+Y`)

### 5. ⚡ Sistem ve Kullanılabilirlik
- **1:1 Donanım Pikselleri:** High-DPI ekranlarda sıfır kalite kaybı, Windows Snipping Tool ile birebir kristal netlik.
- **Otomatik Tuş Algılayan Kısayol Düzenleyici:** Ayarlardan herhangi bir kutucuğa tıklayıp klavyeden tuşa basarak kısayol atama.
- **Global Kısayollar:**
  - `PrintScreen` → Ekran Görüntüsü Al
  - `Ctrl + Shift + P` → Smart Privacy (Hassas Bilgi Gizleme)
  - `Ctrl + Shift + L` → Scrolling Screenshot (Kaydırmalı Ekran)
  - `Ctrl + Shift + G` → Record GIF (GIF Kaydedici)
- **Türkçe ve İngilizce Dil Desteği (i18n):** Ayarlardan anında dil değiştirme.
- **Sistem Tepsisi ve Bildirimler:** Windows başlangıcında çalışma, tepsi menüsü ve şık toast bildirimleri.

---

## 💻 Kurulum ve Çalıştırma

### Gereksinimler
- **Python 3.10+** (Python 3.12/3.14 önerilir)
- Windows 10/11 (Linux ve macOS uyumlu)

### 1. Bağımlılıkları Yükleyin
```powershell
pip install -r requirements.txt
```

*(İsteğe bağlı)* Tesseract OCR kullanmak isterseniz:
- Windows için: [Tesseract OCR Installer](https://github.com/UB-Mannheim/tesseract/wiki) indirip kurun.

### 2. Uygulamayı Başlatın
```powershell
python main.py
```

---

## 🧪 Testleri Çalıştırma

Tüm test paketini (Privacy, Scrolling, GIF, Editor, Capture) çalıştırmak için:

```powershell
pytest -v tests/
```

---

## 📦 Bağımsız Windows (.exe) Oluşturma

PyInstaller ile tek dosya `.exe` paketi derlemek için:

```powershell
python build_exe.py
```

Derlenen uygulama `dist/Quickglint/Quickglint.exe` dizininde hazır olacaktır.

---

## 📄 Lisans ve Kullanım Koşulları

Bu proje **Quickglint Source-Available Non-Commercial Share-Alike License (QSNCSL) 1.0.0** ile korunmaktadır.  
Telif Hakkı Sahibi: **[Nazmican Yaraş](https://github.com/Nazmicanyrs/)**

- ✅ **İnceleme ve Değişiklik:** Kaynak kodunu görebilir, değiştirebilir ve yeni özellikler ekleyebilirsiniz.
- ✅ **Değiştirilmiş sürüm yayımlama:** Değiştirilmiş bir sürüm yayımlanacaksa [LICENSE](LICENSE) dosyasındaki lisansın tamamı korunmalı ve telif hakkı sahibi belirtilmelidir.
- ❌ **Ticari kullanım:** Satış, kiralama, reklam, ücretli özellik, abonelik veya başka bir ticari kazanç amacı yasaktır.
- ⚠️ **Gizlilik ve sansürleme garantisi yoktur:** Vault, e-posta, kimlik numarası, IBAN ve diğer hassas verilerin tespiti veya korunması %100 garanti edilmez; sonuçları kullanıcı kontrol etmelidir.
- ⚠️ **ImgBB/API yükleme sorumluluğu:** Kullanıcı, kendi API anahtarıyla ImgBB’ye yüklediği dosyaların içeriğinden, izinlerinden, gizliliğinden ve üçüncü taraf hizmetteki saklama/işleme sonuçlarından kendisi sorumludur.
- ⚠️ **Sorumluluk Reddi (AS IS):** Kullanıcı yazılımı kendi sorumluluğunda kullanır. Veri kaybı, veri ifşası, sistem arızası ve uyumluluk sorunları dahil ayrıntılı şartlar için [LICENSE](LICENSE) dosyasını inceleyin.

## Windows Installer

Yeni sürüm etiketlendiğinde GitHub Actions otomatik olarak Quickglint için Windows
installer'ı oluşturur ve GitHub Releases bölümüne yükler. Kurulum sırasında [LICENSE](LICENSE)
görüntülenir ve kabul edilmeden kuruluma devam edilemez.

Installer, [GitHub Releases](https://github.com/Nazmicanyrs/Quickglint/releases)
sayfasından indirilebilir.

---

## English

Quickglint is a privacy-focused desktop application for screenshots, annotation,
OCR, PDF creation, GIF recording, panorama stitching, and sensitive-data redaction.

### Installation

Download the latest Windows installer from the
[GitHub Releases](https://github.com/Nazmicanyrs/Quickglint/releases) page.
The installer displays the [LICENSE](LICENSE), and installation cannot continue
unless the license is accepted.

### From source

```powershell
pip install -r requirements.txt
python main.py
```

To build the Windows executable locally:

```powershell
python build_exe.py
```

Quickglint is distributed under the **Quickglint Source-Available Non-Commercial
Share-Alike License (QSNCSL) 1.0.0**. Users may inspect and modify the source code
for non-commercial purposes. See [LICENSE](LICENSE) for the complete terms,
including the restrictions on commercial use, redistribution, privacy features,
and ImgBB/API uploads.


