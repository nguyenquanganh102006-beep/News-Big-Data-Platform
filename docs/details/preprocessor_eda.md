## Preprocessors

### 0. General

File này mô tả quá trình tôi (Huy) làm EDA, chuyển từ raw data (bronze) sang cleaned data (silver)

Folder structure:
+ PWD: `src/preprocessors`
+ File chính để chạy luồng: `run.py`
+ File chứa các hàm hỗ trợ: `utils.py`

>[!NOTE]
> Các số liệu ở dưới phụ thuộc vào ngày chạy file crawl (vì RSS cập nhật liên tục)
> Check bằng cách vào file `.parquet` -> Tìm field `system_created_at`

Ngày crawl: $20/10/2026$


### 1. RSS VnExpress

#### 1.0. Overview
Path: `src/preprocessors/rss_vnexpress.py`

In ra các cột `df.columns`:  
`['title', 'description', 'pub_date', 'link', 'link_count', 'meta_title', 'meta_description', 'meta_link', 'system_created_at', 'meta_pub_date', 'meta_generator', 'guid']`

Check từng cột một

#### 1.1. Cột title
**Attempt 1**: Kiểm tra xem có ký tự nào bất thường không -> Viết hàm util `check_valid_characters(text: str) -> bool`  
--> Số row valid: $60/60$ 

**Attempt 2**: Độ dài nằm trong khoảng $[24, 85]$

**Kết luận**: Chưa có vấn đề gì


#### 1.2. Cột description
**Attemp 1**: Kiểm tra ký tự bất thường --> Số row valid: $0/60$

Ví dụ: `<a href="https://vnexpress.net/vu-be-trai-nga-tu-vong-o-san-truong-khong-co-dau-hieu-toi-pham-5133447.html"><img src="https://i1-vnexpress.vnecdn.net/2026/10/16/1792109308590-1993428671226091-2894-8354-1792109614.jpg?w=1200&amp;h=0&amp;q=100&amp;dpr=1&amp;fit=crop&amp;s=VN7kACCvRNzNIThxS4KqEA" /></a>Qua khám nghiệm hiện trường, giám định pháp y, Công an Hải Phòng bước đầu xác định vụ học sinh lớp 1 ngã ở sân Trường Tiểu học An Dương không có dấu hiệu tội phạm.`

Vấn đề: Tất cả các description đều có tag link `<a>` bọc ngoài tag `<img>`

**Attempt 2**: Check xem mỗi description có bao nhiêu link -> Nếu có nhiều link thì tạo field mới `links: str[]`

```bash
┌─────────────────────────────────┬────────────┐
│ link                            ┆ link_count │
│ ---                             ┆ ---        │
│ str                             ┆ i64        │
╞═════════════════════════════════╪════════════╡
│ https://vnexpress.net/xe-tang-… ┆ 1          │
│ https://vnexpress.net/nga-ra-d… ┆ 1          │
│ https://vnexpress.net/thanh-ho… ┆ 1          │
│ https://vnexpress.net/bo-chinh… ┆ 1          │
│ https://vnexpress.net/cau-gan-… ┆ 1          │
└─────────────────────────────────┴────────────┘
...
```

+ Tổng số links: $60$ = Tổng số row  
--> Mỗi description đều chỉ chứa đúng 1 link, cùng 1 format thẻ `<a>` bọc ngoài `<img>`

**Attemp 3**: Lấy link trong thẻ `<a>` để so sánh với cột `link` -> Nếu không giống nhau sẽ tạo cột mới `description_link`
+ Viết hàm util `extract_anchor_tag_href(text: str) -> str` để lấy link của thẻ `<a>` 

```bash
┌─────────────────────────────────┬─────────────────────────────────┬────────────┐
│ link                            ┆ description_link                ┆ link_count │
│ ---                             ┆ ---                             ┆ ---        │
│ str                             ┆ str                             ┆ i64        │
╞═════════════════════════════════╪═════════════════════════════════╪════════════╡
│ https://vnexpress.net/xe-tang-… ┆ https://vnexpress.net/xe-tang-… ┆ 1          │
│ https://vnexpress.net/nga-ra-d… ┆ https://vnexpress.net/nga-ra-d… ┆ 1          │
│ https://vnexpress.net/thanh-ho… ┆ https://vnexpress.net/thanh-ho… ┆ 1          │
│ https://vnexpress.net/bo-chinh… ┆ https://vnexpress.net/bo-chinh… ┆ 1          │
│ https://vnexpress.net/cau-gan-… ┆ https://vnexpress.net/cau-gan-… ┆ 1          │
└─────────────────────────────────┴─────────────────────────────────┴────────────┘
```

+ Số row mà tại đó `link == description_link`: $60/60$  
--> Tất cả đều có description link lặp lại

+ Xét thấy các link đều giống nhau, mà thẻ `<img>` trong thẻ `<a>` không dùng tới --> sẽ bỏ nguyên cái thẻ `<a>` đi

**Process 3**: Loại bỏ các thẻ `<a>`
+ Viết hàm util `remove_anchor_tag(text: str) -> str`, trả về description mới hoặc chuỗi rỗng `""` nếu không có thẻ `<a>`

**Attempt 4**: Độ dài description
+ Trước khi bỏ thẻ `<a>`: $[372, 502]$
+ Sau khi bỏ thẻ `<a>`: $[110, 185]$

#### 1.3. pub_date

**Attempt 1**: Format: "Tue, 20 Oct 2026 11:08:48 +0700" -> string

**Process 1**: Chuyển về datetime utc (chỉnh timezone `+07:00` về `+00:00`), time unit là `microseconds`
+ Viết hàm util `convert_string_to_datetime_utc(dt_str: str, format: str) -> datetime`

**Attempt 2**: Check range: `2026-10-16T18:34:09Z` -> `2026-10-20T04:08:48Z`

#### 1.4. link

**Attempt 1**: Expect các format đều phải có cùng source `https://vnexpress.net/...` -> OK

**Attempt 2**: Expect các đuôi url đều là `.html` -> OK

#### 1.5. guid

**Attempt 1**: Expect `guid` là unique -> OK


### 2. RSS Vietnamplus

#### 2.1. title

**Attempt 1**: Check ký tự bất thường -> $4/50$ có vấn đề.
+ Ví dụ: Rà soát, tháo dỡ biển báo hạn chế tốc độ “bủa vây” đường ven biển Nghệ An  
--> Điểm chung: Dấu nháy kép kiểu hoa mỹ (“”) khác với dấu nháy bình thường ("")

**Process 1**: Chuẩn hóa dấu nháy
+ Viết hàm util `normalize_double_quotes(text: str) -> str` chuyển dấu nháy “hoa mỹ” về dấu "nháy thường"

**Attempt 2**: Check range $[56, 81]$

#### 2.2. description

**Attempt 1**: Description cái này hơi bựa, nó gồm 1 ảnh bọc trong 1 link, 1 đoạn text, và 3 cái link (chưa rõ link gì, nhưng có vẻ là link liên quan đến bài báo thôi). Tổng cộng 4 link, trong đó link bọc ngoài ảnh giống cột `link` -> Chỉ cần lấy 3 link còn lại là được. 

**Process 1**: Loại bỏ thẻ `<a>` đầu tiên, và trích xuất `href` của 3 thẻ `<a>` tiếp theo, sau đó bỏ hết, chỉ giữ lại đoạn text trong thẻ `<p>`
+ Sử dụng lại hàm `extract_anchor_tag_href(text: str) -> str` để lấy 3 link trên
+ Nối chúng lại, seperate bằng ký tự `;` và thêm cột mới `description_links`
+ Viết thêm hàm `extract_paragraph_tag_innertext(text: str) -> text` để lấy text trong thẻ `<p>` và lưu lại vào cột `description`

#### 2.3. pub_date

Giống `pub_date` trên kia ([1.3](#13-pub_date))

#### 2.4. link

Bắt đầu bằng `https://www.vietnamplus.vn/`, kết thúc bằng `.vnp`

#### 2.5. atom_link

Link này trỏ đến chính link rss, nhưng do tôi chủ quan nên chưa check kĩ syntax để kéo trường này về, nên hiện tại nó đang là `null`, mà thấy ae dùng cột `link` là đủ rồi, nên tôi sẽ xóa luôn cột này nhé :D

#### 2.6. updated

Chuyển từ `str` sang `datetime` (xử lý giống cột `pub_date`)

So sánh với cột `pub_date` -> $3/50$ row tại đó `updated` > `pub_date`  
--> Giả thuyết: Đây là thời gian lần cuối bài báo được chỉnh sửa, có thể coi 2 trường `pub_date` và `updated` tương ứng 2 cột `created_at` và `updated_at` trong database.

#### 2.7. guid

Xử lý giống `guid` trên kia ([1.5](#15-guid))

### 3. RSS Tuoitre

#### 3.1. title

range $[55, 105]$

valid characters: $50/50$ rows ok

#### 3.2. description

range $[101, 282]$

valid characters: $50/50$ rows ok

#### 3.3. pub_date

**Attempt 1**: Format: `10/20/2026 1:10:00 PM` -> Chưa rõ timezone 
+ Vào lại trang báo (`.htm`) để check, vd: `23/10/2026 14:22 GMT+7` dùng timezone VN  
--> Trùng với giờ của pub_date `10/23/2026 2:22:00 PM`  
--> Giờ trong RSS đang mặc định là dùng timezone VN

**Process 1**: Định nghĩa lại format và dùng timezone VN (+7)

**Attempt 2**: Khi chạy thử process thì gặp lỗi `ValueError: time data '10/20/2026 1:10:00\u202fPM' does not match format '%a, %d %b %Y %H:%M:%S %z'`  
--> Chạy `print(repr(df[0, 'pub_date']))` để show hết dưới dạng unicode  
--> Vấn đề: String thực chất chứa một khoảng trắng khá sus `10/20/2026 1:10:00\u202fPM` -> Cần normalize thành space bình thường

Note: Sau khi sửa lại format thì thấy code vẫn xử lý được, nên không cần thêm bước xử lý khoảng trắng :D

#### 3.4. link

Start with: `https://tuoitre.vn/`  
End with: `.htm`  
--> $50/50$ rows ok

#### 3.5. author 

**Attempt 1**: Đa số tên tác giả đều có hình ngôi sao ở đằng sau: `LÊ TRUNG⭐`, `TRƯỜNG TRUNG⭐`, `HOÀNG TÁO⭐`, `ĐOÀN CƯỜNG`
+ Thống kê: $44/50$ có hình sao -> Không phải vấn đề typo
+ Lọc uniques: vd: `ĐỨC PHÚ⭐`, `THẨM PHÁN LÊ THIẾT HÙNG`, `THANH HIỀN⭐` -> Không phải outliers
+ Thử kiểm tra tài khoản:
  + Tài khoản có ngôi sao thường là nhà báo, phóng viên, ... (có tài khoản)
  + Tài khoản không có ngôi sao là không có tài khoản :D (không có link đến tài khoản)

**Process 1**: Giả thiết các account có ngôi sao là tài khoản đã xác thưc (nếu sau này tính đến độ uy tín thì sẽ ưu tiên các tài khoản này)
+ Normalize tên tài khoản (Chuyển từ dạng CAPSLOCKS về Viết Hoa Bình Thường)  
--> Split by dấu cách ` ` và cả dấu chấm `.` (vd: `P.Thảo`)
+ Xóa ngôi sao (unicode: `\u2b50`)
+ Thêm một cột `verified` (boolean), `= true` nếu tài khoản có ngôi sao

