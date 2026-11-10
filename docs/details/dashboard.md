# Dashboard tin tức và sự kiện

Dashboard Streamlit chạy local. Khi xem, dashboard chỉ đọc dữ liệu; nút Làm mới
tổng hợp lại snapshot lịch sử và dựng canonical, không sửa Bronze/Silver gốc
hoặc ghi quyết định review. Dashboard không tự crawl.

## Khởi động

Từ gốc repository:

```powershell
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m streamlit run src/dashboard/app.py
```

Mở `http://127.0.0.1:8501`. Dừng server bằng Ctrl+C. Cấu hình mặc định chỉ lắng
nghe trên máy local.

## Một bộ dữ liệu hiện hành, toàn bộ lịch sử

Không có dropdown chọn các lần diagnostics. Dashboard dùng duy nhất snapshot được
trỏ bởi `data_artifacts/dashboard_current.json`, gồm tất cả bài trong lịch sử Bronze gốc và
các lần crawl thật đã kiểm chứng ở diagnostics. Không cộng các bản copy hoặc replay:
snapshot crawl giống nhau được gộp; bài trùng source + URL chuẩn hóa chỉ giữ bản
trong lần crawl mới nhất. Không giới hạn hôm nay; bộ lọc ngày mặc định tắt.

Nhấn **Làm mới dữ liệu** sau pipeline để tổng hợp lại lịch sử, chạy classifier
hiện hành và dựng canonical từ phần lịch sử đã trích xuất. Có thể chạy CLI:

```powershell
.venv/Scripts/python.exe -m dashboard.publish
```

Mỗi lần xuất bản tạo snapshot mới trong `data_artifacts/dashboard_snapshots/`; pointer chỉ
được thay sau khi catalog và canonical hoàn tất. Lỗi cập nhật giữ bản hiện hành.
Snapshot cũ giữ để truy vết nhưng không xuất hiện như bộ dữ liệu khác trên UI.
Nếu chưa có pointer, dashboard dùng `data/` làm bộ duy nhất.

Catalog bài báo, lọc tai nạn, extraction và canonical đều dùng cùng danh sách đủ
7 nguồn RSS. Thư mục `data/` chỉ giữ `bronze/`, `silver/`, `gold/`; snapshot
dashboard và diagnostics nằm trong `data_artifacts/`.
Không có Redis vẫn xem được. Không giữ connection DuckDB giữa các lần đọc.

## Các tab

Tab **Thống kê thời gian** bổ sung:

- Gộp ngày, tuần (bắt đầu thứ Hai), tháng; tổng bài/tai nạn/chưa chắc chắn và
  tỷ lệ tai nạn trên tổng bài trong từng kỳ.
- Trung bình bài mỗi ngày trong khoảng được chọn (gồm ngày trống), số ngày có
  bài đăng, so sánh tỷ lệ theo từng nguồn và biểu đồ từng nguồn theo ngày.
- Phân bố giờ đăng 0–23 và thứ Hai đến Chủ nhật; bảng số liệu tải được CSV.
- Trong tab Sự kiện: số vụ và thương vong đã ghi nhận theo ngày bài đầu tiên,
  đếm mỗi vụ một lần, không đếm theo số bài liên quan. Thương vong thiếu vẫn
  để trống; không biến thành số 0.

Thống kê bài áp dụng các bộ lọc sidebar. Thống kê sự kiện áp dụng kho sự kiện và
bộ lọc tỉnh riêng. Ngày không có bài trong snapshot không chứng minh ngoài thực
tế không có vụ tai nạn. Đây là phân bố theo ngày đăng, không phải lúc xảy ra vụ.

1. **Tổng quan**: số bài, nhãn lọc theo nguồn, bài theo ngày đăng, bài tai nạn gần
   đây. Bộ lọc nguồn/nhãn/từ khóa/ngày ở sidebar áp dụng cho số liệu bài báo.
2. **Bài báo**: bảng tìm kiếm, link mở bài gốc, mô tả, lý do và tải CSV.
3. **Sự kiện**: số sự kiện/bài liên kết/review của toàn kho đã chọn; thống kê theo
   tỉnh và tra cứu các bài thuộc một event. Lọc tỉnh áp dụng cho bảng/biểu đồ sự
   kiện. Bộ lọc bài báo không làm thay đổi các chỉ số toàn kho này.
4. **Chờ review**: tách bài chưa chắc là tai nạn (`uncertain`) và bài đã xác định
   tai nạn nhưng thiếu thông tin hoặc matching chưa chắc chắn. Các bảng review
   dùng toàn bộ bộ dữ liệu/kho đã chọn, không phụ thuộc bộ lọc bài báo.

Không đồng nhất số bài tai nạn với số vụ. Ví dụ lần chạy mới có 2 bài tai nạn
nhưng 0 canonical event và 2 matching review; dashboard thể hiện đúng trạng thái
này. Thương vong trống không được thay bằng 0. Biểu đồ ngày là ngày đăng theo
múi giờ Việt Nam, không phải ngày xảy ra tai nạn. Không có bản đồ vì dữ liệu hiện
chưa có tọa độ được xác thực.

## Kiểm tra

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_dashboard.py
```

Đã kiểm tra tìm kiếm ký tự đặc biệt, lọc ngày theo giờ Việt Nam, database chỉ đọc,
chuyển nhóm review, dữ liệu trống và thao tác UI bằng Streamlit AppTest. Kiểm tra
thêm trên dữ liệu chạy thật: đổi dataset, đổi canonical/streaming, mở nhánh có sự
kiện và review; server trả HTTP health 200. Phiên công cụ không có trình duyệt
khả dụng để chụp và kiểm tra ảnh giao diện.
