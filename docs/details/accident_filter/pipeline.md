# Luồng lọc tai nạn giao thông (task 23)

## Mục đích và phạm vi

Áp dụng nguyên bộ `rules-v1` đã chốt vào dữ liệu Silver tích lũy. Dùng `title` và câu đầu `description`, không tải thân bài, không thay đổi luật sau đánh giá. Mỗi dòng là một bài báo, không phải một vụ tai nạn độc lập. Chưa trích xuất province, district, vehicles, casualties và chưa tạo Gold nghiệp vụ.

Nguồn đang hỗ trợ: VnExpress, VietnamPlus, Tuổi Trẻ, tương ứng 3 preprocessor hiện có. Crawler vẫn lấy 7 nguồn nhưng 4 nguồn còn lại chưa có Silver nên chưa được lọc trong luồng này.

## Cài đặt và chạy

PowerShell tại thư mục gốc dự án, dùng Python >= 3.10:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
if (!(Test-Path .env)) { Copy-Item .env.example .env }
New-Item -ItemType Directory -Force data/silver | Out-Null
```

Chạy toàn bộ luồng:

```powershell
.\.venv\Scripts\python.exe -m main
```

Thứ tự: RSS → file Bronze → preprocess + dedup batch/lịch sử → Silver tích lũy → phân loại → lưu output lọc. Nếu một bước lỗi, pipeline dừng; không chạy bước tiếp theo.

Đã có Bronze, chạy preprocessors rồi filters:

```powershell
.\.venv\Scripts\python.exe -m main --step=2
.\.venv\Scripts\python.exe -m main --step=3
```

Chỉ lọc lại Silver hiện có (`--step=1` chỉ chạy crawler):

```powershell
.\.venv\Scripts\python.exe -m main --step=3
```

Các lệnh cũ `python -m crawlers.run` và `python -m preprocessors.run` vẫn chỉ chạy từng bước riêng. Muốn tự động chạy bước lọc sau preprocessors, dùng `python -m main`.

## Đường dẫn và dữ liệu đầu ra

Input `data/silver/<source>.parquet` được đọc toàn bộ. Không lấy riêng DataFrame bài mới do preprocessor trả về: nếu batch không có bài mới vẫn phải giữ các bài đã chọn trước đó.

```text
data/filtered/
  vnexpress/
    classified.parquet
    accident.parquet
    not_accident.parquet
    uncertain.parquet
  vietnamplus/               # cấu trúc tương tự
  tuoitre/                   # cấu trúc tương tự
```

- `classified.parquet`: toàn bộ Silver nguồn đó kèm nhãn và lý do.
- `accident.parquet`: bài được chọn để chuyển sang bước trích xuất sau này.
- `not_accident.parquet`: bài không phù hợp, vẫn lưu để kiểm tra chọn nhầm/bỏ sót.
- `uncertain.parquet`: hàng chờ xem xét, chưa coi là bài tai nạn chắc chắn.

Giữ các cột đầu vào (kể cả article_key/source/link), bổ sung hoặc cập nhật:

| Cột | Ý nghĩa |
|---|---|
| accident_label | accident / not_accident / uncertain |
| filter_reason | Mã luật quyết định |
| filter_evidence | Tiêu đề hoặc lead đã chuẩn hóa dùng ở nhánh quyết định |
| filter_version | rules-v1 |

Output lọc là bản dựng lại từ Silver hiện tại, được thay thế mỗi lần chạy; không append gây trùng qua các lần chạy. File của nhóm không có bài vẫn được ghi rỗng với schema đầy đủ để không giữ kết quả cũ. Không sửa input Silver. Thư mục output tự tạo; data đã có trong `.gitignore`.

Ghi file tạm rồi thay thế từng file sau khi ghi xong. Bốn file không được thay thế như một giao dịch duy nhất: nếu bị gián đoạn, chạy lại bước lọc để đồng bộ. Chỉ chạy một tiến trình ghi tại một thời điểm.

## Log và xử lý lỗi

Log thống kê chỉ in khi `DEBUG=True`.

```text
[Filter] source=vnexpress, input=86, accident=2, not_accident=78, uncertain=6
```

Luôn có `input = accident + not_accident + uncertain`. Đây là số bài trên Silver tích lũy, không phải số vụ hoặc số bài mới của batch.

- Thiếu một trong 3 file Silver: báo đường dẫn thiếu trước khi bắt đầu ghi output; chạy preprocessors trước.
- Thiếu cột title: báo lỗi schema, không đoán nội dung từ các cột khác.
- Title null/rỗng: nhãn uncertain. Description thiếu: dùng tiêu đề.
- Silver rỗng nhưng có schema title: tạo output rỗng.
- Thay nguồn/đường dẫn output tại `src/config/filters.py`; đường dẫn Silver lấy từ `src/config/crawlers.py`. Chỉ thêm nguồn khi đã có preprocessor và Silver tương ứng.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m filters.evaluate --samples data/reviewed_accidents.jsonl --output data/evaluation/accident_filter
```

Test kiểm tra phân nhóm, giữ khóa/cột, không sửa Silver, chạy lại không nhân đôi output, input rỗng/thiếu cột, thứ tự pipeline và dừng khi lỗi.

Lệnh đánh giá cần file nhãn đã được kiểm duyệt do người dùng chuẩn bị. Schema đầu vào và cách sinh JSON: [rules_v1.md](rules_v1.md). Chưa có kết quả kiểm định độc lập trong repo. Output uncertain cần được xem xét; chưa có cơ chế lưu quyết định duyệt tay vào pipeline.
