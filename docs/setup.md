
# Setup Guide

Hướng dẫn cài môi trường Python và chạy luồng từ RSS đến database sự kiện.

## 1. Yêu cầu hệ thống

- Python >= 3.10
- pip
- Git

## 2. Cấu trúc dự án

> [flow.md](flow.md)

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

Repo đã có `pyproject.toml`; dùng file hiện tại, không cần tạo lại.
Nếu thêm thư viện vào danh sách `dependencies`, chạy lại lệnh cài ở bước 5.

### Chức năng các thư viện

| Thư viện | Chức năng |
|---|---|
| requests | Gửi HTTP request và tải HTML |
| beautifulsoup4 | Phân tích HTML, trích xuất nội dung |
| feedparser | Đọc dữ liệu RSS/Atom |
| pandas | Xử lý dữ liệu dạng bảng |
| pyarrow | Đọc và ghi dữ liệu Parquet |
| setuptools | Hỗ trợ cài đặt project |
| polars | Làm sạch, đọc và ghi dữ liệu |
| duckdb, pytz | Lưu database và đọc thời gian có múi giờ |
| scikit-learn | So sánh nội dung các bài báo |
| ... | ... |

## 5. Cài đặt dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

Lệnh `pip install -e .` cài đặt project ở chế độ editable và tự động cài các dependencies khai báo trong `pyproject.toml`.
Lệnh này cũng giúp Python tìm được các module trong `src/`; không cần đặt
`PYTHONPATH` nếu chạy bằng đúng môi trường vừa cài.

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

Từ thư mục gốc, sau khi kích hoạt môi trường:

```bash
python -m main
python -m events.inspect
```

`main` tự tạo thư mục dữ liệu. Lệnh đầu lấy RSS và xử lý đến database; lệnh sau
hiển thị các sự kiện đã lưu. Nếu đã có bài trích xuất trong
`data/silver/accidents/` và chỉ muốn chạy phần sự kiện,
dùng `python -m main --step=5`.

Xem [hướng dẫn dễ hiểu và kết quả chạy thật](details/event_database_guide.md).

## 8. Redis và Streaming Consumer (4.1–4.2)

Luồng streaming chạy riêng với luồng `main`. Cài Docker Desktop và khởi động
engine, sau đó chạy tại gốc repository:

```powershell
docker compose up -d --wait redis
docker compose exec -T redis redis-cli ping
.venv/Scripts/python.exe -m streaming.run
```

`PONG` xác nhận Redis sẵn sàng. Biến môi trường Redis và database streaming
được mô tả trong `.env.example`, đọc bởi `src/config/streaming.py`.
Xem [luồng tổng thể](flow.md) và [hướng dẫn streaming](details/streaming.md)
để gửi bài bằng Producer, kiểm tra dữ liệu và chạy test.
