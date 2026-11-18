# Rà soát bộ lọc bài tai nạn giao thông — 17/11/2026

## Phạm vi và cách rà soát

Người dùng xác nhận giữ **tin tường thuật vụ tai nạn đường bộ**, loại tin điều tra/khởi tố, xét xử, thăm hỏi và cập nhật thuần túy sau vụ việc. Tin thống kê, tư vấn luật, giới thiệu sản phẩm xe, thử nghiệm an toàn, tai nạn ngoài đường bộ không thuộc nhóm sự kiện cần giữ. Va chạm giữa tàu và phương tiện đường bộ tại đường ngang vẫn thuộc phạm vi. Tin cứu nạn tại hiện trường có mô tả vụ tai nạn cụ thể được giữ; bài cập nhật điều trị hoặc thăm hỏi được loại.

Đã quét 20.745 bài sau khử trùng nội dung, từ 20.755 URL bài trong bộ dữ liệu. Kiểm tra thêm tiêu đề 10 bản trùng đã bị khử trùng; không thấy tin tường thuật tai nạn trong nhóm này. Đây là rà soát trên dữ liệu đã lưu, không phải crawl hoặc xác minh lại toàn bộ trang gốc.

Đã đọc toàn bộ tiêu đề của 325 bài được bộ lọc cũ nhận, đọc thêm mô tả/nội dung các ca nghi ngờ. Bộ tìm ứng viên độc lập rà cả tiêu đề, mô tả và nội dung, tìm được 206 ứng viên theo tiêu đề, 143 theo mô tả và 3.187 bài chỉ có tín hiệu trong thân bài. Các ứng viên chưa được coi là nhãn đúng: phần lớn là nhắc lại tai nạn trong bài hạ tầng, chính sách hoặc tin ngoài phạm vi. Một lượt sàng lọc tín hiệu mạnh trong phần mở đầu thân bài tiếp tục thu hẹp để kiểm tra các ca có khả năng bỏ sót.

Tập rà soát có nhãn tham chiếu gồm 422 bài: 325 bài cũ và 97 trường hợp bổ sung. Nhãn được lập từ việc đọc tiêu đề, mô tả và phần nội dung cần thiết; đây là nhãn rà soát của đợt này, cần kiểm duyệt độc lập trước khi dùng làm chuẩn đánh giá chính thức. Các trường hợp ranh giới có nhãn `uncertain`.

## Kết quả rà soát

### Nhóm 325 bài cũ

| Kết luận rà soát | Số bài |
|---|---:|
| Tin tường thuật tai nạn đường bộ | 257 |
| Ngoài phạm vi đã chốt | 65 |
| Ranh giới/chưa chốt được chủ đề chính | 3 |

Một số ví dụ ngoài phạm vi:

- **Honda sắp có xe bán tải ‘đối đầu’ Ford Ranger?**: cạnh tranh sản phẩm, không phải hai xe đâm nhau.
- **Giải mã nút có biểu tượng xe va chạm kèm ngôi sao trên ô tô**: hướng dẫn tính năng.
- **Hàng loạt xe SUV bị chê trong việc bảo vệ cổ hành khách...**: thử nghiệm độ an toàn xe.
- **Khi robot tung hoành chiến địa...** và bài xe tăng của Israel: bối cảnh quân sự.
- **39 người đã thiệt mạng trong vụ tai nạn đường sắt tại Tây Ban Nha**: đường sắt thuần túy.
- **Toàn quốc xảy ra 381 vụ tai nạn giao thông trong 9 ngày nghỉ Tết**: thống kê nhiều vụ.
- **Container rơi xuống kênh Chợ Gạo**: đọc nội dung xác nhận container rơi từ sà lan, thuộc đường thủy.
- Tin khởi tố, tạm giữ, tuyên án, thăm hỏi, hỗ trợ tiền và cập nhật điều trị: không phải tin tường thuật theo phạm vi người dùng xác nhận.

Danh sách có tiêu đề, link và lý do: [65 bài ngoài phạm vi trong nhóm 325](../data_artifacts/filter_review_20261117/confirmed_non_accidents_original_325.csv). Toàn bộ kết quả đối chiếu 325 bài: [review_original_325.csv](../data_artifacts/filter_review_20261117/review_original_325.csv).

### Các bài bị bỏ sót

Đã xác nhận **57 tin tai nạn/sự cố giao thông đường bộ** trong các nhóm cũ `not_accident` và `uncertain`. Bộ lọc sửa bắt lại được các ca này trên tập rà soát.

Các dạng bỏ sót đã tìm được:

- Xe máy **bị cuốn vào gầm**, **hất văng**, **quật ngã**; xe **đấu đầu**, **đâm vỡ kính**, **đâm dồn toa**, **lật nhiều vòng**.
- Tin nêu rõ tai nạn giao thông và thương vong nhưng không ghi loại phương tiện trong tiêu đề.
- Xe đạp, người đi bộ, va chạm với động vật khi đang tham gia giao thông.
- Xe buýt va chạm tàu hỏa: bộ lọc cũ hiểu nhầm chữ “tàu” là đường thủy hoặc loại toàn bộ tin tàu.
- Xe cháy trên cầu, ven đường, khi dừng tại trạm xăng; cây/vữa/vật rơi trúng phương tiện trên đường.
- Người/xe bị nước cuốn, ngã trên đường; hàng hóa rơi từ xe đang lưu thông. Các sự cố này được giữ theo hướng ưu tiên không bỏ sót sự cố đường bộ.
- Diễn biến va chạm nằm ở câu thứ hai của RSS hoặc phần mở đầu nội dung, thay vì câu đầu của mô tả.
- Bản tin tổng hợp vừa có chuyện ngoài phạm vi vừa tường thuật vụ tai nạn đường bộ. Bài được giữ, số bài không được hiểu là số vụ; cần xử lý nhiều vụ riêng ở giai đoạn trích xuất/matching.

Danh sách có link và bằng chứng: [57 bài bị bỏ sót đã xác nhận](../data_artifacts/filter_review_20261117/confirmed_missed_accidents.csv).

## Thay đổi trong code

Phiên bản mới: **`rules-v4-road-recall`**.

1. Kiểm tra chủ đề chính trước khi nhận một từ khóa va chạm: phân biệt sản phẩm xe, luật, thống kê, y tế, tin pháp lý và tường thuật sự kiện.
2. Bổ sung các cách diễn đạt va chạm và phương tiện; không đòi hỏi tin phải có người chết/bị thương.
3. Phân biệt phương tiện đường bộ va chạm tàu với tai nạn đường sắt/đường thủy thuần túy.
4. Xử lý “suýt bị ô tô tông” và tình huống tránh được va chạm; vẫn giữ tai nạn thật nếu chỉ “suýt chết”.
5. Đọc thêm mô tả RSS đã bỏ phần tin liên quan và phần mở đầu thân bài, có giới hạn độ dài. Tín hiệu thân bài được xét theo câu có phương tiện/nhân vật liên quan, tránh ghép tiêu đề ô tô với từ “đối đầu” trong đoạn chính trị không liên quan.
6. Truyền `content` thống nhất qua lọc Silver, Streaming, dashboard publisher và bộ đánh giá.
7. Các ca thiếu ngữ cảnh hoặc chủ đề tang thương/tường thuật chưa phân biệt được vẫn giữ `uncertain` để xem xét.

Mã phân loại không tra ID, URL hoặc danh sách bài đã rà. Nhãn tham chiếu chỉ được dùng trong công cụ đánh giá và báo cáo.

## Kết quả chạy trên toàn bộ đầu vào

| Nhóm | Bộ lọc cũ | Bộ lọc mới |
|---|---:|---:|
| Tai nạn | 325 | 318 |
| Cần xem xét | 79 | 33 |
| Ngoài nhóm tai nạn | 20.341 | 20.394 |
| Tổng | 20.745 | 20.745 |

Số cuối không tăng tương ứng số bài tìm lại được: bộ mới giữ 259 bài trong nhóm tai nạn cũ, bổ sung 59 bài từ hai nhóm khác, chuyển 65 bài cũ sang ngoài phạm vi và 1 bài cũ sang cần xem xét. Trong 59 bài được nhận thêm, 57 bài đã được xác nhận ở lượt rà này, 2 bài còn ở ranh giới chủ đề/ý định. Trong 318 dự báo dương tính có 314 bài được gán nhãn tham chiếu dương tính và 4 ca ranh giới được giữ để ưu tiên không bỏ sót.

Kết quả lọc đầy đủ, giữ nội dung và trường dữ liệu gốc: [classified_v4.parquet](../data_artifacts/filter_review_20261117/classified_v4.parquet). [Danh sách ưu tiên xem xét](../data_artifacts/filter_review_20261117/priority_review.csv) bao gồm cả các ca bộ lọc và nhãn rà soát còn chưa chắc chắn.

## Kiểm chứng và giới hạn

- Có kiểm tra hồi quy cho các nhóm bỏ sót, loại nhầm và các cách diễn đạt tương tự; kiểm tra truyền nội dung qua pipeline.
- Chỉ số trên tập rà có chủ đích được lưu trong [comparison.json](../data_artifacts/filter_review_20261117/comparison.json). Tập này được dùng để tìm lỗi và chỉnh quy tắc nên không phải tập kiểm định độc lập. Không được suy ra độ chính xác hoặc recall 100% trên toàn bộ hơn 20.000 bài từ các chỉ số này.
- Chưa đọc thủ công từng nội dung của 20.745 bài. Việc tìm ứng viên có thể bỏ sót cách diễn đạt chưa được dự liệu. Cần kiểm duyệt chéo và lấy mẫu ngẫu nhiên trong nhóm bị loại để đo chất lượng trên phân bố thật.
- Kết quả mới được xuất riêng trong đợt rà soát này. Silver/Gold vận hành và snapshot dashboard trước đó chưa được xuất bản lại; chúng vẫn là kết quả phiên bản cũ. Khi áp dụng cần chạy lại lọc, trích xuất và canonical Batch. Streaming cần kho replay mới hoặc cơ chế phiên bản receipt, vì receipt cũ đang bỏ qua bài đã xử lý.

Chạy lại việc rà soát và đánh giá:

```powershell
.venv/Scripts/python.exe scripts/audit_accident_filter.py
.venv/Scripts/python.exe scripts/evaluate_filter_review.py
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_accident_filter*.py"
```

Baseline bất biến và các CSV nằm trong `data_artifacts/filter_review_20261117/`; dữ liệu Bronze không bị sửa bởi công cụ rà soát.


## Cập nhật kiểm tra bổ sung

Rà lại phát hiện thêm 3 bài bỏ sót; kết quả hiện tại 321 tai nạn, 33 cần xem xét, 20.391 không phải tai nạn. Các số 318 ở phần trước thuộc lần rà trước. Xem [báo cáo bổ sung](ra_soat_bo_sung_20k_2026_11_17.md) để biết phạm vi kiểm tra và giới hạn.


## Cập nhật rà toàn bộ 20.745 bài

Đã hoàn tất sàng lọc toàn tập bằng 3 agent Luna max và agent chính; kết quả sau kiểm tra chéo: 322 tai nạn, 35 cần xem xét, 20.388 ngoài phạm vi. Xem [báo cáo toàn tập](ra_soat_toan_bo_20745_2026_11_17.md). Các số liệu ở phần trước là lịch sử các lượt rà, không phải kết quả cuối.
