# 4.1 và 4.2 — Nhận bài báo qua Redis và tạo sự kiện tạm

## 1. Kết quả chính

Đã xây dựng luồng nhận **từng bài báo mới** và xử lý ngay để tạo hoặc cập nhật
sự kiện tai nạn trong DuckDB.

Trước đây, luồng chính đọc các file rồi xử lý theo từng đợt. Luồng mới có một
chương trình chạy liên tục, chờ bài được gửi đến và xử lý từng bài:

```text
Bài báo → Producer → Redis → Consumer → sự kiện tạm trong DuckDB
```

Hiểu đơn giản: **Producer đưa bài vào hàng đợi**, **Redis giữ bài chờ xử lý**,
còn **Consumer lấy bài ra, xử lý và lưu kết quả**.

Sự kiện tạm (`Provisional Event`) là vụ tai nạn được hệ thống nhận diện ban đầu.
Kết quả có thể còn thiếu hoặc gom chưa đúng; bước Batch sau này sẽ xem lại để
tạo dữ liệu chính thức. Batch 4.3 và interface dùng chung 4.4 được mô tả trong
[hướng dẫn batch và matching](batch_matching.md).

Mã nguồn nằm trên nhánh `task/41-42`. Cách đánh số theo bảng phân công cuối của
IT4931: **4.1 là Redis Queue, 4.2 là Streaming Consumer**.

## 2. Đã chạy dữ liệu thật được những gì?

Lần kiểm chứng mới nhất ngày **10/11/2026**, sau khi chỉnh lại cấu trúc file:

- Redis chạy bằng Docker Desktop, phiên bản **7.4.12**; container báo
  `healthy`, lệnh kiểm tra kết nối trả về `PONG`.
- Lấy lại một bài Bronze có sẵn của VietnamPlus ngày 07/11/2026:
  **“Triệu tập tài xế ôtô VF3 chèn ép, tông xe máy khiến thai phụ ngã xuống đường”**.
- Producer gửi bài qua Redis; Consumer đang chờ tự nhận và xử lý bài.
- Database thử nghiệm có **1 bài, 1 sự kiện tại Lào Cai và 1 liên kết bài–vụ**.
  Không có bài chờ xem xét hoặc message lỗi trong lần chạy này.
- Thời gian từ lúc gửi đến lúc Consumer xử lý xong khoảng **0,078 giây**.
- **123 kiểm tra tự động đều đạt**, gồm 12 test streaming mới; 5 test dùng
  Redis thật trong Docker. Không có test bị bỏ qua trong lần chạy này.

Đây là **chạy lại bài Bronze đã có**, không phải crawl bài mới từ mạng.
Database và hàng đợi kiểm thử được tạo riêng, không ghi đè dữ liệu đang dùng.

Lần chạy thật này chỉ có một bài nên chứng minh được luồng tự động từ Redis đến
DuckDB. Trường hợp nhiều bài cùng vụ được kiểm tra bằng dữ liệu mẫu có kết quả
biết trước; chưa dùng lần chạy một bài để kết luận độ chính xác của việc gom.

Bằng chứng nằm trong `data_artifacts/diagnostics/streaming_conventions_20261110_124637/`:

| File | Dùng để xem gì? |
|---|---|
| `tests.log` | Kết quả 123 test |
| `real_bronze/article.json` | Bài thật được gửi vào Redis |
| `real_bronze/result.json` | Thời gian xử lý, số bài, số vụ và mã sự kiện |
| `real_bronze/provisional.duckdb` | Database của lần chạy thật |

## 3. Hai công việc 4.1 và 4.2 làm gì?

### 4.1 — Đưa bài vào hàng đợi Redis

Producer nhận một bài theo cấu trúc RSS Bronze, kiểm tra các trường cần thiết,
chuyển thành JSON rồi gửi vào hàng đợi `article_queue`. Producer chưa lọc tai
nạn hoặc tạo sự kiện. Nếu Redis không kết nối được thì báo lỗi cho bên gửi.

Bảy nguồn RSS đang được validator hỗ trợ là **VnExpress, VietnamPlus, Tuổi Trẻ,
Dân Trí, Thanh Niên, Báo Xây Dựng và Tiền Phong**. Đầu vào cần có nguồn, tiêu đề,
URL, thời gian đăng và mô tả; mô tả có thể rỗng. Consumer sẽ
kiểm tra định dạng thời gian khi xử lý.

Đã cung cấp hàm để crawler gọi sau khi lưu Bronze:

```python
from streaming.producer import enqueue_article

enqueue_article({**bronze_row, "source": "vietnamplus"})
```

**Crawler hiện tại chưa tự gọi hàm này.** Lần triển khai này cung cấp chỗ kết
nối và lệnh gửi bài riêng, chưa thay đổi luồng crawler cũ. Nếu gửi thất bại,
bên gọi cần giữ Bronze và gửi lại sau; chưa có chương trình tự gửi bù.

### 4.2 — Lấy bài và tạo hoặc cập nhật sự kiện tạm

Consumer chạy liên tục, chờ đến khi Redis có bài mới. Mỗi bài được xử lý như sau:

1. Đọc JSON và kiểm tra dữ liệu. Nếu bài đã xử lý thì bỏ qua.
2. Làm sạch HTML, khoảng trắng và chuẩn hóa ngày giờ.
3. Gọi bộ lọc phần 2. Bài không liên quan hoặc chưa rõ có phải tai nạn không
   được đưa sang bước tạo sự kiện.
4. Trích xuất địa điểm, phương tiện và thương vong bằng code phần 2.
   VnExpress có thêm bước đọc nhãn tỉnh/thành ở đầu trang bài.
5. Gọi interface matching dùng chung của phần 3, tìm vụ cùng tỉnh trong khoảng
   **24 giờ trước đến đúng mốc đăng bài** (gồm hai biên, loại candidate tương lai),
   rồi so nội dung, địa điểm, phương tiện và thời gian.
6. Lưu bài và kết quả vào DuckDB.

Ví dụ một bài nói về xe tải va chạm xe máy tại Hà Nội:

| Tình huống | Kết quả |
|---|---|
| Chưa có vụ phù hợp, bài đủ thông tin | Tạo một sự kiện tạm mới |
| Đã có vụ phù hợp và đủ điểm khớp | Liên kết bài vào vụ đó, tính lại thông tin vụ |
| Thiếu tỉnh hoặc chưa chắc cùng vụ | Giữ bài chờ xem xét |
| Gửi lại bài đã xử lý | Không tạo thêm bài, vụ hoặc liên kết |
| Bài chỉ nói về quy định giao thông | Không tạo sự kiện tai nạn |

Thuật toán và ngưỡng matching giữ như phần 3, không viết lại cách gom vụ.
Điểm khớp mặc định cần đạt 0.75, đồng thời thỏa các điều kiện về bằng chứng và
độ cách biệt với ứng viên khác. Không mặc định giống tiêu đề là cùng một vụ.

`article_key` là **mã bài báo**, tính từ nguồn và URL chuẩn hóa như phần 2;
`event_id` là **mã vụ tai nạn**. Một vụ có thể có nhiều bài với các mã bài khác
nhau nhưng cùng `event_id`.

## 4. Dữ liệu nằm ở đâu?

Các đường dẫn sau tính từ thư mục gốc repository:

```text
data/
├── bronze/                         # Bài RSS gốc vẫn được giữ
└── gold/
    ├── events/
    │   └── accident_events.duckdb   # Database phần 3 đã có
    └── streaming/
        └── provisional.duckdb      # Database sự kiện tạm của 4.1–4.2
```

Database streaming có các bảng chính:

| Bảng | Hiểu đơn giản |
|---|---|
| `provisional_articles` | Những bài đã lọc và trích xuất thông tin tai nạn |
| `provisional_events` | Các vụ tai nạn tạm thời |
| `provisional_event_articles` | Bài nào thuộc vụ nào và kết quả so khớp |
| `provisional_match_reviews` | Những bài cần xem xét thêm |
| `stream_receipts` | Bài đầu vào và kết quả xử lý, kể cả bài không phải tai nạn |

Bảng xem `provisional_accident_event_summary` có thêm danh sách URL bài nguồn
của mỗi vụ. Các bảng phần 3 được giữ nguyên. Consumer tìm ứng viên trong **kho
sự kiện tạm**, chưa tự đối chiếu với kho sự kiện chính thức.

Database kiểm thử ở mục 2 nằm trong diagnostics riêng, **không phải** file
mặc định `data/gold/streaming/provisional.duckdb`. Thư mục `data/` bị Git bỏ qua,
nên dữ liệu không tự đi theo code khi clone sang máy khác.

## 5. Cách chạy

Mở terminal tại thư mục gốc `News-Big-Data-Platform`, dùng môi trường `.venv`
đã cài theo [setup.md](../setup.md). Các lệnh dưới dành cho Windows PowerShell.

### Bước 1 — Khởi động Redis

Mở Docker Desktop và chờ engine sẵn sàng, sau đó chạy:

```powershell
.venv/Scripts/python.exe -m pip install -e .
docker compose up -d --wait redis
docker compose exec -T redis redis-cli ping
```

Kết quả cần có `PONG`. Redis mở tại `localhost:6379`, dùng volume để giữ dữ liệu
khi container khởi động lại.

### Bước 2 — Chạy Consumer

```powershell
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe -m streaming.run
```

Terminal này tiếp tục chờ bài; đó là trạng thái hoạt động bình thường.
Lệnh trực tiếp `python -m streaming.consumer` cũng chạy được.

Nếu chỉ thử dữ liệu minh họa ở bước 3, dùng database riêng thay cho lệnh trên:

```powershell
.venv/Scripts/python.exe -m streaming.run --database data/demo/provisional.duckdb
```

Chọn **một** lệnh chạy Consumer, không mở cả hai cùng lúc trên cùng hàng đợi.

### Bước 3 — Gửi bài từ terminal khác

Tạo file `article.json` theo cấu trúc sau. Đây là **dữ liệu minh họa**, không
phải bài báo thật:

```json
{
  "source": "vietnamplus",
  "title": "Xe tải va chạm xe máy tại Hà Nội",
  "description": "Xe tải va chạm xe máy tại quận Cầu Giấy, Hà Nội khiến 2 người tử vong.",
  "link": "https://example.com/demo-accident-1",
  "pub_date": "2026-11-10T08:00:00+07:00"
}
```

Gửi bài bằng Producer:

```powershell
.venv/Scripts/python.exe -m streaming.producer article.json
```

Terminal Consumer sẽ in kết quả xử lý. Với ví dụ trên và database trống, bài
đủ thông tin để tạo một sự kiện mới. Gửi lại cùng bài sẽ báo đã xử lý.

### Bước 4 — Xem dữ liệu đã lưu

Nhấn **Ctrl+C** ở terminal Consumer. Chương trình hoàn tất bài đang xử lý rồi
thoát. Sau đó chạy đoạn chỉ đọc sau để xem database mặc định:

```powershell
$env:PYTHONUTF8='1'
@'
import duckdb
c = duckdb.connect('data/gold/streaming/provisional.duckdb', read_only=True)
print(c.sql('SELECT event_id, province, article_count FROM provisional_events'))
print(c.sql('SELECT article_key, event_id FROM provisional_event_articles'))
print(c.sql('SELECT article_key, status FROM stream_receipts'))
c.close()
'@ | .venv/Scripts/python.exe -
```

Nếu dùng database demo hoặc xem lần chạy thật ở mục 2, thay đường dẫn trong
`duckdb.connect()` cho đúng. Dừng Consumer trước khi mở file từ chương trình
khác để tránh xung đột truy cập DuckDB.

Cấu hình đọc từ `.env`, có mẫu trong `.env.example`:

| Biến | Mặc định |
|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` |
| `REDIS_ARTICLE_QUEUE` | `article_queue` |
| `STREAM_DATABASE_PATH` | `data/gold/streaming/provisional.duckdb` |

## 6. Những điểm đã kiểm tra và cách xử lý lỗi

Consumer không xóa bài khỏi Redis ngay khi vừa lấy ra. Bài được chuyển sang
danh sách **đang xử lý**; chỉ khi DuckDB lưu thành công mới xác nhận hoàn tất.
Nếu chương trình dừng giữa chừng, lần chạy sau đưa bài dang dở về hàng đợi.

Database lưu dấu bài đã hoàn thành trong `stream_receipts`. Vì vậy, nếu đã lưu
xong nhưng chưa kịp xác nhận với Redis, nhận lại bài không tạo thêm vụ.

| Trường hợp đã kiểm tra | Hành vi |
|---|---|
| Hai bài khác URL được xác định cùng vụ | Cùng sự kiện, không cộng lặp thương vong |
| Gửi lại bài đã hoàn thành | Giữ nguyên số bài, số vụ và liên kết |
| Bài không liên quan hoặc chưa rõ là tai nạn | Giữ kết quả phân loại, không tạo vụ |
| Bài tai nạn thiếu tỉnh | Giữ bài chờ xem xét |
| JSON sai định dạng | Giữ message và lỗi trong hàng lỗi `<queue>:dead` |
| Lỗi module hoặc lỗi ghi giữa lúc xử lý | Hủy phần ghi chưa hoàn tất; thử lại nếu lỗi có thể thử lại |
| Đã lưu DB nhưng chưa xác nhận với Redis | Nhận lại và bỏ qua nhờ dấu đã xử lý |
| Hai Consumer mở cùng file DB | Khóa ghi ngăn Consumer thứ hai chạy |
| Producer không kết nối được Redis | Báo lỗi cho bên gửi |

Lỗi xử lý có thể thử lại được thử tối đa **3 lần**, sau đó giữ message trong
hàng lỗi để kiểm tra và gửi lại sau. Dữ liệu được xác định không hợp lệ có thể
chuyển thẳng sang hàng lỗi. Khi Redis mất kết nối, Consumer chờ rồi kết nối lại.

Các ca lỗi module/ghi DB được chủ động gây ra trong test để kiểm tra phục hồi.
Các ca thành công dùng Redis và DuckDB thật, không giả kết quả matching. Đã
kiểm tra bảng sự kiện chính thức phần 3 không bị thay đổi.

Chạy lại bộ test khi Redis đang mở:

```powershell
$env:STREAM_TEST_REDIS_URL='redis://localhost:6379/0'
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Nếu không đặt biến trên, **5 test Redis bị bỏ qua**; khi đó chưa thể coi là đã
kiểm chứng kết nối Redis. Mỗi test dùng hàng đợi và database riêng.

## 7. Những file chính của phần 4.1–4.2

| File | Vai trò |
|---|---|
| `src/config/streaming.py` | Cấu hình Redis và đường dẫn database |
| `src/streaming/producer.py` | Nhận bài từ crawler hoặc JSON, đưa vào Redis |
| `src/streaming/message.py` | Kiểm tra đầu vào và tạo mã nhận diện bài |
| `src/streaming/queue.py` | Quản lý bài chờ, đang xử lý, thử lại và hàng lỗi |
| `src/streaming/consumer.py`, `src/streaming/run.py` | Chạy vòng lặp nhận bài, hỗ trợ dừng an toàn |
| `src/streaming/pipeline.py` | Nối các bước phần 2–3 để xử lý từng bài |
| `src/streaming/repository.py` | Dùng lại cách lưu phần 3 với các bảng tạm riêng |
| `tests/test_streaming.py` | Kiểm tra xử lý bài, lỗi và kết nối Redis thật |
| `scripts/smoke_streaming.py` | Chạy lại bài Bronze thật, ghi bằng chứng riêng |
| `compose.yaml` | Khởi động Redis bằng Docker, có lưu dữ liệu |

Dependency Redis được thêm trong `pyproject.toml`. Hướng dẫn luồng tổng thể
và cài đặt ở [flow.md](../flow.md), [setup.md](../setup.md).

## 8. Điều còn hạn chế

- **Chưa tự nối crawler vào Producer**, chưa tự gửi bù khi enqueue thất bại.
- **Chưa xử lý bản sửa trên cùng URL.** Bài đã xử lý mà gửi lại nội dung mới
  vẫn bị bỏ qua. Bài mới có URL khác, nếu khớp cùng vụ, vẫn cập nhật được vụ đó.
- **Chất lượng phụ thuộc phần 2–3.** Bài thiếu tỉnh có thể phải chờ; chưa có tập
  bài thật được con người gán nhãn để đo độ chính xác. Hai bài Lào Cai trong
  báo cáo phần 3 từng có điểm 0.4356 chưa đủ gom; lần này không hạ ngưỡng để gộp.
- **Mốc tìm ứng viên là ngày đăng bài**, chưa phải thời điểm tai nạn.
  `time_occurred` để trống khi thiếu bằng chứng.
- **0,078 giây chỉ là kết quả của một bài VietnamPlus.** VnExpress còn phải
  tải nhãn tỉnh từ trang bài; chưa đo tải lớn hoặc cam kết tốc độ mọi nguồn.
- **Chỉ hỗ trợ một Consumer cho một cặp hàng đợi/database trên một máy.**
  Không chạy cùng hàng đợi với nhiều database khác nhau.
- Redis ghi dữ liệu AOF mỗi giây; khi Redis hoặc máy chết đột ngột vẫn có thể
  mất khoảng một giây dữ liệu. Bronze cần được giữ làm nguồn phục hồi.

Batch 4.3 sau này có thể đọc bài gốc từ `stream_receipts`, bài đã trích xuất và
quan hệ bài–vụ từ các bảng `provisional_*` để xem lại việc gom, xử lý bản cập
nhật và tạo kết quả chính thức. Giữ `article_key` và `event_id` để đối chiếu.
Phần đó chưa được triển khai trong công việc 4.1–4.2.
