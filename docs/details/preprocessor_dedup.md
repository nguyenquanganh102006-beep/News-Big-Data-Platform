# Dedup và lưu Silver tích lũy

Sau khi phân tích và làm sạch dữ liệu trong các file `src/preprocessors/rss_*.py`, preprocessor gọi các hàm `dedup_*` trong `utils.py` để bổ sung ba cột vào DataFrame trước khi loại trùng và ghi Silver:

| Cột | Ý nghĩa |
|---|---|
| `source` | Tên nguồn báo, ví dụ `vnexpress`, để phân biệt bài giữa các nguồn. |
| `normalized_url` | URL từ cột `link` sau chuẩn hóa, giúp nhận ra các URL chỉ khác tham số tracking. |
| `article_key` | Mã nhận diện bài báo bằng SHA-256 của nguồn và URL chuẩn hóa; dùng so trùng trong batch và lịch sử Silver. Không phải mã vụ tai nạn. |

## Chọn file Bronze

`latest_bronze_path(source, crawled_date=None)` được khai báo trong `src/config/preprocessors.py` và export qua `config`:

- Không truyền ngày: lấy file mới nhất.
- `YYYY-MM-DD`: lấy file mới nhất trong ngày đó.
- `YYYY-MM-DD hh:mm:ss`: lấy file đúng thời điểm đó; nếu trùng thời điểm thì chọn hậu tố lớn nhất.
- Không có file phù hợp: raise `FileNotFoundError`. Sai định dạng ngày: raise `ValueError`.

Cả ba hàm `rss_*_preprocessor(save_file=True, crawled_date=None)` và `run_preprocessors(crawled_date=None)` đều chuyển tham số này tới hàm chọn file. Ví dụ:

```python
from preprocessors import rss_vnexpress_preprocessor

rss_vnexpress_preprocessor(crawled_date="2026-10-24")
```

## Chuẩn hóa và loại trùng

Silver bổ sung `source`, `normalized_url` và `article_key`. Khóa là SHA-256 của `source + "\n" + normalized_url`, ổn định qua các lần crawl. Chuẩn hóa bỏ khoảng trắng ở hai đầu URL, fragment `#...`, chuyển scheme/host sang chữ thường và bỏ các tham số tracking trong `src/config/preprocessors.py` (không phân biệt hoa thường). Các query khác, thứ tự và encoding được giữ nguyên để tránh mất ID bài. Không gộp HTTP/HTTPS hoặc các URL khác path.

URL thiếu hoặc không hợp lệ có `normalized_url` và `article_key` là null; bản ghi vẫn được giữ lại. Dedup không gộp các bản có khóa null.

Kiểm tra khóa nhận diện từ thư mục gốc:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Silver history dedup

Sau khi tạo khóa, loại trùng trong batch theo `article_key`, giữ bản xuất hiện cuối cùng và giữ thứ tự tương đối của các bản còn lại. Sau đó dùng Polars `anti join` với lịch sử `data/silver/<source>.parquet` để lấy bài mới, rồi lưu lịch sử cũ + bài mới. Nếu chưa có Silver thì toàn bộ batch được xem là mới. Silver cũ chưa có khóa được bổ sung khóa từ `link`. Bài đã có giữ nguyên dữ liệu cũ.

Ghi vào file tạm rồi thay thế file đích sau khi ghi thành công. Chỉ chạy một tiến trình ghi cho mỗi nguồn tại một thời điểm. Hàm preprocessor trả về **các bài mới**; `save_file=False` chỉ tính kết quả, không ghi file.

Thống kê chỉ được in khi `DEBUG=True`:

```text
[Silver] source=..., input=..., batch_duplicates=..., history_duplicates=..., new=..., silver_total=..., status=saved
```

`input` là số dòng trước dedup; `batch_duplicates` là số bản dư trong batch; `history_duplicates` là số bản sau batch dedup đã có trong lịch sử; `new` là số bài mới. Luôn có `input = batch_duplicates + history_duplicates + new`. `silver_total` là tổng sau gộp; `status=dry_run` là kết quả dự kiến, chưa ghi file.

Chạy lại cùng batch có khóa hợp lệ cho `new=0`. Các bản khóa null vẫn được giữ và có thể lặp qua các lần chạy. Lịch sử bắt đầu từ Silver hiện có; chưa tự động nạp lại các file Bronze cũ.
