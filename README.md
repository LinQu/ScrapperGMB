# 🗺️ Google Maps Scraper v2.1 by Asira

Tool scraping otomatis untuk mengekstrak data rating, review, dan informasi tempat dari Google Maps.

## 📋 Fitur

- ✅ **Scraping Reviews** - Ambil review lengkap dengan rating, username, tanggal
- ✅ **Scraping Summary** - Ambil informasi tempat (rating, jumlah review, kategori, etc)
- ✅ **Multi-language Support** - Otomatis detect bahasa (Indonesia/Inggris)
- ✅ **Auto URL Detection & Conversion** - Otomatis handle short URL, normal URL, atau direct reviews link
- ✅ **Custom Fields** - Pilih field spesifik yang ingin di-scrape
- ✅ **Batch Processing** - Process multiple links sekaligus
- ✅ **Excel Output** - Hasil langsung ke format Excel

## 🚀 Quick Start

### Prerequisite

```bash
python3 --version  # Python 3.8+
pip install -r requirements.txt
```

### Instalasi Dependencies

```bash
pip install pandas playwright beautifulsoup4
playwright install  # Install browser drivers
```

## 📖 Cara Penggunaan

### Mode 1: Scrape Reviews (Ulasan)

Ambil data review dari Google Maps (username, rating, caption, tanggal).

```bash
python3 main.py \
  --mode reviews \
  --input input_links.xlsx \
  --output reviews.xlsx \
  --fields username,rating,caption,relative_date
```

**Contoh Output:**
| username | rating | caption | relative_date |
|----------|--------|---------|---------------|
| John Doe | 5.0 | Pelayanan terbaik! | 2 minggu yang lalu |
| Jane Smith | 4.0 | Bagus tapi lama | 1 bulan yang lalu |

### Mode 2: Scrape Summary (Ringkasan Tempat)

Ambil informasi lengkap tentang tempat (nama, rating, jumlah review, kategori).

```bash
python3 main.py --mode summary --input converted.xlsx --output summary.csv --fields name,overall_rating,n_reviews,pelayanan_count,angsuran_count,pengiriman_count,proses_count,stnk_count,bpkb_count,kasir_count,lain_lain_count
```

**Contoh Output:**
| name | overall_rating | n_reviews | pelayanan_count |
|------|----------------|-----------|-----------------|
| Dealer_Mobil_ABC | 4.8 | 250 | 85 |

### ✨ Auto URL Detection (Built-in!)

Tidak perlu konversi URL manual lagi! Fitur reviews mode otomatis handle semua format URL.

**Program mendukung 3 format URL:**
1. **Short URL**: `https://maps.app.goo.gl/b1UKcdF2j9AWWhSQ8`
2. **Normal URL**: `https://www.google.com/maps/place/Restoran/@lat,lng`
3. **Direct Reviews**: `https://www.google.com/maps/place/Restoran/reviews`

**Cukup jalankan satu command** - program otomatis deteksi dan konversi jika diperlukan:

```bash
python3 main.py --mode reviews \
  --input input_links.xlsx \
  --output reviews.xlsx
```

**File input bisa mix berbagai format URL** - program akan handle semuanya!

## 🎯 Field Options

### Review Fields
```
--fields username,rating,caption,relative_date,id_review,n_review_user,url_user
```

### Summary Fields
```
--fields name,overall_rating,n_reviews,address,phone_number,website,category,
         pelayanan_count,angsuran_count,pengiriman_count,proses_count,
         stnk_count,bpkb_count,kasir_count,lain_lain_count,lat,long
```

## ⚙️ Advanced Options

### Review Offset
Lewati N review pertama (contoh untuk pagination):

```bash
python3 main.py --mode reviews --input input_links.xlsx --output reviews.xlsx --offset 10
```

### Debug Mode
Jalankan dengan browser visible (untuk troubleshooting):

```bash
python3 main.py --mode reviews --input input_links.xlsx --debug
```

### Tanpa Filter Field
Ambil semua available fields:

```bash
python3 main.py --mode reviews --input input_links.xlsx --output reviews.xlsx
```

## 📁 Struktur File Input

File Excel input (`input_links.xlsx`) harus memiliki kolom **url**:

```
url
https://maps.app.goo.gl/xxxxx
https://maps.app.goo.gl/yyyyy
```

## 🔍 Troubleshooting

### Error: "Reject all button tidak ditemukan"
- Google Maps Anda menggunakan bahasa berbeda
- Solution: Tool akan otomatis try detect berbagai bahasa

### Error: "Timeout saat scroll"
- Reviews terlalu banyak, gunakan `--offset` untuk skip N reviews awal
- Atau gunakan `--max-scrolls 100` (custom)

### Review tidak lengkap
- Beberapa review mungkin di-hide, coba dengan `--debug` untuk lihat
- Pastikan Anda tidak terdeteksi sebagai bot (proxy/VPN mungkin membantu)

## 📊 Contoh Workflow Lengkap

```bash
# 1. Scrape summary info (auto-handle semua format URL)
python3 main.py --mode summary --input my_links.xlsx --output summary.xlsx \
  --fields name,overall_rating,n_reviews,pelayanan_count

# 2. Scrape reviews (otomatis convert URL jika perlu)
python3 main.py --mode reviews --input my_links.xlsx --output reviews.xlsx \
  --fields username,rating,caption

# File input bisa mix: short URLs, normal URLs, direct reviews links - semua supported!
```

## 🤖 Language Support

Tool secara otomatis detect dan handle:
- ✅ Bahasa Indonesia ("Saring ulasan", "Semua")
- ✅ Bahasa Inggris ("Filter reviews", "All")
- ✅ Bahasa Lainnya (best effort)

## ⚠️ Catatan Penting

1. **Rate Limiting** - Gunakan delay yang cukup antar request agar tidak blocked
2. **Login** - Untuk beberapa tempat, Anda mungkin perlu login Google
3. **Dinamis** - Layout Google Maps berubah, jika error report issue
4. **Terms of Service** - Pastikan penggunaan sesuai ToS Google Maps

## 📝 Log Files

Semua aktivitas tercatat di `gm-scraper.log`:
```
tail -f gm-scraper.log
```

## 🐛 Bug Reports

Jika ada error, check:
1. `gm-scraper.log` untuk detail error
2. Jalankan dengan `--debug` untuk lihat browser
3. Report dengan log messages + command yang dijalankan

## 📦 Dependencies

- `pandas` - Data manipulation & Excel export
- `playwright` - Browser automation
- `beautifulsoup4` - HTML parsing

## 📄 License

MIT License - Bebas digunakan untuk keperluan non-komersial

---

**Last Updated:** 2025  
**Version:** 2.0
