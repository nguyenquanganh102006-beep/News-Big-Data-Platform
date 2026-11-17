# Báo cáo hợp nhất nhánh và kiểm tra Phần 3 — 17/11/2026

## Phạm vi

Hợp nhất `fix/23-24` (commit `22f80be`, bản sửa mới nhất của bước lọc và trích xuất Phần 2) vào `task/32-33`. Giữ bán kính tìm sự kiện ±48 giờ của nhánh hiện tại và nhận phần bổ sung về batch, streaming, dashboard của nhánh mới. Các xung đột ở tài liệu, cấu hình phụ thuộc, hồ sơ sự kiện, embedding và kiểm thử đã được xử lý trước khi chạy lại.

Dữ liệu cũ do nhóm lưu nằm ở `data/bronze/bronze/<source>/`, trong khi bộ chọn Bronze trước đó chỉ đọc `data/bronze/<source>/`. Đã bổ sung đường dẫn lồng nhau vào bộ chọn và kiểm thử riêng. File Bronze gốc không bị sửa. Thư mục `data/` được Git bỏ qua nên dữ liệu đầu vào và Parquet đầu ra chỉ nằm ở máy chạy.

## Cách chạy và kết quả

Chạy `python -m preprocessors.run` rồi `python -m filters.run` bằng `.venv/bin/python` với `PYTHONPATH=src`. Preprocessor đọc file RSS và file `history_*.parquet` của cả 7 nguồn, giữ thân bài lịch sử trong Silver. Bước khử trùng nội dung nhận 20.965 bài, đánh dấu 12 bản trùng và đưa 20.953 bài vào bộ lọc.

| Nguồn | Bài sau khử trùng | Tai nạn | Không phải tai nạn | Cần xem xét |
|---|---:|---:|---:|---:|
| Báo Xây dựng | 3.730 | 170 | 3.555 | 5 |
| Dân Trí | 476 | 17 | 458 | 1 |
| Thanh Niên | 4.081 | 21 | 4.052 | 8 |
| Tiền Phong | 4.444 | 74 | 4.363 | 7 |
| Tuổi Trẻ | 3.768 | 29 | 3.730 | 9 |
| VietnamPlus | 4.286 | 20 | 4.262 | 4 |
| VnExpress | 168 | 6 | 161 | 1 |
| **Tổng** | **20.953** | **337** | **20.581** | **35** |

Đây là số **bài báo**, không phải số vụ tai nạn. Các bản tin có nhiều vụ vẫn có thể nhận nhãn `accident` và cần tách vụ ở bước sau. Số liệu này khác báo cáo rà soát 20.745 bài trên nhánh nguồn vì lần chạy này còn đọc các snapshot RSS có sẵn trong thư mục Bronze hiện tại; không so trực tiếp hai tỷ lệ như cùng một tập đầu vào.

## Rà soát hiệu quả và sửa lỗi

Đã đọc phân bố nhãn theo nguồn và lý do, xem 100 tiêu đề đầu trong nhóm tai nạn, toàn bộ 35 tiêu đề `uncertain`, và tìm các tiêu đề bị loại dù cùng chứa từ chỉ phương tiện và va chạm. Các trường hợp bị loại nổi bật là tin pháp lý sau vụ, tư vấn luật, tin sản phẩm và tai nạn ngoài đường bộ; đó là cách xử lý phù hợp với phạm vi đã ghi trong tài liệu bộ lọc. Các trường hợp `uncertain` vẫn cần người kiểm tra, nhất là tin thiếu ngữ cảnh đường bộ.

Phát hiện một lỗi chắc chắn: bài “Liên tục xảy ra tai nạn trên đường ven biển qua Gia Lai dù chưa đưa vào khai thác” là bài về tình trạng an toàn trên tuyến đường, không tường thuật một vụ cụ thể, nhưng bộ lọc nhận `accident` do tìm thấy tín hiệu va chạm trong thân bài. Đã bổ sung nhận diện tiêu đề tổng hợp “liên tục xảy ra tai nạn” trước khi xét nội dung; số bài `accident` giảm từ 339 còn 338.

Khi chạy 338 bài qua Phần 3, phát hiện thêm bài “Khánh Hòa: Ưu tiên mổ cấp cứu, nhiều nạn nhân vụ sạt lở đèo Khánh Lê qua cơn nguy kịch” chỉ cập nhật việc điều trị sau tai nạn. Đã bổ sung quy tắc loại tin điều trị này, thêm kiểm thử hồi quy và chạy lại bộ lọc. Đầu vào cuối cùng còn **337 bài tai nạn**; phiên bản quy tắc là `rules-v5.2-exclude-medical-followup`.

Không có tập nhãn độc lập cho toàn bộ dữ liệu hiện tại, nên các số trên không chứng minh precision hoặc recall. Rà soát tiêu đề và tìm kiếm theo từ khóa có thể bỏ sót các cách diễn đạt khác. Cần người kiểm duyệt một mẫu ngẫu nhiên ở cả ba nhóm trước khi công bố điểm chất lượng.

## Chạy toàn bộ Phần 3 trên bài tai nạn thật

Đã đưa **cả 338 bài ban đầu** qua trích xuất và ghép sự kiện với embedding mặc định. Lần đó tạo 173 sự kiện mới, ghép 13 bài với sự kiện có sẵn và để 152 bài chờ xem xét. Sau khi loại một bài cập nhật điều trị, đã chạy lại **toàn bộ 337 bài** qua trích xuất và ghép sự kiện trên database kiểm thử mới. Cả 6 bài VnExpress lấy được dấu địa phương từ trang nguồn khi chạy với kết nối mạng.

| Kết quả Phần 3 trên đầu vào cuối | Số lượng |
|---|---:|
| Bài đầu vào | 337 |
| Sự kiện mới | 173 |
| Bài được ghép vào sự kiện | 13 |
| Bài liên kết với sự kiện | 186 |
| Bài chờ xem xét, chưa liên kết | 151 |

Trong 151 bài chờ, 119 bài thiếu tỉnh/thành đã trích xuất, 34 bài có dấu hiệu chứa nhiều vụ, 37 bài thiếu chi tiết diễn biến và 7 bài chưa đủ căn cứ để ghép. Các lý do có thể cùng xuất hiện trên một bài nên không cộng các số này. Tỷ lệ chờ cao cho thấy giới hạn của dữ liệu và bước trích xuất hiện tại; hệ thống giữ các bài đó riêng thay vì tự gộp khi thiếu bằng chứng. Kiểm tra các sự kiện có nhiều bài cho thấy 11 sự kiện gồm hai bài và một sự kiện gồm ba bài; các cặp/nhóm đã xem nói về cùng vụ. Chưa có nhãn cùng vụ/khác vụ độc lập để đo độ đúng trên toàn bộ tập.

Chạy lại trên cùng database giữ nguyên 173 sự kiện, 186 liên kết và 151 bài chờ; 186 bài đã liên kết được nhận là đã xử lý, không tạo thêm sự kiện hoặc liên kết trùng.

Database kiểm thử nằm tại `data/evaluation/phase3_337_20261117/events.duckdb`; Parquet xuất tại thư mục `exports/` bên cạnh. Lần kiểm thử 338 bài trước khi sửa được giữ riêng tại `data/evaluation/phase3_338_20261117/`. Cả hai thư mục nằm trong `data/` và không được push lên GitHub.

## Kiểm thử và tái chạy

`python -m unittest discover -s tests -q`: **184 kiểm thử đạt, 5 bỏ qua**. Các kiểm thử gồm phát hiện Bronze lồng thư mục, lọc tai nạn, truyền thân bài, khử trùng và logic ghép sự kiện. Năm kiểm thử bị bỏ qua là kiểm thử tích hợp tùy chọn. Đã chạy Gold Phần 3 trên toàn bộ bài tai nạn; chưa chạy Redis replay, batch hoặc dashboard trên toàn bộ dữ liệu.

Để tái tạo từ Bronze đến Phần 3 trên database kiểm thử riêng tại thư mục gốc (Linux):

```bash
PYTHONPATH=src .venv/bin/python -m preprocessors.run
PYTHONPATH=src .venv/bin/python -m filters.run
PYTHONPATH=src .venv/bin/python -m extractors.run
PYTHONPATH=src .venv/bin/python -m events.run --database data/evaluation/phase3_337_20261117/events.duckdb --export-dir data/evaluation/phase3_337_20261117/exports
.venv/bin/python -m unittest discover -s tests -q
```

Đầu ra lọc nằm tại `data/silver/filtered/<source>/classified.parquet` và các file theo nhãn. Thống kê khử trùng nằm ở `data/silver/deduplicated/manifest.json`.

## Cập nhật: lấy thân bài sau khi lọc đầu RSS

RSS hiện chỉ cung cấp các trường đang chọn như tiêu đề, mô tả ngắn và liên kết. Đã thêm lượt lọc đầu bằng dữ liệu đó. Với bài được nhận là tai nạn hoặc còn chưa chắc chắn mà thiếu `content`, chương trình mở URL của đúng nguồn báo, lấy thân bài, lưu kết quả vào cache rồi lọc lại trước khi trích xuất và ghép vụ. Bài đã có thân bài không bị tải lại. Nếu URL lỗi hoặc trang không có vùng thân bài rõ ràng, chương trình giữ bài và ghi `body_fetch_status`; nó không dùng nội dung của khung “bài liên quan” làm thân bài.

Đã thử trực tiếp trên cả 7 nguồn. Trong **338 bài tai nạn** sau lượt lọc mới, 202 bài đã có thân bài, 61 bài được lấy thêm thân bài từ URL và 75 bài vẫn thiếu. Nhóm còn thiếu gồm 52 trang Báo Xây dựng, 22 trang Tiền Phong và 1 trang Dân Trí; nhiều trang trong đó là bản tin video hoặc clip, chỉ có mô tả ngắn. Kết quả lấy bài được lưu trong `data/silver/filtered/<source>/body_cache.parquet`; trang không có thân bài được thử lại sau một ngày.

Đã sửa thêm lỗi trích xuất tỉnh: nơi cư trú của tài xế và tỉnh ở cuối hướng di chuyển không được dùng làm nơi xảy ra vụ việc. Ví dụ bài xe khách ở Đồng Tháp trước đây bị để trống tỉnh vì có nhắc tài xế ngụ An Giang. Khi có thân bài mới và quy tắc này, số bài thiếu tỉnh trong đầu vào Phần 3 giảm từ 119 xuống 111. Bộ lọc cũng nhận thêm một bài tai nạn ở Gia Lai nhờ thân bài; bài về cây đổ đè ô tô khi mưa lớn vẫn ở nhóm chưa chắc chắn vì không rõ xe có đang lưu thông hay không. Phiên bản bộ lọc là `rules-v5.3-body-enrichment`.

| Kết quả Phần 3 | Trước cập nhật | Sau cập nhật |
|---|---:|---:|
| Bài tai nạn đầu vào | 337 | 338 |
| Sự kiện mới | 173 | 182 |
| Bài ghép vào sự kiện | 13 | 18 |
| Bài đã liên kết với sự kiện | 186 | 200 |
| Bài chờ xem xét | 151 | 138 |

Trong 138 bài chờ mới, 111 bài thiếu tỉnh, 34 bài có dấu hiệu kể nhiều vụ, 30 bài thiếu chi tiết diễn biến và 5 bài có ứng viên nhưng chưa đủ căn cứ ghép. Các lý do có thể chồng nhau. Số bài chờ giảm cho thấy dữ liệu đầy đủ hơn giúp hệ thống đưa ra thêm quyết định; chưa có nhãn độc lập để kết luận độ đúng của toàn bộ các quyết định ghép. Các nhóm ghép có nhiều bài đã được xem theo tiêu đề, không thấy cặp khác vụ rõ ràng trong lượt kiểm tra này.

Database thử nghiệm mới nằm tại `data/evaluation/phase3_body_enriched_338_20261117/events.duckdb`; Parquet xuất nằm trong `exports/` cùng thư mục. Đã chạy lại toàn bộ bước lọc, trích xuất và ghép vụ. Bộ kiểm thử chạy 197 trường hợp: **192 đạt, 5 bỏ qua**. Lần chạy này cần truy cập các trang báo để lấy nội dung; dữ liệu tải về và database thử nghiệm nằm trong `data/`, không được đưa lên GitHub.

## Cập nhật: tự bỏ qua video thiếu thân bài và giải thích bài chờ ghép

Mốc **138 bài chờ** ở trên chưa loại video. Kiểm tra HTML cho thấy các trang video của Báo Xây dựng và Tiền Phong có dữ liệu `VideoObject` nhưng không có thân bài chữ. Bộ lọc nay nhận video bằng tên video trùng tiêu đề trang và chỉ bỏ qua khi không trích được thân bài; lý do được ghi là `video_without_body`, nhãn là `skipped_video`. Bài chữ thiếu thân bài vẫn được giữ. Cache cũ của các trang thiếu thân bài được kiểm tra lại một lần theo quy tắc mới.

| Kết quả sau khi bỏ qua video | Số bài |
|---|---:|
| Bài tai nạn ở lần trước | 338 |
| Video thiếu thân bài được bỏ qua | 73 |
| Bài đưa vào Phần 3 | 265 |
| Tạo sự kiện mới | 165 |
| Ghép vào sự kiện đã có | 18 |
| Bài đã liên kết | 183 |
| Bài chờ xem xét | **82** |

Trong 73 video được bỏ qua, 55 bài từng nằm trong nhóm 138 bài chờ và 18 bài từng được tự liên kết. Vì vậy không thể lấy 138 trừ 73 để tính số chờ mới. Một bài khác trước đây chờ đã thành sự kiện mới khi tập bài ứng viên thay đổi. Trong 82 bài còn chờ, 71 bài có thân bài sẵn, 9 bài đã lấy được thân bài từ URL, và chỉ 2 bài chữ vẫn chưa lấy được thân bài. Do đó phần lớn số chờ hiện nay không phải do thiếu nội dung.

| Lý do chính của 82 bài chờ | Số bài | Ví dụ |
|---|---:|---|
| Không xác định chắc tỉnh/thành nơi xảy ra vụ | 65 | [Vụ ở Pleiku](https://thanhnien.vn/tai-nan-giao-thong-tai-pleiku-hai-ong-chau-tu-vong-duoi-gam-xe-tai-185251128125441622.htm) có “Gia Lai” trong mô tả nhưng bộ trích xuất vẫn bỏ sót. [Vụ ở Lâm Đồng](https://thanhnien.vn/xe-khach-lao-xuong-vuc-4-nguoi-chet-nhieu-nguoi-bi-thuong-185260406164240372.htm) nhắc cả địa danh cũ Bình Thuận nên bị coi là xung đột. [Cháy xe trên cao tốc Hà Nội – Hải Phòng](https://tienphong.vn/o-to-boc-chay-tren-cao-toc-ha-noi-hai-phong-post1805765.tpo) chỉ nêu tuyến đi qua nhiều địa phương. |
| Chưa đủ chi tiết để xác nhận một vụ tai nạn cụ thể | 12 | [Bài về hố sụt ở Đà Nẵng](https://www.vietnamplus.vn/can-canh-ho-tu-than-xuat-hien-giua-trung-tam-thanh-pho-da-nang-post1080824.vnp) chủ yếu nói về hiện trạng hố sụt. |
| Có ứng viên ghép nhưng chứng cứ chưa đủ chắc | 4 | [Vụ 7 ô tô trên cao tốc Phan Thiết – Dầu Giây](https://baoxaydung.vn/cao-toc-phan-thiet-dau-giay-7-o-to-va-cham-lien-hoan-giao-thong-un-tac-keo-dai-192260104170640203.htm). |
| Một bài kể nhiều vụ cần tách thành các sự kiện riêng | 1 | [Hai vụ trên cao tốc Nội Bài – Lào Cai](https://baoxaydung.vn/lien-tiep-hai-vu-tai-nan-tren-cao-toc-noi-bai-lao-cai-mot-tai-xe-tu-vong-19226030314461267.htm). |

Các hàng trong bảng dùng **lý do chính**, nên cộng đúng 82. Nếu tính mọi lý do cùng xuất hiện trên một bài, có 65 bài thiếu tỉnh, 18 bài kể nhiều vụ, 18 bài thiếu chi tiết và 4 bài ghép chưa chắc. Trong 65 bài thiếu tỉnh, 25 bài bị cờ xung đột địa danh và 17 bài cũng kể nhiều vụ. Có cả bài nước ngoài như [tai nạn ở Nigeria](https://tuoitre.vn/anthony-joshua-thoat-chet-sau-vu-tai-nan-nghiem-trong-o-nigeria-20251230062729713.htm), trong khi trường `province` hiện chỉ chứa tỉnh/thành Việt Nam. Đây là các nguyên nhân khác nhau, không thể xử lý bằng một quy tắc ghép duy nhất. Với các bài đã nêu rõ tỉnh nhưng trích xuất bỏ sót hoặc nhầm địa danh cũ, cần sửa bước trích xuất địa điểm; với bản tin nhiều vụ, cần tách vụ trước khi ghép. Hệ thống vẫn để chờ thay vì tự gán sai địa điểm hoặc gộp nhầm vụ.

Database kiểm thử nằm tại `data/evaluation/phase3_skip_empty_video_265_20261117/events.duckdb`, file xuất ở `exports/` bên cạnh. Đã chạy lại bộ lọc trên 20.953 bài sau khử trùng, trích xuất và ghép toàn bộ 265 bài còn lại. Bộ kiểm thử chạy 199 trường hợp: **194 đạt, 5 bỏ qua**. Dữ liệu và database nằm trong `data/`, không được đưa lên GitHub.

## Cập nhật: phân biệt bốn bài có ứng viên ghép

Kiểm tra quyết định ghép cho thấy ba cặp thực sự cùng vụ nhưng bị chặn vì thiếu nhãn phương tiện trùng nhau hoặc câu chữ không đủ giống. Quy tắc mới cho phép ghép khi hai bài cùng ngày, đăng cách nhau không quá 12 giờ, cùng một địa điểm cụ thể **và** có chi tiết diễn biến khớp. Với vụ sập cầu, cần cùng tên cầu và xã/phường, cả hai tiêu đề đều nói cầu sập hoặc gãy. Với va chạm liên hoàn, cần cùng tuyến đường, xã/phường và số xe trong tiêu đề. Cả hai trường hợp vẫn phải vượt ngưỡng giống nhau về nội dung, không có địa điểm hoặc ngày mâu thuẫn. Tên tỉnh và ngày đăng riêng lẻ không đủ để ghép.

Đã sửa thêm nhánh quyết định khi ứng viên có điểm thấp và không chung địa điểm cụ thể: bài được tạo thành sự kiện mới thay vì tự động chờ chỉ vì có ứng viên cùng tỉnh. Với [vụ xe buýt va quệt taxi ở Nguyễn Thị Thập](https://dantri.com.vn/thoi-su/dong-nguoi-dam-mua-vi-2-o-to-va-quet-khong-chiu-roi-di-o-tphcm-20261031174302254.htm), ứng viên cũ là [vụ xe ben tông xe máy trong hầm Phan Thúc Duyện](https://dantri.com.vn/thoi-su/doi-nam-nu-bi-xe-ben-can-tu-vong-trong-ham-chui-o-tphcm-20261031090102468.htm); hai vụ chỉ trùng TP.HCM và ngày, nên bài va quệt taxi nay tạo sự kiện riêng.

Chạy lại **toàn bộ 265 bài** trên database mới cho kết quả: **166 sự kiện mới, 21 bài ghép vào sự kiện có sẵn, 187 bài đã liên kết, 78 bài còn chờ**. Đối chiếu từng bài với lần chạy trước cho thấy **chỉ đúng bốn bài đổi quyết định**: ba bài được ghép vào đúng sự kiện đã có (7 ô tô trên cao tốc Phan Thiết – Dầu Giây, cầu Đắk Lung, cầu Tân Thành); một bài va quệt taxi trở thành sự kiện mới. Không có bài khác đổi kết quả. Trong 78 bài còn chờ, lý do chính gồm 65 bài thiếu tỉnh/thành, 12 bài thiếu chi tiết vụ việc và 1 bài kể nhiều vụ.

Database mới: `data/evaluation/phase3_matcher_v3_265_20261117/events.duckdb`; file xuất nằm tại `exports/` bên cạnh. Bộ kiểm thử chạy 202 trường hợp: **197 đạt, 5 bỏ qua**. Chưa có bộ nhãn độc lập cho toàn bộ cặp bài, nên kết quả trên xác nhận bốn trường hợp đã kiểm tra và không chứng minh chất lượng ghép trên mọi tình huống tương lai.
