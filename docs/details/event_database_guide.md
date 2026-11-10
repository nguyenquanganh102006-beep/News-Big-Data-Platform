# Đã lấy dữ liệu thật và lưu các vụ tai nạn vào database như thế nào?

## 1. Kết quả chính

Hệ thống đã chạy từ bước lấy tin RSS đến bước lưu sự kiện vào DuckDB.
DuckDB là database nằm trong một file trên máy, không cần cài một máy chủ riêng.

Quy ước tầng dữ liệu: **Silver chứa bài báo đã xử lý, là đầu vào phần 3**;
**Gold chứa database sự kiện và các bản xuất từ database**, là kết quả phần 3.

Trước đây hệ thống dừng ở danh sách **bài báo**. Bây giờ đã có thêm danh sách
**sự kiện tai nạn**, mỗi sự kiện có một `event_id`. Các bài được xác định cùng
nói về một vụ sẽ được liên kết vào cùng mã đó, trong khi bài nguồn vẫn được giữ.

Các thay đổi được làm trên nhánh `task/32-33`, nối tiếp code 3.1 của `task/31`.

## 2. Đã chạy dữ liệu thật được những gì?

Trong lần kiểm tra ban đầu ngày **04/11/2026**:

- Lấy được tổng cộng **410 bản tin RSS từ 7 nguồn** trong một lần crawl.
- Ở lần kiểm tra lịch sử này, luồng downstream mới xử lý VnExpress, VietnamPlus
  và Tuổi Trẻ, tổng cộng **160 bài** sau làm sạch và loại trùng URL. Luồng hiện
  tại đã mở preprocessing/filter/extraction cho cả 7 nguồn RSS; xem
  [sơ đồ luồng và các hướng dẫn chi tiết](../flow.md).
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

### Sau khi bổ sung tỉnh và chạy lại phần 3

Bước trích xuất phần 2 đã đọc thêm nhãn tỉnh/thành ở đầu bài VnExpress.
Phần 3 được sửa để bài **chưa có sự kiện** nhận thông tin mới từ Silver và được
xét lại, thay vì bị chặn vì dữ liệu thay đổi.

Kết quả trên database có sẵn:

- Giữ nguyên hai sự kiện cũ và các liên kết đã có.
- Cập nhật tỉnh cho cả ba bài VnExpress chưa được gán sự kiện.
- Tạo thêm hai sự kiện ở **Huế** và **Nghệ An**.
- Bài cầu Nhật Tân đã có tỉnh **Hà Nội** nhưng còn cờ thiếu chi tiết tai nạn,
  nên tiếp tục chờ xem xét, chưa tự tạo vụ mới.
- Database hiện có **5 bài, 4 sự kiện, 4 liên kết và 1 bài đang chờ**.
- Sáu mục chờ cũ được đánh dấu đã xử lý, vẫn giữ để tra lịch sử. Bảng
  `match_reviews` có bảy dòng lịch sử, trong đó chỉ một dòng còn `pending`.
- Chạy lại lần nữa không tạo thêm vụ, liên kết hoặc mục chờ.

Database đã được sao lưu trước thay đổi tại
`data/backups/before_unassigned_update_20261104_230840/`.

### Tự cập nhật theo bản Silver mới nhất

Phần 3 hiện tự nhận thay đổi của cả bài **đã có sự kiện**. Khi chạy lại bước 5:

1. Bài không thay đổi được bỏ qua.
2. Bài có thông tin mới được cập nhật trong database, lưu bản cũ vào lịch sử.
3. Nếu bài đã có sự kiện, giữ nguyên mã/liên kết đó và tính lại thông tin vụ.
4. Nếu bài chưa có sự kiện, tìm và so khớp lại như bình thường.

Không còn đưa bài vào hàng chờ chỉ vì `changed_input`. Những lý do thay đổi
cũ được đóng khi bản Silver hiện tại đã được áp dụng.

Ví dụ cùng một bài trước ghi 2 người tử vong, sau sửa thành 3: sự kiện tự đổi
sang 3, không tạo thêm vụ và không cộng thành 5. Thông tin mới được ghi nhận
theo từng trường: chỉ sửa mô tả hoặc bổ sung nhãn địa điểm không làm một con số
thương vong cũ trở thành con số mới nhất.

Với các bài khác nhau cùng vụ, ưu tiên thông tin có mốc cập nhật mới hơn; khi
chưa có lần sửa nào thì so theo ngày đăng bài. Nếu hai nguồn cùng mốc thời gian
nhưng số khác nhau hoặc nguồn mới nhất tự mâu thuẫn, trường đó vẫn là “chưa rõ”.
Thông tin bị thiếu trong bản mới không tự xóa giá trị đã biết; số 0 được nêu rõ
vẫn thay thế được số cũ. Các bằng chứng nguồn được giữ để đối chiếu.

“Bản mới nhất” ở đây là bài đã trích xuất trong `data/silver/accidents/` được
đem vào bước 5; hệ thống không tự biết một file cũ mà người dùng phục hồi là
bản cũ. Giới hạn cập nhật ở Silver làm sạch vẫn được nêu trong mục 7.

Đã chạy với database có sẵn sau sao lưu tại
`data/backups/before_auto_updates_20261104_233510/`. Mã/liên kết của 4 sự kiện
được giữ nguyên. Dữ liệu Silver thật lần này không thay đổi thêm nên không tạo
bản sửa giả để thử trên dữ liệu thật; các trường hợp cập nhật thương vong và
địa điểm được kiểm tra bằng test riêng.

## 3. Ba phần 3.1, 3.2, 3.3 làm gì?

### 3.1 — Tìm những vụ có thể liên quan

Với mỗi bài mới, hệ thống tìm các sự kiện cùng tỉnh/thành, có mốc đăng bài
trong khoảng 48 giờ trước đến 48 giờ sau. Nếu database đang rỗng thì không có
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
| `match_reviews` | Trường hợp thiếu hoặc khó quyết định cần xem xét |

Ngoài ra có bảng ghi lại các lần chạy, phiên bản và hai bảng xem tổng hợp
`accident_event_summary`, `article_event_summary`. Bảng xem sự kiện có danh sách
URL bài nguồn; bảng xem bài có `event_id` nếu bài đã được gán.
`article_revisions` giữ bản trước mỗi lần sửa; `article_updates` ghi mốc thay đổi
của các trường để chọn đúng thông tin mới hơn khi tổng hợp.

## 4. Dữ liệu nằm ở đâu?

Tất cả đường dẫn sau tính từ thư mục gốc repo:

```text
data/
├── bronze/<nguồn>/<thời điểm>.parquet       # Tin RSS vừa lấy
├── silver/
│   ├── <nguồn>.parquet                    # Lịch sử bài đã làm sạch
│   ├── filtered/<nguồn>/                   # Kết quả lọc tai nạn
│   └── accidents/<nguồn>.parquet          # Phần 2: bài đã trích xuất, đầu vào phần 3
└── gold/
    └── events/
        ├── accident_events.duckdb          # Database chính
        └── exports/
            ├── accident_events.parquet    # Danh sách vụ, có URL nguồn
            ├── articles.parquet           # Bài và event_id nếu đã được gán
            ├── event_articles.parquet     # Liên kết bài–vụ
            ├── match_reviews.parquet      # Các trường hợp cần xem xét
            ├── article_revisions.parquet  # Bản cũ trước khi tự cập nhật
            └── manifest.json             # Số lượng bản ghi lúc xuất
```

File cần giữ nếu muốn mở lại database là **`data/gold/events/accident_events.duckdb`**.
Các file Parquet trong `exports/` là bản xuất thêm, không thay thế database chính.
Thư mục `data/` được Git bỏ qua, nên dữ liệu nằm trên máy này, không tự đi theo
code khi push hoặc clone repo trên máy khác.

Trong thư mục xuất, `articles.parquet` là bản xem bảng bài nguồn đã nhập vào
database sự kiện, có `event_id` khi đã gán; đây không phải đầu vào phần 3.

### Chuyển từ bố cục cũ

Từ cập nhật ngày 06/11/2026, bước 4 ghi bài vào
`data/silver/accidents/<nguồn>.parquet`; bước 5 chỉ đọc đường dẫn Silver này.
Database vẫn nằm ở `data/gold/events/accident_events.duckdb`.

Với dữ liệu cũ ở `data/gold/accidents/`, sao lưu trước rồi chuyển nguyên các
file bài sang `data/silver/accidents/`; không sửa nội dung bài và không xóa
database. Hoặc chạy lại bước 4 để tạo đầu vào Silver từ kết quả lọc đang có
(cần mạng để đọc nhãn địa điểm VnExpress). Nếu thiếu Silver, bước 5 báo rõ cần
chạy bước 4; không âm thầm đọc lại dữ liệu trong Gold cũ.

Đã chuyển dữ liệu hiện có và chạy lại bước 5: vẫn có 5 bài, 4 sự kiện, 1 bài
chờ; các mã sự kiện và nội dung bài không đổi. Bản sao database cùng thư mục
bài cũ được giữ ở `data/backups/before_silver_event_input_20261106_203039/`.

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
| Đã có bài trích xuất trong Silver, chỉ chạy phần sự kiện | `python -m main --step=5` |
| Xem nhanh số bài, số vụ và nội dung vụ | `python -m events.inspect` |
| Chạy bộ kiểm tra tự động | `python -m unittest discover -s tests -v` |

Lệnh xem database chỉ đọc, không tải tin và không sửa dữ liệu. Chỉ chạy một
tiến trình ghi database tại một thời điểm; chạy lại bước 5 khi muốn tạo lại các
file xuất từ dữ liệu đã lưu.

## 6. Những điểm đã kiểm tra và sửa

- Đã chạy **111 kiểm tra tự động**, tất cả đều đạt, không cần đặt `PYTHONPATH`.
- Hai bài khác nguồn nói cùng vụ được gom thành một sự kiện trong test.
- Hai vụ có địa điểm khác nhau không bị gộp chỉ vì tiêu đề giống nhau.
- Chạy lại không tạo thêm bản ghi trùng, giữ nguyên mã sự kiện đã lưu.
- Bài chưa có sự kiện được cập nhật khi Silver bổ sung thông tin, rồi được tìm
  và so khớp lại. Nếu đã đủ thông tin thì gán vào vụ phù hợp hoặc tạo vụ mới.
- Bài đã có sự kiện cũng tự cập nhật khi Silver thay đổi; thông tin vụ được tính
  lại, giữ nguyên ID và liên kết, có lịch sử bản cũ. Nếu lỗi ghi thì cả nội dung,
  lịch sử và thông tin vụ đều được khôi phục bằng cách hủy lần nhập.
- Lý do chờ cũ được đóng khi xét lại; nếu bài vẫn thiếu thông tin thì chỉ lý do
  hiện tại còn chờ. Lịch sử không bị xóa.
- Nhiều báo cùng ghi 2 người tử vong thì tổng vẫn là 2, không cộng thành 4.
- Nếu các bài đưa số thương vong khác nhau, chọn số có mốc cập nhật mới hơn.
  Nếu mới ngang nhau mà mâu thuẫn thì để “chưa rõ”. Không tự chọn số lớn nhất
  và không coi thiếu số liệu là 0.
- Nếu lỗi giữa lúc nhập database, các thay đổi của cả lần nhập đó được hủy;
  dữ liệu đã lưu từ lần chạy thành công trước vẫn còn.
- Đã sửa hàm đổi ngày giờ: giữ đúng múi giờ có sẵn trong RSS. Ví dụ 12:00 giờ
  Việt Nam phải tương ứng 05:00 UTC. Dữ liệu thử mới được tạo lại từ Bronze sau sửa.

Nếu đã có Silver từ phiên bản cũ trước thay đổi múi giờ, chạy lại bước 2 chưa
chắc sửa được các dòng cũ vì cơ chế hiện tại giữ bài đã lưu theo URL. Cần sao lưu
và có kế hoạch xử lý lại dữ liệu cũ; không xóa database để thử tùy tiện.

## 7. Điều còn hạn chế

- Phần trích xuất hiện đọc tiêu đề và mô tả RSS; VnExpress được bổ sung nhãn
  tỉnh/thành ở đầu trang bài trong phần 2. Chưa dùng toàn bộ thân bài để trích
  xuất. Thiếu địa điểm ở đầu vào thì bài có thể chờ dù là tai nạn thật. Xem
  [cập nhật VnExpress và lưu ý với database cũ](accident_extraction.md).
- Mốc so sánh hiện là **ngày đăng bài**, chưa phải ngày tai nạn thực sự xảy ra.
  Trường `time_occurred` để trống khi chưa có bằng chứng, không điền ngày đăng thay thế.
  Bài về cùng vụ nhưng đăng muộn hơn bán kính 48 giờ có thể bị tách thành sự kiện mới.
- Chưa có trường tên đường riêng từ bước trích xuất. Phần so địa điểm chi tiết
  đang dùng quận/huyện và phường/xã khi có.
- Chưa đo độ đúng bằng tập bài thật được con người đánh dấu cùng/khác vụ.
  Các sự kiện tự động vẫn có thể bị gộp nhầm hoặc tách nhầm.
- Tin cập nhật trên cùng URL vẫn chịu cách lưu lịch sử bài làm sạch tại
  `data/silver/<nguồn>.parquet`: bản cũ được giữ. Khi thông tin mới đã có trong
  `data/silver/accidents/`, cả bài chưa gán và đã gán sự kiện đều được cập
  nhật tự động. Bài đã gán giữ cùng sự kiện, chưa tự chuyển sang vụ khác.
- Các file xuất được thay thế từng file. Nếu xuất bị gián đoạn sau khi database
  đã lưu thành công, chạy lại bước 5 để đồng bộ; database vẫn là dữ liệu chính.
- Chưa có màn hình duyệt các bài chờ xem xét, bản đồ hoặc dashboard.
