# 🚀 CMC Daily Crawler

Tự động crawl top 1500 coin CoinMarketCap mỗi ngày lúc **7:00 sáng (giờ VN)**.

---

## 📋 Dữ liệu được lấy

### Bảng listing (1500 coin)
| Cột | Mô tả |
|-----|-------|
| rank | Thứ hạng market cap |
| name | Tên coin |
| symbol | Ký hiệu (BTC, ETH...) |
| slug | Slug URL (bitcoin, ethereum...) |
| price_usd | Giá USD |
| change_24h_pct | % thay đổi 24h |
| change_7d_pct | % thay đổi 7 ngày |
| market_cap_usd | Market Cap USD |
| volume_24h_usd | Volume 24h USD |
| circulating_supply | Lượng cung lưu thông |
| total_supply | Tổng cung |
| max_supply | Cung tối đa |
| date_snapshot | Ngày snapshot |

### Bảng detail (top 500 coin — thêm vào)
| Cột | Mô tả |
|-----|-------|
| fdv_usd | Fully Diluted Valuation |
| liq_mkt_cap_pct | Liq/Mkt Cap % (Volume/MarketCap) |
| vol_mkt_cap_24h_pct | Vol/Mkt Cap 24h % |

---

## ⚙️ Setup (làm 1 lần)

### Bước 1: Fork/Clone repo này lên GitHub

```bash
git clone https://github.com/YOUR_USERNAME/cmc-crawler.git
cd cmc-crawler
```

### Bước 2: Tạo Google Service Account

1. Vào [Google Cloud Console](https://console.cloud.google.com/)
2. Tạo project mới (hoặc dùng project có sẵn)
3. Vào **APIs & Services → Enable APIs**:
   - ✅ Google Sheets API
   - ✅ Google Drive API
4. Vào **APIs & Services → Credentials → Create Credentials → Service Account**
5. Điền tên, bấm Create
6. Vào Service Account vừa tạo → tab **Keys → Add Key → JSON**
7. Download file JSON về máy

### Bước 3: Tạo Google Spreadsheet

1. Vào [Google Sheets](https://sheets.google.com/), tạo spreadsheet mới
2. Đặt tên: **CMC Dashboard**
3. Copy **Spreadsheet ID** từ URL:
   ```
   https://docs.google.com/spreadsheets/d/[SPREADSHEET_ID]/edit
   ```
4. Share spreadsheet với email của Service Account (quyền **Editor**)
   - Email có dạng: `xxx@project-name.iam.gserviceaccount.com`

### Bước 4: Thêm Secrets vào GitHub

Vào repo GitHub → **Settings → Secrets and variables → Actions → New repository secret**

Thêm 2 secrets:

| Secret Name | Value |
|-------------|-------|
| `GOOGLE_CREDENTIALS_JSON` | Toàn bộ nội dung file JSON service account |
| `GOOGLE_SPREADSHEET_ID` | ID của spreadsheet ở Bước 3 |

### Bước 5: Enable GitHub Actions

1. Vào tab **Actions** trong repo
2. Click **"I understand my workflows, go ahead and enable them"**
3. Vào workflow **CMC Daily Crawler**
4. Click **"Enable workflow"**

---

## 🧪 Test chạy thử

Sau khi setup xong, chạy thử ngay:

1. Vào **Actions → CMC Daily Crawler**
2. Click **"Run workflow"** → **"Run workflow"**
3. Xem log real-time

Hoặc chạy local:
```bash
pip install -r requirements.txt
mkdir -p data logs

# Không có Google Sheets (chỉ save CSV)
python scripts/crawl_cmc.py

# Có Google Sheets
export GOOGLE_CREDENTIALS_JSON='{"type":"service_account",...}'
export GOOGLE_SPREADSHEET_ID='your_spreadsheet_id'
python scripts/crawl_cmc.py
```

---

## 📁 Cấu trúc output

```
data/
├── snapshot_2026-05-21.csv   ← Snapshot ngày hôm nay
├── snapshot_2026-05-22.csv   ← Snapshot ngày hôm sau
└── master_daily.csv          ← Tất cả ngày gộp lại (historical)

logs/
└── crawl.log                 ← Log chi tiết từng lần chạy
```

---

## 📊 Google Sheets Structure

| Sheet | Nội dung |
|-------|----------|
| **Daily Snapshot** | 1500 coin của ngày hôm nay (overwrite mỗi ngày) |
| **Master** | Tất cả ngày gộp lại — dùng filter theo `date_snapshot` |

### Tips dùng Google Sheets:
- Tạo sheet thứ 3 tên **"Dashboard"** với công thức QUERY:
  ```
  =QUERY(Master!A:Q, "SELECT * WHERE A=500 ORDER BY D DESC", 1)
  ```
- Dùng **Filter View** để lọc theo ngày
- Insert **Chart** từ data để visualize

---

## ⏰ Lịch chạy tự động

Mặc định: **7:00 AM Vietnam (00:00 UTC)** mỗi ngày.

Đổi giờ: Sửa `cron` trong `.github/workflows/daily_crawl.yml`:
```yaml
# 7:00 AM VN = 00:00 UTC
- cron: "0 0 * * *"

# 6:00 AM VN = 23:00 UTC (hôm trước)
- cron: "0 23 * * *"
```

---

## ❗ Troubleshooting

| Lỗi | Giải pháp |
|-----|-----------|
| `429 Too Many Requests` | Tăng `DELAY_LIST` và `DELAY_DETAIL` trong script |
| `GOOGLE_CREDENTIALS_JSON not set` | Kiểm tra lại GitHub Secrets |
| `Worksheet not found` | Script tự tạo sheet, không cần lo |
| `403 Forbidden` trên Sheets | Share sheet với email service account |
