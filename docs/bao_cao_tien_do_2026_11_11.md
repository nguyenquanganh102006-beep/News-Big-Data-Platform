# Báo cáo tiến độ hệ thống thu thập và phân tích tin tai nạn giao thông

**Ngày báo cáo:** 11/11/2026 (giờ Việt Nam)  
**Nhánh phát triển:** `task/43-44`  
**Commit mã nguồn gần nhất khi lập báo cáo:** `3219155`  
**Snapshot dashboard dùng làm căn cứ:** `20261111_082837_4ab14093`

## 1. Mục tiêu và phạm vi

Hệ thống thu thập tin từ 7 nguồn báo, lưu lịch sử bài viết, phát hiện bài trùng nội dung, lọc bài tai nạn giao thông đường bộ, trích xuất thông tin và gom các bài cùng vụ thành sự kiện. Kết quả được lưu trong DuckDB và trình bày trên dashboard.

Các nguồn hiện có: VnExpress, VietnamPlus, Tuổi Trẻ, Dân Trí, Thanh Niên, Báo Xây dựng và Tiền Phong.

Báo cáo phản ánh mã nguồn và kết quả vận hành đã quan sát trong môi trường local. Trạng thái “đã triển khai” thể hiện chức năng đã có trong code; không đồng nghĩa đã được đánh giá độ chính xác đầy đủ trên tập dữ liệu có nhãn.

## 2. Tiến độ các hạng mục

| Hạng mục | Trạng thái | Kết quả hiện tại |
|---|---|---|
| Thu thập RSS | Đã triển khai, đã chạy thực tế | Crawl đủ 7 nguồn, lưu snapshot Bronze |
| Tiền xử lý và tích lũy Silver | Đã triển khai | Làm sạch dữ liệu, chuẩn hóa URL, lưu lịch sử theo bài |
| Phát hiện bài trùng nội dung | Đã triển khai | TF-IDF và cosine similarity; đánh dấu bản trùng và loại khỏi luồng xử lý tiếp |
| Lọc tai nạn | Đã triển khai, cần tiếp tục đánh giá | Phân loại `accident`, `uncertain`, `not_accident` theo phạm vi đường bộ |
| Trích xuất thông tin | Đã triển khai, còn thiếu dữ liệu ở một số bài | Địa điểm, phương tiện, diễn biến và thương vong |
| Matching và lưu Gold Giai đoạn 3 | Đã triển khai, đã chạy thực tế | Cập nhật database hiện có, lưu liên kết bài–sự kiện, review và lịch sử sửa bài |
| 4.1 Redis Queue | Đã triển khai, đã chạy với Redis/Memurai local | Producer, queue chính, processing, retry, dead-letter và ACK |
| 4.2 Streaming Consumer | Đã triển khai, đã thử một message thực tế | Xử lý từng bài, ghi provisional và receipt; crawler chưa tự đưa bài vào Redis |
| 4.3 Batch | Đã triển khai, đã chạy thực tế | Dựng lại canonical từ Silver đã trích xuất, kiểm tra và thay database khi thành công |
| Matching dùng chung cho các luồng | Đã tích hợp | Dùng `events.service.MatchingService` cho Giai đoạn 3, Batch và Streaming |
| Dashboard | Đã triển khai, đã publish snapshot | Tra cứu bài, sự kiện, review, thống kê thời gian và số bản ghi sau từng bước |
| Tự động hóa lịch chạy | Chưa thiết lập trong đợt công việc này | Các lần vận hành được thực hiện bằng lệnh hoặc nút làm mới dashboard |
| Dùng chung đầu vào Silver cho Batch và Streaming | Mới đề xuất | Chưa thay đổi kiến trúc theo đề xuất này |

## 3. Luồng xử lý đang triển khai

### 3.1. Luồng chính

```text
Crawl 7 nguồn
→ Bronze: snapshot bài RSS
→ Silver: làm sạch, chuẩn hóa URL và tích lũy lịch sử bài
→ Phát hiện trùng nội dung
→ Lọc phạm vi tai nạn
→ Trích xuất thông tin vào Silver accidents
→ Giai đoạn 3: matching và cập nhật Gold events
```

Lệnh `python -m main --step 0` chạy toàn bộ luồng. Bước 4 tạo Silver đã trích xuất; bước 5 cập nhật `data/gold/events/accident_events.duckdb`. Bài đã gán và không đổi được bỏ qua; bài thay đổi được cập nhật và tính lại thông tin sự kiện liên quan.

### 3.2. Batch

```text
Silver accidents của 7 nguồn
→ Kiểm tra schema, định danh và tính ổn định của đầu vào
→ Sắp xếp theo ngày đăng, chuẩn bị mô hình văn bản
→ Tạo database canonical tạm mới
→ Ghép bài vào event / tạo event / lưu review
→ Tổng hợp thông tin các event
→ Kiểm tra số lượng → COMMIT → CHECKPOINT
→ Đóng database và thay canonical cũ
```

Batch runner nhận bài đã trích xuất, dựng lại toàn bộ kho canonical mỗi lần chạy. Đầu ra mặc định là `data/gold/batch/canonical.duckdb`. Nếu lần dựng mới thất bại, bản canonical hiện có được giữ lại.

Khi publish dashboard, hệ thống còn tổng hợp lịch sử Bronze, tạo catalog theo URL, đánh dấu trùng nội dung, phân loại bài và lấy dữ liệu trích xuất đã có trước khi gọi Batch. Snapshot dashboard được công bố sau khi xử lý thành công.

### 3.3. Streaming

```text
Bài RSS → Producer → Redis
→ Consumer nhận từng message
→ Kiểm tra receipt chống xử lý lặp
→ Làm sạch → Lọc tai nạn → Trích xuất
→ Ghép bài vào event / tạo event / lưu review
→ Ghi Gold provisional và receipt trong cùng transaction
→ COMMIT → ACK → Chờ message tiếp theo
```

Consumer chạy liên tục khi được khởi động. Đầu ra mặc định là `data/gold/streaming/provisional.duckdb`. Lỗi tạm được thử lại; message không hợp lệ hoặc hết số lần thử được chuyển vào dead-letter.

Producer hiện có interface và CLI riêng. Crawler chưa gọi producer tự động, vì vậy chạy luồng chính chưa đưa các bài vừa crawl vào Redis.

## 4. So sánh Batch và Streaming

| Nội dung | Batch | Streaming |
|---|---|---|
| Đầu vào | Toàn bộ Silver đã trích xuất | Một bài RSS từ Redis |
| Làm sạch, lọc, trích xuất | Đã thực hiện ở các bước trước | Thực hiện trong consumer |
| Thứ tự | Theo ngày đăng | Theo thứ tự nhận message |
| Trạng thái ban đầu | Database canonical tạm rỗng | Kho provisional đã tích lũy |
| Cửa sổ ghép thông thường | ±48 giờ theo giờ đăng | 24 giờ về trước theo giờ đăng |
| Cách ghi | Dựng lại toàn bộ và thay bản cũ | Cập nhật dần sau từng bài |
| Vai trò | Tính lại kết quả trên lịch sử đầu vào | Có kết quả khi bài mới được gửi đến |

Các luồng dùng chung logic matching với bằng chứng địa điểm, phương tiện, thời gian, dấu hiệu nhận diện và độ tương đồng văn bản. Mặc định có embedding đa ngôn ngữ. Matcher còn có nhánh xét tin theo dõi ngoài cửa sổ thông thường với điều kiện bằng chứng riêng.

Kho Giai đoạn 3, canonical và provisional là ba database độc lập, chưa tự đồng bộ hoặc hợp nhất. Cửa sổ 48 giờ/24 giờ là phạm vi tìm ứng viên, không phải chu kỳ chạy.

## 5. Kết quả vận hành gần nhất

Đã thực hiện `python -m main --step 0`, sau đó `python -m dashboard.publish`. Cả hai lệnh hoàn tất với mã thoát 0.

| Bước / chỉ số | Số lượng |
|---|---:|
| Nguồn RSS | 7 |
| Snapshot Bronze | 42 |
| Dòng dữ liệu Bronze | 2.460 |
| Bài duy nhất theo nguồn và URL trong catalog lịch sử | 735 |
| Bài trùng nội dung được đánh dấu | 1 |
| Bài còn lại sau khử trùng nội dung | 734 |
| Bài được phân loại tai nạn | 47 |
| Bài cần xem xét ở bước lọc | 2 |
| Bài ngoài nhóm tai nạn | 685 |
| Bài đã trích xuất, đưa vào Batch | 47 |
| Event trong Batch canonical | 24 |
| Bài đã gán event trong Batch | 28 |
| Bài chờ review matching trong Batch | 19 |

### Số bản ghi sau từng bước trên dashboard

Bảng dưới đây ghi lại số liệu của tab **Luồng dữ liệu** trong ảnh dashboard, trên snapshot hiện hành và toàn bộ lịch sử:

| Bước | Số bản ghi | Chi tiết |
|---|---:|---|
| Bronze · snapshot crawl | 2.460 | 42 snapshot · 7 nguồn; có thể lặp bài qua các lần crawl |
| Silver · gộp theo URL | 735 | Bài duy nhất theo nguồn và URL chuẩn hóa |
| Sau phát hiện trùng nội dung | 734 | Đầu vào 735 · đánh dấu trùng 1 |
| Sau lọc phạm vi tai nạn | 734 | Tai nạn 47 · cần xem xét 2 · loại 685 |
| Sau trích xuất | 47 | Bài tai nạn có dữ liệu trích xuất · 7 nguồn |
| Gold · bài đưa vào matching | 47 | Đã lưu 47 bài trong kho canonical |
| Gold · bài gán vào sự kiện | 28 | 24 sự kiện · chưa gán 19 bài |
| Gold · chờ review matching | 19 | Các bài matching chưa tự động gán vào sự kiện |

Ở bước lọc, 734 là tổng số bài đã được phân loại vào ba nhóm; 47 bài thuộc nhóm tai nạn được chuyển sang trích xuất. Kết quả matching được đối chiếu bằng phép tính **47 bài đầu vào = 28 bài đã gán sự kiện + 19 bài chờ review**. Có 24 sự kiện vì nhiều bài có thể cùng đưa tin về một vụ.

Bronze đếm dòng trong các snapshot, có thể lặp cùng bài qua nhiều lần crawl. Catalog lịch sử gộp theo nguồn và URL chuẩn hóa. Một bài báo và một vụ tai nạn là hai đơn vị đếm khác nhau.

So với snapshot trước, catalog tăng từ 715 lên 735 bài, tương ứng **20 bài mới theo URL**. Trong đó có 2 bài được phân loại tai nạn và 18 bài ngoài nhóm tai nạn.

Database Giai đoạn 3 hiện có 47 bài, 26 event, 28 liên kết bài–event và 19 review đang chờ. Số event khác Batch (24) phản ánh hai kho có trạng thái và cách cập nhật khác nhau; cần đối chiếu nếu yêu cầu kết quả hai kho phải đồng nhất.

Streaming đã được chạy thử qua Redis thực với một bài từ Silver chuyển thành message đầu vào. Consumer trả `new_event`, ghi receipt và ACK thành công; queue chính, processing và dead-letter đều bằng 0 sau lượt thử đó. Kết quả này chỉ chứng minh lượt xử lý quan sát được, chưa chứng minh crawler và Streaming đã tích hợp tự động.

## 6. Phân tích 19 bài chờ review matching

Đã đọc trực tiếp các review trong kho canonical của snapshot hiện hành:

| Lý do | Số bài có lý do này | Ý nghĩa |
|---|---:|---|
| `province_missing` | 13 | Trường tỉnh/thành chưa trích xuất được, ngăn ghép tự động |
| `missing_incident_details` | 4 | Chưa nhận diện được chi tiết diễn biến cần thiết |
| `ambiguous_or_insufficient_match` | 4 | Có ứng viên nhưng thiếu bằng chứng hoặc điểm ghép chưa đủ |

Hai bài có đồng thời hai lý do, nên tổng số bài duy nhất vẫn là 19. Đây là review matching, khác nhóm 2 bài chưa chắc chắn ở bước lọc tai nạn.

Một số nhóm có dấu hiệu cùng đưa tin về một vụ: ba bài người đi bộ qua cao tốc Pháp Vân–Cầu Giẽ; hai bài tai nạn cầu Nhật Tân; hai bài cầu sắt gãy; hai bài người giao cơm tử vong; hai bài nữ sinh va chạm với rơ-moóc. Các nhóm này mới được nhận diện qua tiêu đề, thời gian và dữ liệu đã lưu, chưa được xác minh để tự gộp.

Một số tiêu đề có địa danh nhưng trường `province` vẫn trống, cho thấy cần cải thiện trích xuất và chuẩn hóa địa điểm. Bốn review do matching có điểm ứng viên cao nhất khoảng 0,585; 0,461; 0,502 và 0,297, đều dưới ngưỡng tự ghép mặc định 0,75 và còn thiếu bằng chứng hỗ trợ.

## 7. Dashboard và quản lý mã nguồn

Dashboard có các tab Tổng quan, Thống kê thời gian, Luồng dữ liệu, Bài báo, Sự kiện và Chờ review. Thống kê đầu trang thể hiện toàn bộ lịch sử và riêng ngày hiện tại theo giờ Việt Nam. Tab Luồng dữ liệu đọc số liệu theo bước từ manifest của snapshot.

Snapshot được publish hiện chứa kho canonical Batch. Nút “Làm mới dữ liệu” dựng snapshot từ dữ liệu đã có, không tự crawl bài mới. Cần chạy luồng thu thập trước để bổ sung đầu vào.

Các thay đổi mã nguồn gần nhất đã được push lên `task/43-44`, gồm tích hợp matching dùng chung và tab thống kê pipeline. Các lệnh vận hành tạo dữ liệu local; báo cáo không khẳng định dữ liệu local được đưa lên GitHub.

## 8. Công việc tiếp theo

| Ưu tiên | Công việc | Kết quả cần đạt |
|---|---|---|
| 1 | Thống nhất đầu vào xử lý bài cho Streaming và Batch | Dùng chung kết quả làm sạch, khử trùng, lọc và trích xuất |
| 1 | Nối crawler với đường xử lý Streaming | Bài mới được tự đưa vào queue sau khi lưu bền dữ liệu |
| 1 | Cải thiện trích xuất địa điểm và diễn biến | Giảm review do thiếu tỉnh/thành và chi tiết tai nạn |
| 2 | Xác minh các nhóm bài trong 19 review | Có nhãn cùng vụ/khác vụ làm căn cứ đánh giá matcher |
| 2 | Xử lý bài cập nhật cùng `article_key` trong Streaming | Có chính sách phiên bản; receipt hiện khiến cùng key được bỏ qua |
| 2 | Chốt quan hệ giữa ba kho Gold | Xác định nguồn kết quả chính thức và cách đối chiếu/hợp nhất |
| 3 | Thiết lập lịch chạy và giám sát | Crawl định kỳ, consumer liên tục, Batch và publish có trạng thái rõ ràng |
| 3 | Đánh giá chất lượng bằng tập có nhãn | Đo độ chính xác lọc, trích xuất và ghép sự kiện |

Lịch từng được đề xuất để thảo luận: crawl mỗi 10 phút, consumer chạy liên tục, Batch mỗi giờ và publish sau Batch. Lịch này chưa được thiết lập tự động trong đợt công việc được báo cáo.

Kiến trúc dùng chung Silver đã trích xuất là hướng đề xuất tiếp theo. Khi triển khai, cần giải quyết thứ tự ghi Silver và gửi queue, chống gửi lặp, xử lý phiên bản bài thay đổi và cơ chế chạy lại khi logic trích xuất đổi. Các phần này hiện chưa được triển khai theo đề xuất mới.

## 9. Tài liệu và căn cứ

- [Luồng tổng thể](flow.md).
- [Streaming](details/streaming.md).
- [Batch và matching](details/batch_matching.md).
- [Matching theo bằng chứng](details/event_matching_v2.md).
- [Database sự kiện](details/event_database_guide.md).
- [Dashboard](details/dashboard.md).
- Manifest snapshot local: `data_artifacts/dashboard_snapshots/20261111_082837_4ab14093/manifest.json`.

Các kết quả chạy thực tế và truy vấn database trong báo cáo chưa thay thế đánh giá toàn diện hoặc kiểm thử tải. Không có tỷ lệ hoàn thành phần trăm hoặc chỉ số độ chính xác được suy ra từ các lượt chạy này.
