# 🚀 9Chain Auto Mining Bot

Bot otomasi untuk platform **9Chain** yang mendukung daily check-in, tap-tap mining, upgrade komponen, dan upgrade tier node secara paralel untuk banyak akun sekaligus.

---

## ✨ Fitur Utama

- ✅ **Multi-Account Support** — Proses banyak akun secara paralel dengan `ThreadPoolExecutor`
- 🔄 **Auto Loop Harian** — Otomatis standby dan reset pada jam tertentu (default: 07:00 WIB)
- 👆 **Tap Otomatis** — Tap sampai kuota habis, termasuk bonus dari daily/streak/level
- 🎁 **Daily Check-in** — Klaim reward harian otomatis
- ⚙️ **Upgrade Komponen** — Upgrade CPU, RAM, Firewall, dll secara otomatis
- 🏆 **Upgrade Node Tier** — Naikkan tier node otomatis
- 🔐 **Token Cache** — Simpan token JWT agar tidak perlu login ulang
- 📊 **Live Dashboard** — Tampilan real-time dengan `rich` library
- 🔁 **Auto Token Refresh** — Refresh token otomatis jika expired

---

## 📋 Persyaratan

- **Python** 3.9 atau lebih baru
- **Akun 9Chain** yang valid (email + password)
- Koneksi internet stabil

---

## 🛠️ Instalasi

### 1. Clone Repository

```bash
git clone https://github.com/username/9chain.git
cd 9chain
```

### 2. Install Dependencies

```bash
pip install requests rich
```

Atau jika menggunakan `requirements.txt`:

```bash
pip install -r requirements.txt
```

**Isi `requirements.txt`:**

```
requests>=2.28.0
rich>=13.0.0
```

### 3. Siapkan File `accounts.json`

Buat file `accounts.json` di root folder dengan format:

```json
[
  {
    "email": "akun1@example.com",
    "password": "password123"
  },
  {
    "email": "akun2@example.com",
    "password": "password456"
  }
]
```

> ⚠️ **PENTING:** Jangan upload `accounts.json` ke GitHub! Sudah ada di `.gitignore`.

### 4. (Opsional) Buat `.gitignore`

```gitignore
# Sensitive files
accounts.json
tokens.json
login_results.json

# Python
__pycache__/
*.py[cod]
*.egg-info/
venv/
env/
.venv/

# IDE
.vscode/
.idea/
*.swp
.DS_Store
```

---

## 🚀 Cara Penggunaan

### Jalankan Bot

```bash
python 9chain.py
```

### Pilih Mode Aksi

Saat pertama kali dijalankan, bot akan menampilkan menu:

```
Pilih mode aksi:
  1) Daily check-in (auto loop ke daily+tap setelah selesai)
  2) Tap-tap (auto loop ke daily+tap setelah selesai)
  3) Daily + Tap-tap Loop (Auto Standby Reset Harian)
  4) Upgrade komponen (auto loop ke daily+tap setelah selesai)
  5) Upgrade Tier (auto loop ke daily+tap setelah selesai)
```

**Penjelasan Mode:**

| Mode | Deskripsi |
|------|-----------|
| **1. Daily** | Klaim check-in harian, lalu masuk loop daily+tap |
| **2. Tap** | Tap sampai kuota habis, lalu masuk loop daily+tap |
| **3. Both** ⭐ | Loop otomatis daily + tap, standby sampai reset harian |
| **4. Upgrade** | Upgrade komponen terpilih, lalu masuk loop daily+tap |
| **5. Tier** | Upgrade node tier, lalu masuk loop daily+tap |

> 💡 **Rekomendasi:** Pilih mode **3** untuk bot berjalan terus-menerus.

---

## ⚙️ Konfigurasi

Edit bagian berikut di dalam script untuk menyesuaikan perilaku bot:

### Konfigurasi Tap

```python
# ==================== KONFIGURASI TAP ====================
TAP_BATCH_SIZE = 2              # Jumlah tap per request
TAP_DELAY_SECONDS = 1.0         # Delay antar request (detik)
TAP_RETRY_DELAY = 5             # Delay saat retry jika error
TAP_MAX_CONSECUTIVE_ERRORS = 10 # Maksimal error beruntun sebelum berhenti
# ========================================================
```

### Konfigurasi Loop

```python
# ==================== KONFIGURASI LOOP ====================
WIB_RESET_HOUR = 7              # Jam reset harian (WIB)
MAX_WORKERS = 10                # Jumlah worker paralel
CYCLE_DELAY_MINUTES = 1         # Delay 1 menit SEBELUM memulai cycle
# ========================================================
```

**Penjelasan:**

| Parameter | Default | Deskripsi |
|-----------|---------|-----------|
| `TAP_BATCH_SIZE` | `2` | Jumlah tap per request API |
| `TAP_DELAY_SECONDS` | `1.0` | Jeda antar request tap (detik) |
| `TAP_RETRY_DELAY` | `5` | Jeda saat retry setelah error |
| `TAP_MAX_CONSECUTIVE_ERRORS` | `10` | Batas error beruntun |
| `WIB_RESET_HOUR` | `7` | Jam reset harian (WIB) |
| `MAX_WORKERS` | `10` | Jumlah thread paralel |
| `CYCLE_DELAY_MINUTES` | `1` | Jeda sebelum cycle baru |

---

## 📁 Struktur File

```
9chain-bot/
├── bot.py                    # Script utama
├── accounts.json             # Data akun (JANGAN di-commit!)
├── tokens.json               # Cache token (auto-generated)
├── login_results.json        # Hasil login (auto-generated)
├── requirements.txt          # Dependencies
├── .gitignore                # Git ignore rules
└── README.md                 # Dokumentasi ini
```

**File yang di-generate otomatis:**

- `tokens.json` — Cache access token per akun
- `login_results.json` — Log hasil eksekusi terakhir

---

## 📊 Tampilan Dashboard

Bot akan menampilkan dashboard live seperti ini:

```
╭────────────── 🚀 9CHAIN • DAILY+TAP • CYCLE #5 ──────────────╮
│ # │ ACCOUNT         │ LOGIN     │ DAILY │ TAP-TAP │ TIER │ DETAIL │
│ 1 │ akun1@example   │ LOGIN OK  │ DONE  │ 500/500 │ T3   │ ...    │
│ 2 │ akun2@example   │ CACHE     │ SKIP  │ 500/500 │ T2   │ ...    │
│ 3 │ akun3@example   │ LOGIN OK  │ DONE  │ 450/500 │ T1   │ ...    │
╰──────────────────────────────────────────────────────────────╯
Accounts: 3 • Next daily: 06:45:12 • Tap: 2/batch @ 1.0/s
```

**Kolom:**

- **LOGIN** — `CACHE` (pakai token lama) atau `LOGIN OK` (login baru)
- **DAILY** — `DONE`, `SKIP` (sudah check-in), atau `ERROR`
- **TAP-TAP** — Progress tap (contoh: `1000/1000 ✅` = selesai)
- **TIER** — Tier node saat ini
- **DETAIL** — Info detail reward, streak, error, dll

---

## 🔒 Keamanan

> ⚠️ **PERINGATAN KEAMANAN**

1. **JANGAN PERNAH** commit file `accounts.json` ke GitHub
2. **JANGAN PERNAH** share token JWT ke publik
3. Gunakan **password unik** untuk setiap akun 9Chain
4. File `tokens.json` berisi access token — jaga kerahasiaannya
5. Review kode sebelum menjalankan pada akun utama
6. Gunakan **VPS/PC pribadi** — jangan di lingkungan publik

**File yang HARUS di-ignore di Git:**

```
accounts.json
tokens.json
login_results.json
```

---

## ❓ Troubleshooting

### Error: `File tidak ditemukan: accounts.json`

**Solusi:** Buat file `accounts.json` di root folder dengan format yang benar.

### Error: `Rich belum terinstall`

**Solusi:**

```bash
pip install rich
```

### Error: `Token expired` berulang

**Solusi:** Bot akan otomatis refresh token. Jika terus terjadi, cek kredensial akun.

### Bot berhenti tiba-tiba

**Solusi:** Cek log error. Kemungkinan penyebab:

- Koneksi internet terputus
- Akun terkena rate-limit
- Server 9Chain down

### Tap tidak selesai (PARTIAL)

**Solusi:** Kuota mungkin bertambah karena bonus. Bot akan otomatis mendeteksi dan lanjut tap.

---

## 🧠 Cara Kerja

```
┌─────────────────┐
│  Load Accounts  │
└────────┬────────┘
         ↓
┌─────────────────┐
│  Load Token     │──→ Token valid? ──→ Pakai token cache
│     Cache       │
└────────┬────────┘
         ↓ (tidak valid)
┌─────────────────┐
│   Login API     │
└────────┬────────┘
         ↓
┌─────────────────┐
│  Daily Check-in │
└────────┬────────┘
         ↓
┌─────────────────┐
│   Tap Mining    │──→ Loop sampai kuota habis
└────────┬────────┘
         ↓
┌─────────────────┐
│  Standby Reset  │──→ Tunggu jam 07:00 WIB
└────────┬────────┘
         ↓
    (ulangi cycle)
```

---

## 📝 Changelog

### v1.0.0

- ✨ Initial release
- ✅ Multi-account parallel processing
- ✅ Auto token refresh
- ✅ Tap sampai kuota habis dengan deteksi bonus
- ✅ Daily check-in otomatis
- ✅ Upgrade komponen & tier
- ✅ Live dashboard dengan rich
- ✅ Auto standby sampai reset harian

---

## ⚖️ Disclaimer

> **PENGGUNAAN RISIKO SENDIRI**

Bot ini dibuat untuk **tujuan edukasi** dan **otomasi pribadi**. Penggunaan bot dapat melanggar Terms of Service platform 9Chain. Pengembang **tidak bertanggung jawab** atas:

- Akun yang terkena banned/suspend
- Kehilangan aset atau reward
- Kerusakan perangkat
- Konsekuensi hukum apapun

**Gunakan dengan bijak dan tanggung jawab sendiri.**

---

<div align="center">

**Made with ❤️ for 9Chain Community**

⭐ Jangan lupa kasih bintang ya! ⭐

</div>
