
# Setup Guide

Hướng dẫn cài đặt môi trường Python, cài dependencies và chạy RSS Crawler.

## 1. Yêu cầu hệ thống

- Python >= 3.10
- pip
- Git

## 2. Cấu trúc dự án

> [flow.md](../flow.md)

## 3. Tạo môi trường ảo

Mở Terminal tại thư mục dự án:

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\Activate
```

### MacOS / Linux

```bash
source .venv/bin/activate
```

Sau khi kích hoạt thành công, Terminal thường hiển thị `(.venv)` ở đầu dòng.

## 4. Khai báo dependencies bằng `pyproject.toml`

Tạo file `pyproject.toml` tại thư mục gốc:

```toml
[project]
name = "rss-crawler"
version = "0.1.0"
description = "RSS crawler for collecting and storing article data"
requires-python = ">=3.10"
dependencies = [
    "requests",
    "beautifulsoup4",
    "feedparser",
    "pandas",
    "pyarrow",
    <!-- Them cac thu vien khac vao duoi nay -->
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

>[!NOTE]
> Nếu muốn thêm thư viện, thì viết ở chỗ tôi note, rồi chạy lại lệnh install là được

### Chức năng các thư viện

| Thư viện | Chức năng |
|---|---|
| requests | Gửi HTTP request và tải HTML |
| beautifulsoup4 | Phân tích HTML, trích xuất nội dung |
| feedparser | Đọc dữ liệu RSS/Atom |
| pandas | Xử lý dữ liệu dạng bảng |
| pyarrow | Đọc và ghi dữ liệu Parquet |
| setuptools | Hỗ trợ cài đặt project |
| ... | ... |

## 5. Cài đặt dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

Lệnh `pip install -e .` cài đặt project ở chế độ editable và tự động cài các dependencies khai báo trong `pyproject.toml`.

## 6. Update `.env`

Tạo file `.env` tại thư mục gốc (template là `.env.example`)

```bash
cp .env.example .env
```

Chỉnh sửa các biến, ví dụ biến `DEBUG` để print ra màn hình, giá trị là `True` (các giá trị khác tính là `False`, cái này do code tôi đang xử lý như thế cho đơn giản, file `src/config/main.py`)

>[!TIP]
> Ae nếu muốn print mấy dòng log không quan trọng ra màn hình để debug thì đều viết `if DEBUG: print(...)` nhé, còn khi nào muốn chạy thông thì đặt `DEBUG=False` để chạy thông luôn cho đỡ rối mắt.

## 7. Chạy các luồng 

Xem cụ thể ở file [`docs/flow.md`](./flow.md) rồi chạy từng luồng phụ (partial flows)

>[!NOTE]
> Do trong các luồng phụ tôi mặc định là folder đã tồn tại, nên ae tạo folder thủ công nhé (nhớ xem folder structure trong `flow.md` trước rồi tạo theo cho đúng)
> Folders cần tạo thủ công: `data/bronze`, `data/silver`, `data/gold`
> Sau này khi làm luồng chính (tổng hợp các luồng phụ) tôi mới thêm các hàm tạo folder tự động (`os.makedir()`) sau
