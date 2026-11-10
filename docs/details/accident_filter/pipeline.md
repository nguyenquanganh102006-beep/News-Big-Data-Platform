# Luồng lọc tai nạn giao thông (task 23)

## Mục đích và phạm vi

Áp dụng bộ `rules-v3-road` vào dữ liệu Silver tích lũy. Dùng `title` và đoạn mở đầu `description`, không tải thân bài. Mỗi dòng là một bài báo, không phải một vụ tai nạn độc lập. Bước filter không trích xuất thông tin; bước tiếp theo được mô tả tại [task24 — trích xuất](../accident_extraction.md).

Luồng hỗ trợ cả 7 nguồn RSS. VnExpress, VietnamPlus và Tuổi Trẻ dùng preprocessor riêng; Dân Trí, Thanh Niên, Báo Xây Dựng và Tiền Phong dùng preprocessor RSS chung. Filter và extraction dùng cùng bộ luật cho cả 7 nguồn.

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

Thứ tự: RSS → file Bronze → preprocess + khử trùng URL → Silver tích lũy → Task 2.2 khử trùng nội dung → phân loại → lưu output lọc. Task 2.2 dùng TF-IDF + cosine trên tiêu đề/mô tả, mặc định ngưỡng `>= 0.85` trong cửa sổ 24 giờ. Bài trùng được gắn cờ/lưu ở `data/silver/deduplicated/`; chỉ bài gốc đi vào filter. Nếu một bước lỗi, pipeline dừng; không chạy bước tiếp theo. Xem [Task 2.2 — Duplicate Article Detection](../content_duplicate_detection.md).

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

Task 2.2 đọc toàn bộ `data/silver/<source>.parquet` của 7 nguồn để so sánh chéo nguồn. Filter sau đó đọc `data/silver/deduplicated/<source>.parquet` và chỉ phân loại bài gốc. Không lấy riêng DataFrame bài mới do preprocessor trả về: nếu batch không có bài mới vẫn phải giữ lịch sử đã chọn trước đó.

```text
data/silver/filtered/
  <source>/
    classified.parquet
    accident.parquet
    not_accident.parquet
    uncertain.parquet
```

- `classified.parquet`: toàn bộ bài gốc của nguồn kèm nhãn và lý do. Bài trùng được giữ ở `silver/deduplicated/`, không lặp trong các partition filter.
- `accident.parquet`: bài được chọn để chuyển sang bước trích xuất sau này.
- `not_accident.parquet`: bài không phù hợp, vẫn lưu để kiểm tra chọn nhầm/bỏ sót.
- `uncertain.parquet`: hàng chờ xem xét, chưa coi là bài tai nạn chắc chắn.

Giữ các cột đầu vào (kể cả article_key/source/link), bổ sung hoặc cập nhật:

| Cột | Ý nghĩa |
|---|---|
| accident_label | accident / not_accident / uncertain |
| filter_reason | Mã luật quyết định |
| filter_evidence | Tiêu đề hoặc lead đã chuẩn hóa dùng ở nhánh quyết định |
| filter_version | rules-v3-road |

Output lọc là bản dựng lại từ Silver hiện tại, được thay thế mỗi lần chạy; không append gây trùng qua các lần chạy. File của nhóm không có bài vẫn được ghi rỗng với schema đầy đủ để không giữ kết quả cũ. Không sửa input Silver. Thư mục output tự tạo; data đã có trong `.gitignore`.

Ghi file tạm rồi thay thế từng file sau khi ghi xong. Bốn file không được thay thế như một giao dịch duy nhất: nếu bị gián đoạn, chạy lại bước lọc để đồng bộ. Chỉ chạy một tiến trình ghi tại một thời điểm.

## Log và xử lý lỗi

Log thống kê chỉ in khi `DEBUG=True`.

```text
[Content dedup] input=..., duplicates=..., retained=...
[Filter] source=vnexpress, input=..., accident=..., not_accident=..., uncertain=...
```

Với mỗi nguồn, luôn có `input = accident + not_accident + uncertain`. Đây là số bài gốc được chuyển vào filter sau khi bỏ các bản trùng, không phải số vụ hoặc số bài mới của batch.

- Thiếu một trong 7 file Silver: báo đường dẫn thiếu trước khi bắt đầu ghi output; chạy preprocessors trước.
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
