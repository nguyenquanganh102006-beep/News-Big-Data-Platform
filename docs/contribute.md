## Contribute

Mấy cái chung chung như git pull push gì đó tôi sẽ nói qua lệnh cho đúng quy trình thôi, còn đâu tôi sẽ viết mấy chuẩn chung để ae tiện làm việc với nhau.

Tình huống hiện tại là khi ae được giao việc thì sẽ làm như nào:

### 1. Kéo update mới nhất từ github về
```bash
git checkout develop
git pull
```

### 2. Tạo nhánh mới để làm việc

>[!NOTE]
> Nhánh làm việc chính sẽ là nhánh `develop`, nhưng không code và push thẳng vào nhánh `develop` để tránh code đấm nhau (conflict)

Quy ước tên branch của mình sẽ như thế này:
```bash
git checkout -b task/<mã công việc>
```
Vd: `git checkout -b task/211`

### 3. Đọc hướng dẫn trong `docs`

Mỗi người sau khi hoàn thành công việc đều phải viết hướng dẫn chạy cho người sau, hoặc đơn giản hơn thì thêm phần của mình vào file hướng dẫn có sẵn.

Trong thư mục `docs` có 2 file chính: `setup.md` và `flow.md`:
+ Lần đầu ae chạy code thì làm theo hướng dẫn trong `setup.md`
+ Các lần sau thì ae sẽ đọc trong file `flow.md` để hiểu luồng tổng thể và các luồng phụ

### 4. Code

### 5. Viết tài liệu hướng dẫn

Như đã nói, ae sau khi code được cái gì, thì phải update hướng dẫn để người sau còn chạy được.

Chỉnh sửa file [`flow.md`](./flow.md), thêm luồng phụ của ae vào, cấu trúc giống mấy phần trên tôi đã viết, có gì ae viết chưa rõ tôi sẽ bảo ae bổ sung sau


### 6. Commit

Quy ước commit:
```bash
git commit -m "[<type>] <mã công việc> - <mô tả>"
```

Vd:
```bash
git commit -m "[feat] 211 - RSS crawler pipeline"
```

>[!NOTE]
> Thêm tính năng hoặc code mới thì để type là `feat`, còn sau đấy nếu có lỗi hoặc tôi review code rồi bảo ae sửa lại thì để là `fix`, hoặc chỉnh sửa tài liệu thì để là `docs`.

>[!NOTE]
> Nhớ check nếu có các file rác, cache, output sinh ra được từ luồng, ... thì để vào `.gitignore`


### 7. Đẩy code lên github và tạo PR

```bash
git push
```

Tạo PR, nhánh nguồn là nhánh phụ mấy ông đã tạo ở trên, nhánh đích là nhánh `develop`, xong nhắn trên nhóm tag tên tôi vào review

>[!WARNING]
> KHÔNG đụng vào nhánh `main`, đó là nhánh cuối cùng sau khi cả nhóm đã chốt và hoạt động được.
