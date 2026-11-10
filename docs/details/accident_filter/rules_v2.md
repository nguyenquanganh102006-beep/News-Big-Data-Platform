# Bộ lọc tai nạn rules-v2 — 10/11/2026

## Thay đổi

- Bổ sung cách diễn đạt: tai nạn giữa các xe, tai nạn đối đầu, bị/gặp tai nạn,
  xe mất lái, lao/rơi xuống ruộng, kênh, sông, vực; nhận cả máy cày/rơ-moóc đang
  qua cầu và bài theo dõi trực tiếp sự cố đó. Không bắt buộc có thương vong.
- Bổ sung động từ đụng, húc, đâm trực diện; kiểm tra ranh giới từ để không nhận
  nhầm “bình tông”, “bê tông” hay “cán bộ”.
- Lấy đoạn mô tả chính trong `<p>` và bỏ danh sách link liên quan, script/style.
  Với plain text chỉ dùng câu lead để hạn chế nhiễu từ tiêu đề bài khác nối đuôi.
  Giữ nội dung link nếu đó là wrapper của mô tả chính; không xóa mọi anchor.
- Không cắt lead tại viết tắt TP., QL., Q., P.; giải mã HTML entity và chuẩn hóa
  Unicode trước so khớp.
- Phân biệt sự cố thật với tư vấn, thống kê, diễn tập, giả định, nguy cơ và suýt
  va chạm. “Suýt chết” sau một va chạm thật không làm bài bị loại.
- Vụ tàu/thuyền cháy, va chạm, chìm, mắc cạn; cháy xe không kèm va chạm; vật rơi
  đè xe chưa rõ trạng thái lưu thông: giữ `uncertain` để review. Tai nạn lao động
  hoặc cháy gara không tự được coi là tai nạn đường bộ.

## Dữ liệu rà soát

Quét 705 URL khác nhau từ Bronze có sẵn và lần crawl thử ngày 10/11/2026, đủ 7
nguồn. Rà soát kỹ tiêu đề và mô tả RSS của 116 ứng viên có dấu hiệu tai nạn;
quét bổ sung các diễn đạt đụng/húc/mất phanh/rơi/ngã/đè ngoài nhóm này.

Đây là **rà soát phát triển do trợ lý thực hiện**, không phải nhãn chuẩn được
người kiểm duyệt độc lập xác nhận. Không dùng mức khớp trên nhóm đã xây luật để
khẳng định recall/precision trên báo mới. Không đọc đủ toàn văn 705 bài và không
cam kết không còn bỏ sót. Tiêu chí phạm vi: [criteria.md](criteria.md).

Kết quả chạy rules-v2 trên 705 bài: 46 accident, 16 uncertain, 643 not_accident.
Đây là nhãn dự đoán, không phải số vụ tai nạn và không phải ground truth.

Riêng 160 bài mới của 3 nguồn downstream: **2 accident, 6 uncertain, 152
not_accident**. Hai bài accident là vụ xe bán tải/đầu kéo tại Lâm Đồng và vụ máy
cày/rơ-moóc qua cầu rơi xuống kênh ở Tây Ninh. Bộ lọc cũ bỏ cả hai khỏi tập
accident. Một bài cây đè ôtô được giữ uncertain vì chưa xác định trạng thái lưu
thông; không ép vào nhãn tai nạn đường bộ.

## Kiểm tra sau lọc

Chạy lại filter → extraction → canonical trên 320 bài mới + lịch sử của 3 nguồn:
8 bài accident đi vào extraction, 1 canonical event và 7 matching review.
Lọc đúng không đảm bảo extraction đủ địa điểm hoặc matching tạo được sự kiện.

Replay toàn bộ 320 bài qua producer → Memurai → consumer trên database mới:
8 bài tai nạn (1 event, 7 review), 7 uncertain, 305 not_accident; queue,
processing và dead đều hết, không lỗi producer/consumer. Dùng Memurai tương thích
Redis; không coi đây là kiểm chứng Docker Redis.

Bằng chứng:

- `data_artifacts/diagnostics/filter_rules_v2_review/`: dự đoán đủ 705 bài, review ứng viên,
  dự đoán 160 bài mới và summary; nhãn review có ghi nguồn là trợ lý.
- `data_artifacts/diagnostics/e2e_20261110_211832/filter_v2_pipeline.log`.
- `data_artifacts/diagnostics/e2e_20261110_211832/streaming_rules_v2_final_result.json`.

## Chạy lại dữ liệu

```powershell
.venv/Scripts/python.exe -m main --step 3
.venv/Scripts/python.exe -m main --step 4
.venv/Scripts/python.exe -m batch.run
```

Lệnh trên cập nhật dữ liệu thật tại đường dẫn mặc định. Kết quả kiểm chứng ở trên
chạy trong bản sao riêng để giữ nguyên dữ liệu hiện có. Bốn nguồn ngoài VnExpress,
VietnamPlus, Tuổi Trẻ mới được rà soát classifier trên Bronze; chưa bổ sung
preprocessor/extractor riêng cho chúng.

Không xóa `uncertain.parquet`: đây là hàng chờ review. Với streaming, receipt
đã xử lý không tự chạy lại sau khi đổi rule; muốn tái phân loại cần replay vào
database/queue riêng hoặc xây cơ chế reprocess có phiên bản. Không xóa receipt
trong database đang chạy để ép replay.

Đánh giá độc lập vẫn dùng dữ liệu người kiểm duyệt theo
[hướng dẫn evaluate](rules_v1.md); công cụ nhận cả `description_text` hoặc
`description`, không tự tạo nhãn chuẩn.
