# Trích xuất thông tin tai nạn — task24

## Chạy

Từ thư mục gốc, sau khi có kết quả filter:

```powershell
.\.venv\Scripts\python.exe -m main --step=4
```

`--step=0` hoặc không truyền step chạy toàn bộ: crawler → preprocessors → filters → extractors.
Không cần API key hoặc dịch vụ LLM.

## Input và output

Input: `data/filtered/<source>/accident.parquet`, ba nguồn theo `EXTRACT_SOURCES`.
Đọc toàn bộ `title` và `description`, giải mã HTML entity và chuẩn hóa Unicode NFC.
Không crawl thân bài; không sửa file đầu vào, không tự sửa nhãn của filter.

Output: `data/gold/accidents/<source>.parquet`. Giữ nguyên các cột đầu vào và bổ sung:

| Cột | Ý nghĩa |
|---|---|
| province, district, ward | Tỉnh/thành, quận/huyện/thị xã, phường/xã/thị trấn được nêu rõ; thiếu là null |
| vehicles | Danh sách loại phương tiện chuẩn hóa; không tìm được là danh sách rỗng |
| fatalities, injuries | Số chết, bị thương; không đủ bằng chứng là null |
| incident_types | Danh sách diễn biến: va_cham, tong_duoi, can_nguoi, lat_xe, mat_lai, chay_xe, dam_vat_can, tu_nga, roi_xuong |
| evidence_json | JSON chứa các đoạn khớp luật trong văn bản đã làm sạch |
| review_reasons | Các trường thiếu, mâu thuẫn hoặc ngữ cảnh phủ định/giả định cần xem xét |
| extraction_version | Phiên bản bộ luật trích xuất |

Mỗi lần chạy dựng lại output từ toàn bộ input, ghi file tạm rồi thay thế từng file.
Không gộp nhiều bài thành một vụ; không cộng thương vong giữa các bài.
Nếu một nguồn thiếu input thì dừng trước khi ghi. Nếu lỗi giữa các nguồn thì chạy lại để đồng bộ.
Log chỉ in khi `DEBUG=True`.

## Tổ chức code và quy tắc

- `src/config/extractors.py`: schema, dataclass, từ điển, regex, cấu hình đường dẫn; export qua `config`.
- `src/extractors/accident.py`: trích xuất một bài, xử lý DataFrame, đọc và ghi file.
- `src/extractors/run.py`: chỉ gọi hàm xử lý; package export qua `__init__.py`.
- Phiên bản hiện tại: `rules-v2`.
- Địa danh chỉ nhận khi có ngữ cảnh vị trí hoặc tiền tố tiêu đề. Xét ngữ cảnh ngay trước địa danh để loại tên đường/cao tốc, vẫn giữ “đường Nguyễn Trãi tại Hà Nội”. Loại một số mẫu nơi cư trú/bệnh viện; không suy ra tỉnh từ phường/xã, không nhận “xã” bên trong “thị xã”. Tên cấp dưới phải viết hoa hoặc là số.
- Từ điển được mở rộng với tên tỉnh/thành và tên lịch sử thường gặp. Đây là từ vựng nhận diện văn bản, không phải danh mục hành chính có hiệu lực hoặc bảng ánh xạ địa giới. Ví dụ gặp “Hải Dương” thì giữ “Hải Dương”, không tự đổi sang tên khác.
- Phương tiện xét từng lần xuất hiện: không lấy “ô tô” chung từ “ô tô tải”, nhưng vẫn giữ ô tô con khi đi cùng xe tải. Tách xe máy điện/xe đạp điện.
- Thương vong nhận số nguyên, dấu phân cách hàng nghìn, số bằng chữ theo mẫu tới hàng trăm, thứ tự “2 người chết”/“chết 2 người”, tuổi nạn nhân và số kèm vai trò như “hai tài xế”. Không tách “2 người thương vong” thành chết/bị thương.
- Không cộng số từ tiêu đề với mô tả. Chỉ cộng trong cùng đoạn khi có hai nhóm được nêu rõ là khác nhau (người khác, hiện trường/bệnh viện) hoặc hai vai trò tách biệt trong cấu hình (tài xế/phụ xe, học viên/thầy dạy lái). Đối chiếu kết quả hai đoạn; mâu thuẫn hoặc không rõ nhóm thì null.
- Số cập nhật với “thêm”, “sau đó” cần tổng cuối được nêu rõ để thay số cũ; không tự cộng. Tách cờ số bị thương đã đổi trạng thái sang tử vong. Bài nêu nhiều vụ được gắn cờ và không trả số thương vong chung như một vụ.
- Số xấp xỉ, khoảng và số không phân tích được không được chốt thành số chính xác. Chỉ ghi 0 với xác nhận rõ như “không ai bị thương”, “không có thương vong”. Không coi “chưa ghi nhận” là 0.
- Phủ định xét tại mệnh đề/sự kiện, không xóa 2 người chết vì câu sau viết “chưa rõ nguyên nhân”. “Suýt chết sau va chạm” vẫn giữ diễn biến va chạm; tiêu đề giả định/near-miss không được biến thành tai nạn đã xác nhận.

## Giới hạn và kiểm tra

Đây là baseline theo luật, chưa phải kết quả được kiểm định chất lượng. Regex chưa hiểu đầy đủ quan hệ ngữ nghĩa, đồng tham chiếu, mệnh đề lồng nhau, địa điểm quê quán/điều trị, số tổng và các nhóm giao nhau. Các mẫu khó hoặc viết địa danh không chuẩn vẫn có thể bị bỏ sót hoặc nhận nhầm. Chưa có phép chuẩn hóa địa giới theo ngày sự kiện và chưa đối chiếu đủ mọi tên quận/huyện/phường/xã bằng từ điển.
Bài được filter chọn nhầm vẫn có thể xuất hiện trong Gold; `missing_incident_details` giúp nhận biết trường hợp cần xem xét, không thay thế việc duyệt nhãn.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Test chức năng bao gồm các lỗi phản ví dụ: phủ định nguyên nhân, ô tô con đi cùng xe tải, đếm vai trò nạn nhân, số bằng chữ/đảo thứ tự, tổng và thành phần, cập nhật tử vong, nơi cư trú/bệnh viện, địa điểm sau tên đường, cấp hành chính chồng nhau; cùng HTML/Unicode, input rỗng, bảo toàn input và chạy lại không nhân đôi.
Cần một tập bài được người kiểm duyệt gán thông tin từng trường để đo chất lượng thực tế.
