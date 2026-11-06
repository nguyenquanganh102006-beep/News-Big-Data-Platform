# Trích xuất thông tin tai nạn — task24

## Chạy

Từ thư mục gốc, sau khi có kết quả filter:

```powershell
.\.venv\Scripts\python.exe -m main --step=4
```

`--step=0` hoặc không truyền step chạy toàn bộ, gồm bước lưu sự kiện sau extractors.
Không cần API key hoặc dịch vụ LLM.

## Input và output

Input: `data/filtered/<source>/accident.parquet`, ba nguồn theo `EXTRACT_SOURCES`.
Đọc toàn bộ `title` và `description`, giải mã HTML entity và chuẩn hóa Unicode NFC.
Riêng VnExpress, bước này mở URL của bài đã được filter chọn và đọc nhãn
tỉnh/thành nằm đầu bài (`p.description span.location-stamp`). Ví dụ nhãn
`TP Huế` được nhận diện là `Huế`. Không dùng toàn bộ thân bài để trích xuất thêm
thương vong hay phương tiện trong thay đổi này. Không sửa file đầu vào, không
tự sửa nhãn của filter. Chạy bước 4 cần mạng để mở các bài VnExpress.

Output: `data/silver/accidents/<source>.parquet`. Giữ nguyên các cột đầu vào và bổ sung:

| Cột | Ý nghĩa |
|---|---|
| province, district, ward | Tỉnh/thành, quận/huyện/thị xã, phường/xã/thị trấn được nêu rõ; thiếu là null |
| vehicles | Danh sách loại phương tiện chuẩn hóa; không tìm được là danh sách rỗng |
| fatalities, injuries | Số chết, bị thương; không đủ bằng chứng là null |
| incident_types | Danh sách diễn biến: va_cham, tong_duoi, can_nguoi, lat_xe, mat_lai, chay_xe, dam_vat_can, tu_nga, roi_xuong |
| evidence_json | JSON chứa các đoạn khớp luật trong văn bản đã làm sạch |
| review_reasons | Các trường thiếu, mâu thuẫn hoặc ngữ cảnh phủ định/giả định cần xem xét |
| extraction_version | Phiên bản bộ luật trích xuất |
| article_location_text | Riêng VnExpress: nhãn địa điểm đọc được từ đầu bài |
| article_location_status | Riêng VnExpress: `ok`, `missing`, `unknown`, `ambiguous`, lỗi tải trang/URL… |
| article_location_url | Riêng VnExpress: URL trang dùng làm bằng chứng địa điểm |

Mỗi lần chạy dựng lại output từ toàn bộ input, ghi file tạm rồi thay thế từng file.
Không gộp nhiều bài thành một vụ; không cộng thương vong giữa các bài.
Nếu một nguồn thiếu input thì dừng trước khi ghi. Nếu lỗi giữa các nguồn thì chạy lại để đồng bộ.
Log chỉ in khi `DEBUG=True`.

## Tổ chức code và quy tắc

- `src/config/extractors.py`: schema, dataclass, từ điển, regex, cấu hình đường dẫn; export qua `config`.
- `src/extractors/accident.py`: trích xuất một bài, xử lý DataFrame, đọc và ghi file.
- `src/extractors/vnexpress.py`: mở bài VnExpress và đọc nhãn địa điểm đầu bài;
  xử lý lỗi mạng, giới hạn thời gian/dung lượng, kiểm tra URL và redirect.
- `src/extractors/run.py`: chỉ gọi hàm xử lý; package export qua `__init__.py`.
- Phiên bản hiện tại: `rules-v2`.
- Bài VnExpress được bổ sung nhãn địa điểm có phiên bản
  `rules-v2+vnexpress-dateline-v1`. Các nguồn khác giữ cách trích xuất hiện tại.
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
Bài được filter chọn nhầm vẫn có thể xuất hiện trong Silver; `missing_incident_details` giúp nhận biết trường hợp cần xem xét, không thay thế việc duyệt nhãn.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Test chức năng bao gồm các lỗi phản ví dụ: phủ định nguyên nhân, ô tô con đi cùng xe tải, đếm vai trò nạn nhân, số bằng chữ/đảo thứ tự, tổng và thành phần, cập nhật tử vong, nơi cư trú/bệnh viện, địa điểm sau tên đường, cấp hành chính chồng nhau; cùng HTML/Unicode, input rỗng, bảo toàn input và chạy lại không nhân đôi.
Cần một tập bài được người kiểm duyệt gán thông tin từng trường để đo chất lượng thực tế.

## Bổ sung tỉnh/thành từ đầu bài VnExpress — phần 2

Hàm trích xuất cơ bản và test vẫn có thể chạy chỉ bằng tiêu đề/mô tả. Khi chạy
`python -m main --step=4`, riêng nguồn VnExpress được bổ sung dữ liệu từ trang bài:

1. Lấy URL của bài đã được chọn ở bước lọc.
2. Mở trang VnExpress, chỉ đọc nhãn tỉnh/thành ở đầu mô tả bài.
3. Đối chiếu nhãn với từ điển tỉnh/thành hiện có. Không suy tỉnh từ tên cầu,
   tuyến đường, nơi cư trú hoặc các địa danh xuất hiện ở phần khác của trang.
4. Nếu RSS đang thiếu tỉnh và nhãn rõ ràng, điền `province`, bỏ cờ
   `missing_province` và lưu nhãn/URL trong `evidence_json`.
5. Nếu tỉnh từ RSS khác nhãn đầu bài hoặc RSS đã có nhiều tỉnh mơ hồ, giữ tỉnh
   trống và ghi `conflicting_article_province`; không âm thầm chọn một bên.
6. Nếu không mở được trang hoặc không đọc được nhãn, giữ kết quả từ RSS,
   lưu trạng thái để biết nguyên nhân. Không đoán địa phương.

Mỗi URL chỉ mở một lần trong một batch; có khoảng nghỉ một giây giữa các URL.
Không tải trang của nguồn khác; chỉ dùng HTTPS và các URL/redirect thuộc
`vnexpress.net` hoặc `www.vnexpress.net`.

### Kết quả kiểm tra thực tế ngày 04/11/2026

Đã sao lưu bài trích xuất cũ (lúc đó nằm trong `data/gold/accidents/`) vào
`data/backups/before_vnexpress_dateline_20261104_224943/`
rồi chạy lại riêng bước 4. Ba bài trước đây thiếu tỉnh đã có kết quả:

| Bài | Nhãn trên trang | Giá trị `province` trong Silver |
|---|---|---|
| Tai nạn liên hoàn trên đường Hồ Chí Minh, đoạn A Lưới | TP Huế | Huế |
| Xe container tông người đi bộ thể dục | Nghệ An | Nghệ An |
| Xe ben gây tai nạn liên hoàn trên cầu Nhật Tân | Hà Nội | Hà Nội |

Kết quả nằm trong `data/silver/accidents/vnexpress.parquet`. Các thông tin khác
vẫn có thể thiếu: bài cầu Nhật Tân còn cờ `missing_incident_details`; bổ sung
tỉnh không có nghĩa tự xác nhận mọi trường đã đầy đủ.

Đã thêm 13 test trong `tests/test_vnexpress_location.py`; toàn bộ 94 test đạt.
Test mạng dùng trang mẫu và phản hồi giả để chạy ổn định; ba URL thật được chạy
kiểm chứng riêng bằng bước 4.

### Quan hệ với phần 3 và dữ liệu đã lưu

Thay đổi này nằm ở cấu hình và code trích xuất **phần 2**, không sửa code trong
`src/events/`. Silver vẫn có trường `province` như trước để phần 3 đọc.

Sau đó phần 3 đã được bổ sung cách xét lại bài chưa có sự kiện. Khi chạy
`python -m main --step=5`, thông tin mới từ Silver được cập nhật cho những bài
này rồi đem đi tìm/so khớp sự kiện. Bài đã được gán sự kiện vẫn giữ
liên kết với cùng vụ; nếu Silver thay đổi, nội dung bài và thông tin vụ được cập
nhật tự động, có lưu bản cũ để tra lại. Không còn chặn bằng `changed_input`.

Đã chạy lại trên database có sẵn và giữ nguyên hai sự kiện cũ: thêm hai sự kiện
ở Huế, Nghệ An; bài cầu Nhật Tân có tỉnh Hà Nội nhưng còn thiếu chi tiết tai nạn
nên vẫn chờ. Không cần xóa hoặc tạo lại database. Xem
[kết quả cập nhật và bản sao lưu](event_database_guide.md).
