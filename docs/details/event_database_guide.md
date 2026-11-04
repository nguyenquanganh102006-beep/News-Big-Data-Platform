# Đã lấy dữ liệu thật và lưu các vụ tai nạn vào database như thế nào?

## 1. Kết quả chính

Hệ thống đã chạy từ bước lấy tin RSS đến bước lưu sự kiện vào DuckDB.
DuckDB là database nằm trong một file trên máy, không cần cài một máy chủ riêng.

Trước đây hệ thống dừng ở danh sách **bài báo**. Bây giờ đã có thêm danh sách
**sự kiện tai nạn**, mỗi sự kiện có một `event_id`. Các bài được xác định cùng
nói về một vụ sẽ được liên kết vào cùng mã đó, trong khi bài nguồn vẫn được giữ.

Các thay đổi được làm trên nhánh `task/32`, nối tiếp code 3.1 của `task/31`.

## 2. Đã chạy dữ liệu thật được những gì?

Trong lần kiểm tra ngày **04/11/2026**:

- Lấy được tổng cộng **410 bản tin RSS từ 7 nguồn** trong một lần crawl.
- Ba nguồn có bước xử lý tiếp hiện nay là VnExpress, VietnamPlus, Tuổi Trẻ.
  Ba nguồn này có tổng cộng **160 bài** sau làm sạch và loại trùng URL.
- Bộ lọc chọn **5 bài** để trích xuất thông tin tai nạn; còn **2 bài** thuộc nhóm
  chưa rõ của bộ lọc, chưa chuyển sang bước sự kiện.
- Database đã lưu **5 bài**, tạo **2 sự kiện**, liên kết **2 bài** vào các sự kiện
  đó và giữ **3 bài chờ xem xét** vì chưa nhận diện được tỉnh/thành.
- Chạy lại toàn bộ luồng và chạy lại riêng bước sự kiện không làm tăng số vụ,
  số bài hoặc số trường hợp chờ xem xét.

Hai sự kiện được tạo từ bài về vụ va chạm xe ben ở TP Hồ Chí Minh và bài về vụ
ôtô VF3 tông xe máy ở Lào Cai. Đây là kết quả tự động ban đầu từ tin RSS, chưa
phải danh sách đã được con người kiểm duyệt đầy đủ.

Trong 5 bài thật của lần chạy này chưa có cặp nào được gom vào cùng một vụ.
Khả năng gom nhiều bài cùng vụ đã được kiểm tra bằng dữ liệu mẫu có kết quả
biết trước; chưa thể lấy lần chạy thật nhỏ này để kết luận độ chính xác của việc gom.

## 3. Ba phần 3.1, 3.2, 3.3 làm gì?

### 3.1 — Tìm những vụ có thể liên quan

Với mỗi bài mới, hệ thống tìm các sự kiện cùng tỉnh/thành, có mốc đăng bài
trong khoảng 24 giờ trước đến 24 giờ sau. Nếu database đang rỗng thì không có
ứng viên, và bài đủ thông tin có thể mở một sự kiện mới.

### 3.2 — Quyết định bài thuộc vụ nào

Hệ thống so nội dung bài, địa điểm chi tiết, phương tiện và thời gian.
Phần so nội dung dùng TF-IDF: biến văn bản thành các con số để đo mức giống nhau.
Nó không chỉ xem URL và cũng không mặc định cùng loại xe là cùng một vụ.

- Có đủ bằng chứng và một sự kiện phù hợp rõ ràng: liên kết bài vào sự kiện đó.
- Không tìm thấy sự kiện phù hợp, bài đủ thông tin: tạo sự kiện mới.
- Thiếu thông tin hoặc có nhiều sự kiện gần giống nhau: giữ bài chờ xem xét.

Điểm khớp mặc định cần đạt 0.75, đồng thời phải thỏa các điều kiện về lượng
thông tin và độ cách biệt với ứng viên khác. Đây là mức khởi đầu để thử nghiệm,
chưa phải con số đã được xác nhận tối ưu trên tập bài thật được gán nhãn.
Không tự gộp lại hoặc tách lại những sự kiện đã lưu trước đó.

### 3.3 — Lưu sự kiện và các bài liên quan

Database có bốn bảng dữ liệu chính:

| Bảng | Hiểu đơn giản |
|---|---|
| `articles` | Từng bài báo và thông tin đã trích xuất |
| `accident_events` | Từng vụ tai nạn và thông tin tổng hợp |
| `event_articles` | Bài nào đang thuộc vụ nào, vì sao được gán |
| `match_reviews` | Trường hợp thiếu, thay đổi hoặc khó quyết định cần xem xét |

Ngoài ra có bảng ghi lại các lần chạy, phiên bản và hai bảng xem tổng hợp
`accident_event_summary`, `article_event_summary`. Bảng xem sự kiện có danh sách
URL bài nguồn; bảng xem bài có `event_id` nếu bài đã được gán.

## 4. Dữ liệu nằm ở đâu?

Tất cả đường dẫn sau tính từ thư mục gốc repo:

```text
data/
├── bronze/<nguồn>/<thời điểm>.parquet       # Tin RSS vừa lấy
├── silver/<nguồn>.parquet                  # Bài đã làm sạch
├── filtered/<nguồn>/                       # Kết quả lọc tai nạn
└── gold/
    ├── accidents/<nguồn>.parquet           # Thông tin theo từng bài
    └── events/
        ├── accident_events.duckdb          # Database chính
        └── exports/
            ├── accident_events.parquet    # Danh sách vụ, có URL nguồn
            ├── articles.parquet           # Bài và event_id nếu đã được gán
            ├── event_articles.parquet     # Liên kết bài–vụ
            ├── match_reviews.parquet      # Các trường hợp cần xem xét
            └── manifest.json             # Số lượng bản ghi lúc xuất
```

File cần giữ nếu muốn mở lại database là **`data/gold/events/accident_events.duckdb`**.
Các file Parquet trong `exports/` là bản xuất thêm, không thay thế database chính.
Thư mục `data/` được Git bỏ qua, nên dữ liệu nằm trên máy này, không tự đi theo
code khi push hoặc clone repo trên máy khác.

## 5. Cách chạy

Mở terminal ở thư mục gốc repo. Nếu chưa có môi trường Python:

```bash
python -m venv .venv
```

Kích hoạt trên Linux/macOS:

```bash
source .venv/bin/activate
```

Hoặc trên Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Cài các thư viện, kể cả DuckDB và thư viện so nội dung:

```bash
python -m pip install -e .
```

Dùng đúng môi trường vừa cài thì không cần đặt `PYTHONPATH`.

| Muốn làm gì? | Lệnh |
|---|---|
| Lấy tin và chạy toàn bộ đến database | `python -m main` |
| Đã có Gold, chỉ chạy phần sự kiện | `python -m main --step=5` |
| Xem nhanh số bài, số vụ và nội dung vụ | `python -m events.inspect` |
| Chạy bộ kiểm tra tự động | `python -m unittest discover -s tests -v` |

Lệnh xem database chỉ đọc, không tải tin và không sửa dữ liệu. Chỉ chạy một
tiến trình ghi database tại một thời điểm; chạy lại bước 5 khi muốn tạo lại các
file xuất từ dữ liệu đã lưu.

## 6. Những điểm đã kiểm tra và sửa

- Đã chạy **81 kiểm tra tự động**, tất cả đều đạt, không cần đặt `PYTHONPATH`.
- Hai bài khác nguồn nói cùng vụ được gom thành một sự kiện trong test.
- Hai vụ có địa điểm khác nhau không bị gộp chỉ vì tiêu đề giống nhau.
- Chạy lại không tạo thêm bản ghi trùng, giữ nguyên mã sự kiện đã lưu.
- Nhiều báo cùng ghi 2 người tử vong thì tổng vẫn là 2, không cộng thành 4.
- Nếu các bài đưa số thương vong khác nhau, tổng để “chưa rõ”, giữ thông tin
  từng bài để đối chiếu; không tự chọn số lớn nhất. Không coi thiếu số liệu là 0.
- Nếu lỗi giữa lúc nhập database, các thay đổi của cả lần nhập đó được hủy;
  dữ liệu đã lưu từ lần chạy thành công trước vẫn còn.
- Đã sửa hàm đổi ngày giờ: giữ đúng múi giờ có sẵn trong RSS. Ví dụ 12:00 giờ
  Việt Nam phải tương ứng 05:00 UTC. Dữ liệu thử mới được tạo lại từ Bronze sau sửa.

Nếu đã có Silver từ phiên bản cũ trước thay đổi múi giờ, chạy lại bước 2 chưa
chắc sửa được các dòng cũ vì cơ chế hiện tại giữ bài đã lưu theo URL. Cần sao lưu
và có kế hoạch xử lý lại dữ liệu cũ; không xóa database để thử tùy tiện.

## 7. Điều còn hạn chế

- Hiện chỉ đọc tiêu đề và mô tả RSS, chưa lấy toàn bộ nội dung bài. Thiếu địa
  điểm ở đầu vào thì bài có thể nằm trong danh sách chờ dù là tai nạn thật.
- Mốc so sánh hiện là **ngày đăng bài**, chưa phải ngày tai nạn thực sự xảy ra.
  Trường `time_occurred` để trống khi chưa có bằng chứng, không điền ngày đăng thay thế.
  Bài về cùng vụ nhưng đăng muộn hơn cửa sổ 24 giờ có thể bị tách thành sự kiện mới.
- Chưa có trường tên đường riêng từ bước trích xuất. Phần so địa điểm chi tiết
  đang dùng quận/huyện và phường/xã khi có.
- Chưa đo độ đúng bằng tập bài thật được con người đánh dấu cùng/khác vụ.
  Các sự kiện tự động vẫn có thể bị gộp nhầm hoặc tách nhầm.
- Tin cập nhật trên cùng URL vẫn chịu cách lưu Silver hiện có: bản cũ được giữ.
  Nếu đầu vào Gold của một bài đã lưu thay đổi, phần sự kiện ghi nhận để xem xét,
  chưa âm thầm thay nội dung hay chuyển bài sang vụ khác.
- Các file xuất được thay thế từng file. Nếu xuất bị gián đoạn sau khi database
  đã lưu thành công, chạy lại bước 5 để đồng bộ; database vẫn là dữ liệu chính.
- Chưa có màn hình duyệt các bài chờ xem xét, bản đồ hoặc dashboard.
