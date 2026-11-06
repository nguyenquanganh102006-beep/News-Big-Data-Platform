# 3.1 — Bộ lọc ứng viên sự kiện bằng dữ liệu giả

## Phần đã thực hiện

Đã bổ sung hàm `retrieve_candidates()` chạy trong bộ nhớ: nhận một bài báo và
bảng sự kiện Polars, trả về các sự kiện cùng tỉnh/thành trong cửa sổ thời gian.
Không cần crawler, file Gold, DuckDB hoặc phần 3.3 để chạy test.

Đây là bước tìm ứng viên; chưa kết luận cùng vụ, gán bài vào event hay tạo event
mới. Chưa tích hợp vào `main.py`; các lựa chọn `--step=0..4` giữ như hiện tại.

| File | Vai trò |
|---|---|
| `src/config/events.py` | Bán kính mặc định, cột bắt buộc và kiểu kết quả |
| `src/config/__init__.py` | Export cấu hình/kiểu kết quả theo cách tổ chức repo |
| `src/events/retrieval.py` | Kiểm tra đầu vào, chuẩn hóa, lọc và sắp ứng viên |
| `src/events/__init__.py` | Export `retrieve_candidates` |
| `tests/test_event_retrieval.py` | Tự tạo dữ liệu giả và kiểm tra hành vi |

## Quy tắc lọc

```text
cùng tỉnh sau chuẩn hóa
VÀ |anchor_published_at - published_at| <= radius_hours
```

Mặc định `radius_hours=24`: lấy từ 24 giờ trước đến 24 giờ sau, bao gồm hai biên.
Đây là cửa sổ rộng 48 giờ, khác với bán kính 48 giờ. DOCX có hai cách diễn đạt;
phần này chọn hướng dẫn cụ thể `[-24h, +24h]`, cho phép truyền bán kính khác.

- Tên tỉnh chuẩn hóa Unicode NFC, khoảng trắng, chữ hoa/thường và alias trong
  `PROVINCE_ALIASES` hiện có. Không tự suy tỉnh từ huyện hoặc đổi địa giới.
- Thời gian nhận `datetime` có timezone hoặc chuỗi ISO 8601 có offset/`Z`.
  So sánh theo UTC; không tự gán múi giờ cho giá trị thiếu timezone.
- Ngày đăng dùng làm mốc tìm ứng viên, không được coi là ngày xảy ra tai nạn.
- Giữ nguyên cột, schema và giá trị của các dòng sự kiện được chọn. Kết quả sắp
  tăng dần theo mốc thời gian UTC, rồi `event_id`; không cắt top-k.
- Không sửa đầu vào, không đọc/ghi file và không truy cập mạng.

## Hợp đồng đầu vào và kết quả

Bài là dictionary có `article_key`, `province`, `published_at`.
Bảng sự kiện có `event_id` (chuỗi duy nhất), `province`, `anchor_published_at`;
các cột bổ sung như địa điểm chi tiết hoặc phương tiện vẫn được giữ.

Hàm trả `RetrievalResult` gồm `article_key`, `status`, `candidates` (DataFrame),
`reasons` (tuple mã lý do):

| Trường hợp | Kết quả |
|---|---|
| Bài hợp lệ, có ứng viên | `ok`, bảng các sự kiện phù hợp |
| Bài hợp lệ, không có ứng viên/kho rỗng | `ok`, bảng rỗng giữ schema |
| Bài thiếu khóa/tỉnh/thời gian, tỉnh lạ hoặc thời gian lỗi | `needs_review`, bảng rỗng và mã lý do |
| Sai bán kính, bảng thiếu cột, ID sự kiện trùng hoặc dòng sự kiện không hợp lệ | `ValueError` |

Ví dụ mã lý do: `province_missing`, `province_unknown`,
`published_at_timezone_required`. Bài có nhiều lỗi sẽ nhận nhiều lý do.
Không biến kho sự kiện lỗi thành danh sách ứng viên rỗng hợp lệ. Hàm kiểm tra
cấu hình và schema trước; nếu bài cần review thì trả ngay, chưa duyệt từng dòng kho.

## Chạy test

Sau khi kích hoạt môi trường Python và cài dependencies của repo, từ thư mục gốc:

```bash
# Linux/macOS: chỉ test 3.1
PYTHONPATH=src python -m unittest discover -s tests -p 'test_event_retrieval.py' -v

# Toàn bộ test
PYTHONPATH=src python -m unittest discover -s tests -v
```

PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_event_retrieval.py" -v
```

Test tự tạo bài/sự kiện giả, không tạo dữ liệu trong `data/`. Bao gồm biên ±24
giờ, khác tỉnh, đổi bán kính, alias/Unicode, offset timezone, thứ tự ổn định,
giữ nguyên đầu vào/schema, input rỗng, bài thiếu dữ liệu và kho sự kiện lỗi.

Tại thời điểm bàn giao: 9/9 test của 3.1 và 54/54 test toàn repo đạt trên
Python 3.12.3, Polars 2.1.0. Ví dụ Python dưới đây cũng đã được chạy kiểm tra.

## Ví dụ dùng trực tiếp

Ví dụ Python dưới đây có thể chạy sau khi đặt `PYTHONPATH=src`:

```python
import polars as pl
from events import retrieve_candidates

article = {
    "article_key": "A01",
    "province": "Hà Nội",
    "published_at": "2026-10-30T12:00:00+07:00",
}
events = pl.DataFrame({
    "event_id": ["E01", "E02", "E03"],
    "province": ["Hà Nội", "Hải Phòng", "Hà Nội"],
    "anchor_published_at": [
        "2026-10-30T08:00:00+07:00",  # cùng tỉnh, trong cửa sổ
        "2026-10-30T08:00:00+07:00",  # khác tỉnh
        "2026-10-29T11:59:00+07:00",  # ngoài cửa sổ
    ],
})
result = retrieve_candidates(article, events)
print(result.status)                              # ok
print(result.candidates["event_id"].to_list())     # ['E01']
```

## Giới hạn và bước tiếp theo

Đây là baseline quét bảng trong bộ nhớ, chi phí theo số sự kiện đầu vào; chưa
phải truy vấn database tối ưu. Test dữ liệu giả xác minh quy tắc, chưa chứng minh
candidate recall trên bài báo thật hoặc độ đúng của các trường upstream.

Khi nối Gold, adapter sẽ ánh xạ `pub_date` thành `published_at` và kiểm tra dữ
liệu upstream. Khi làm 3.3, repository cung cấp sự kiện và có thể chuyển phép lọc
sang truy vấn SQL với cùng quy tắc UTC/biên thời gian. 3.2 nhận danh sách ứng viên
để chấm điểm và quyết định gộp; phần 3.1 hiện chưa lưu hay cập nhật sự kiện.
