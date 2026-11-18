# Rà soát trích xuất thông tin trên 322 + 35 bài

Ngày thực hiện: 17/11/2026. Phiên bản mới: `rules-v3-body-evidence-v1`.

## Dữ liệu và phạm vi kiểm chứng

- Chạy trước/sau trên cùng **357 bài**, gồm 322 `accident`, 35 `uncertain`, từ kết quả rà soát bộ lọc. Giữ nguyên nhãn phạm vi.
- Bản đầu vào đóng băng: `data_artifacts/extraction_review_20261117/input_357.parquet`.
- SHA256: `2f1d4a05f539b6a7fc0ea623d6ec9df2e18c754cc86b9c9d476fae1b1a36eae8`.
- Cả 357 kết quả được kiểm tra tự động về khóa bài, nhãn, nội dung gốc, số âm, mâu thuẫn và quy tắc bản tin nhiều vụ.
- Đối chiếu trực tiếp các trích đoạn nguồn ở 36 bài; lập bộ tham chiếu **38 trường ở 24 bài** có bằng chứng rõ. Đây là tập hồi quy chọn theo lỗi, không phải mẫu ngẫu nhiên để tính độ chính xác chung. Không tuyên bố đã đọc và xác nhận mọi trường của cả 357 bài.
- **132 bài thiếu thân bài**. Không tải bổ sung hay gọi mạng trong phép so sánh này; không sử dụng dateline VnExpress qua mạng.

## Lỗi phát hiện và thay đổi

1. Bản cũ chỉ dùng tiêu đề, mô tả; `content` có sẵn bị bỏ qua. Bản mới đọc từng đoạn thân bài, lưu câu bằng chứng trong `evidence_json` (`*_body_context`). Batch và streaming cùng dùng `extract_frame`, nên cùng nhận cách xử lý mới.
2. Thân bài có thể dính đoạn giới thiệu bài khác. Cắt phần đuôi có dấu hiệu `TTO -`, `Đọc thêm`, `Xem thêm`, `Tin liên quan`, `Bài liên quan`; bỏ script/style/aside/nav. Việc nhận diện này không bao phủ mọi cách chèn bài liên quan.
3. Bản tin tổng hợp nhiều vụ không có một số thương vong chung có ý nghĩa. Nhận diện thêm các tiêu đề tổng hợp, để trống hai trường thương vong và gắn `multiple_events_in_article`; chưa tách thành từng vụ con.
4. Không cộng số thương vong lặp lại giữa tiêu đề, mô tả và các đoạn. Khi các nguồn cho giá trị khác nhau hoặc có nhóm người chưa rõ quan hệ, để trống và gắn cờ mâu thuẫn; không tự chọn số lớn nhất.
5. Bổ sung nhận diện người bị nạn như “một phụ nữ”, “nữ sinh”, “cô giáo”, “cụ ông”, và nhóm “2 người đi xe máy”, “bốn thanh thiếu niên”. Giữ quy tắc không biến khoảng/ít nhất/thương vong chung thành số chết hoặc bị thương chính xác.
6. Bổ sung `tàu hàng`; tên hành chính có dấu nháy như `M'Đrắk` không còn bị cắt thành `M`.
7. Chỉ bổ sung địa điểm từ đoạn có ngữ cảnh hiện trường; không dùng mọi tỉnh/thành trong thân bài. Hạn chế lấy xe cứu hộ/phương tiện điều tiết thành xe liên quan vụ tai nạn. Các địa điểm/nhóm người còn mâu thuẫn được giữ để kiểm tra.
8. Cả 35 bài `uncertain` vẫn giữ nguyên nhãn và có `upstream_scope_uncertain`; bài thiếu thân bài có `missing_body`.

## Kết quả trước/sau

Các số dưới đây là **số bài có trường được điền**, không phải số trường đúng và không phải số vụ tai nạn:

| Trường | Trước | Sau |
|---|---:|---:|
| Tỉnh/thành | 192 | 225 |
| Quận/huyện/thị xã | 0 | 6 |
| Xã/phường/thị trấn | 70 | 155 |
| Số tử vong | 101 | 113 |
| Số bị thương | 59 | 80 |
| Loại phương tiện | 314 | 335 |
| Dạng tai nạn | 246 | 295 |

203/357 bài thay đổi ít nhất một trường. Bộ tham chiếu 24 bài: bản cũ khớp **21/38**, bản mới khớp **38/38** trường được kiểm tra. Kết quả này chỉ chứng minh sửa được các ca tham chiếu, không chứng minh độ chính xác 100% trên toàn bộ dữ liệu.

Ví dụ đã đối chiếu:

- Xe tải tông lan can cầu Rạch Miễu: lấy đúng Đồng Tháp/phường Thới Sơn, 1 tử vong/2 bị thương; không lấy 2 người chết của bài liên quan ở cuối.
- Tai nạn đường Xuân Thủy: nhận cô gái tử vong là 1, bổ sung xe buýt từ danh sách phương tiện trong thân bài.
- Bản tin ngày 5/2 và 28/1: không gán thương vong của một vụ cho cả bản tin.
- Lật xe khách tại Gia Lai: bổ sung tỉnh/thành và số bị thương từ thân bài.
- Xã `M'Đrắk`: giữ đúng tên thay vì một ký tự.

## Hạn chế còn lại

- Chưa có nhãn chuẩn đủ mọi trường cho toàn bộ 357 bài. Không thể cam kết không còn lỗi hay báo precision/recall tổng thể.
- Trích xuất bằng luật còn bỏ sót tên người có chữ viết tắt, tuổi hoặc hành động chen giữa chủ thể và hậu quả; số thương vong có nhiều nhóm, cập nhật qua thời gian có thể phải để trống.
- Những đoạn chèn bài liên quan không có dấu hiệu rõ, trích lời nạn nhân, quê quán, cơ quan thụ lý hoặc tên đường có tỉnh/thành vẫn có thể gây nhiễu. Cần xem `evidence_json` trước khi duyệt các trường nhạy cảm.
- Bản tin nhiều vụ cần bước tách vụ nếu muốn đưa từng vụ vào Gold. Không cộng cả bài thành một sự kiện.
- Không thay đổi dữ liệu Bronze gốc, không xuất bản kết quả thử nghiệm này vào Gold/dashboard. File `after.parquet` là đầu ra audit riêng.

## File kết quả và chạy lại

Tại `data_artifacts/extraction_review_20261117/`:

- `baseline.parquet`, `baseline.csv`, `baseline_summary.json`: bản trước sửa.
- `after.parquet`, `after.csv`, `after_summary.json`: kết quả sau sửa, có bằng chứng và cờ review.
- `review_ledger_357.csv`: từng bài, các trường thay đổi, cờ cần kiểm tra; phân biệt kiểm tra tự động và tham chiếu đối chiếu trích đoạn.
- `targeted_references.json`, `evaluation.json`: giá trị tham chiếu và kết quả đối chiếu.

```powershell
$env:PYTHONPATH = 'src'
$env:PYTHONUTF8 = '1'
.venv/Scripts/python.exe scripts/audit_extraction_quality.py after
.venv/Scripts/python.exe scripts/evaluate_extraction_review.py
.venv/Scripts/python.exe -m unittest discover -s tests
```

Các kiểm thử hồi quy mới nằm trong `tests/test_extraction_body.py`: bổ sung từ thân bài, loại đuôi bài liên quan, số lặp/mâu thuẫn, bản tin nhiều vụ, xe cứu hộ, số 0 của nhóm con, tên hành chính, nhãn chưa chắc chắn và dữ liệu thiếu thân bài.

Kết quả kiểm thử toàn bộ: **183 tests, thành công, 5 tests được skip** theo điều kiện của bộ kiểm thử; chạy với `PYTHONUTF8=1` để ghi báo cáo tiếng Việt đúng trên Windows.
