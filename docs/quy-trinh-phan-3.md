# Quy trình hoạt động của Phần 3: Gom bài báo thành sự kiện

Phần 3 nhận các bài tai nạn đã được lọc và trích xuất thông tin ở Phần 2. Mục
tiêu là xác định bài nào nói về cùng một vụ tai nạn, rồi lưu kết quả để có thể
tra cứu số vụ và các bài liên quan.

```text
Bài tai nạn đã trích xuất
  → tìm sự kiện có thể liên quan (3.1)
  → so sánh và quyết định (3.2)
  → lưu sự kiện và liên kết bài báo (3.3)
```

## 1. Đầu vào

Phần 3 đọc các file bài tai nạn đã trích xuất trong `data/silver/accidents/`.
Thông tin đầu vào gồm tiêu đề, mô tả, ngày đăng, tỉnh/thành, địa điểm, phương
tiện và những thông tin khác mà Phần 2 trích xuất được. Ngày đăng là ngày bài
báo được xuất bản; hệ thống không tự coi đó là ngày tai nạn xảy ra.

## 2. Tìm sự kiện để đem ra so sánh — 3.1

Với mỗi bài, hệ thống tìm các sự kiện đã lưu ở cùng tỉnh/thành và có ngày đăng
gần nhau. Cửa sổ thông thường là trong vòng 48 giờ trước hoặc sau ngày đăng
của bài. Đây chỉ là bước rút gọn danh sách cần kiểm tra, chưa kết luận hai bài
cùng vụ.

Một số tin cập nhật có thể đăng muộn. Nếu bài có ngày xảy ra và địa điểm cụ thể
phù hợp với một vụ cũ, hệ thống có thể xem xét sự kiện trong phạm vi rộng hơn
(tối đa 7 ngày). Trường hợp này cần có các dấu hiệu cụ thể để tránh ghép chỉ vì
hai tin cùng tỉnh và cách nhau vài ngày.

## 3. So sánh và chọn kết quả — 3.2

Hệ thống tạo hồ sơ ngắn cho bài và sự kiện ứng viên, rồi đối chiếu các dấu hiệu:

- Nội dung tiêu đề và mô tả: embedding đa ngôn ngữ được bật mặc định, kết hợp
  với độ giống từ ngữ bằng TF-IDF.
- Địa điểm và ngày xảy ra, nếu có thông tin đáng tin cậy.
- Các dấu hiệu nhận diện vụ việc, chẳng hạn tên địa điểm cụ thể kết hợp với
  phương tiện hoặc thời gian.
- Loại phương tiện.

Các dấu hiệu được chấm điểm theo trọng số cấu hình. Độ giống câu chữ cao vẫn
chưa đủ để khẳng định cùng vụ: cần có thêm bằng chứng nhận diện vụ việc và
không được có mâu thuẫn rõ ràng về sự kiện. Khi có nhiều ứng viên gần nhau hoặc
thiếu thông tin, hệ thống chuyển bài sang chờ xem xét.

Kết quả có ba loại:

- **`matched`** — bài được liên kết với một sự kiện đã có.
- **`new_event`** — tạo sự kiện mới cho bài.
- **`needs_review`** — chưa đủ căn cứ để tự quyết định; bài được lưu chờ xem xét.

## 4. Lưu sự kiện và bài liên quan — 3.3

Sự kiện và các liên kết bài báo được lưu trong DuckDB ở `data/gold/events/`.
Mỗi bài được liên kết chính thức với tối đa một sự kiện. Các bài chờ xem xét
được giữ riêng, chưa tính vào một sự kiện đã xác nhận. Hệ thống cũng lưu điểm,
lý do quyết định và bằng chứng để có thể giải thích vì sao bài được ghép hoặc
được đưa vào hàng chờ.

Thông tin của sự kiện được tổng hợp từ các bài đã liên kết; hệ thống không cộng
thương vong giữa các bài cùng vụ. Các bản xuất Parquet được tạo trong
`data/gold/events/exports/` để tiện phân tích.

Khi chạy lại với dữ liệu đã xử lý, hệ thống giữ các liên kết hiện có thay vì
tạo lại sự kiện hoặc cộng lặp số liệu. Nếu thông tin của một bài đã liên kết
được cập nhật, sự kiện liên quan sẽ được tính toán lại từ các bài thành viên.

## Tóm tắt

**3.1 thu hẹp danh sách sự kiện cần so sánh → 3.2 cân nhắc nội dung và bằng
chứng để quyết định → 3.3 lưu sự kiện, bài liên quan và lý do quyết định.**
