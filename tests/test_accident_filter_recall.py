"""Real failure categories and paraphrases; no article-key allowlists."""
import unittest

from filters.accident import classify_accident
from filters.run import filter_frame
from filters.evaluate import evaluate
import polars as pl


class AccidentRecallTests(unittest.TestCase):
    def test_full_audit_scope_boundaries(self):
        cases = [
            ("Clip: Đất sạt xuống quốc lộ", "Xe máy người đi đường bị vùi lấp.", None, "accident"),
            ("Hố tử thần nuốt chửng hai ô tô trên đường", None, None, "accident"),
            ("Sụt lún nghiêm trọng trên đường phố", None,
             "Mặt đường bị sụt. Xe bán tải đang chạy bị rơi xuống hố và mắc kẹt.", "accident"),
            ("Cận cảnh hố tử thần giữa thành phố", None,
             "Hai ôtô đậu ven đường bị sụt xuống hố, một xe mắc miệng hố.", "accident"),
            ("Sạt lở đường đèo gây chia cắt giao thông", None,
             "Đất đá tràn mặt đường. Không có xe máy bị vùi lấp. Lực lượng chức năng chặn đường.", "not_accident"),
            ("Sà lan tông cầu, đường sắt tê liệt", "Cầu bị hư hỏng.",
             "Xe máy đang trên cầu phần đường bộ bị đổ vào lan can khiến 6 người bị thương.", "accident"),
            ("Sà lan tông cầu, đường sắt tê liệt", "Không ai bị thương.",
             "Sà lan va chạm trụ cầu. Xe máy phải đi đường khác do cầu phong tỏa.", "not_accident"),
            ("Máy bay va chạm xe tải lúc hạ cánh", None,
             "Bụng của chuyến bay va trúng xe đầu kéo trên đường cao tốc. Tài xế xe tải bị thương.", "accident"),
            ("Máy bay va chạm xe cứu hỏa khi hạ cánh", None,
             "Máy bay va chạm xe cứu hỏa trên đường băng sân bay, nhiều người bị thương.", "not_accident"),
            ("NSND biểu diễn trong đêm nhạc", None,
             "Bản tin 60s có những tin sau. Xe khách rơi xuống vực sâu ở Sơn La, 7 người thương vong.", "accident"),
            ("Xem nhanh: Giá xăng có thể điều chỉnh", None,
             "Bản tin Xem nhanh có những mục sau:\nGiá xăng có thể điều chỉnh\nTàu SE8 va chạm xe tải tại đường ngang, tài xế bị thương.", "accident"),
            ("Lời khuyên lái xe an toàn", None,
             "Trước đây xe khách rơi xuống vực, 7 người thương vong. Cần chú ý khi lái xe.", "not_accident"),
            ("Điều tra vụ tai nạn trên quốc lộ khiến nam sinh tử vong", None,
             "Khoảng 11 giờ hôm qua, nam sinh lái xe máy lao xuống mương trên quốc lộ và tử vong tại chỗ.", "accident"),
            ("Khởi tố tài xế gây tai nạn chết người", None,
             "Khoảng 11 giờ hôm qua, xe tải va chạm xe máy khiến một người tử vong.", "not_accident"),
            ("Truy tìm xe tải gây tai nạn làm du khách tử vong", None,
             "Địa phương xác nhận vừa xảy ra tai nạn. Xe khách chạy trên quốc lộ thì đá từ xe tải rơi trúng kính, làm một người tử vong.", "accident"),
            ("Khống chế tài xế say xỉn gây TNGT liên hoàn trên phố", None,
             "Ô tô tông ba xe máy đỗ bên đường rồi lao vào rào chắn và kéo lê một xe máy.", "accident"),
            ("Ô tô vượt ẩu gây tai nạn rồi bỏ chạy, CSGT truy tìm tài xế",
             "Ô tô tông ngã xe máy trên đường.", None, "accident"),
            ("Xót xa chú rể gặp nạn trước ngày cưới", None,
             "Tối 29/3, lực lượng chức năng khám nghiệm vụ xe máy va chạm xe bồn khiến một người tử vong. Khoảng 18 giờ cùng ngày, xe máy tông xe bồn dừng bên đường.", "accident"),
            ("Xót xa chú rể gặp nạn trước ngày cưới", None,
             "Gia đình sống trong nỗi đau nhiều năm sau khi xe máy tông xe bồn khiến một người tử vong.", "not_accident"),
            ("Tây Ninh: Điều tra nguyên nhân 2 vụ tai nạn giao thông làm 4 người tử vong", None,
             "Khoảng 14 giờ cùng ngày, xe máy va chạm container làm hai người tử vong. Lúc 10 giờ xe tải va chạm xe máy làm hai người chết.", "accident"),
            ("Container đứt dây chằng, hàng rơi chắn đường", None,
             "Không có người ở gần, không xảy ra tai nạn.", "not_accident"),
            ("Ba người đi xe máy suýt chết khi bị bán tải tạt đầu", None,
             "Ô tô bán tải tạt đầu xe máy trên đường. Vụ việc khiến ba người đi xe máy ngã ra đường. Xe tải phía sau tránh được.", "accident"),
            ("Chống lệnh, lao xe vào tổ công tác làm cảnh sát bị thương", None, None, "not_accident"),
            ("Hai nạn nhân bị thương trong vụ xe tải tông xe máy đã tử vong", None, None, "not_accident"),
        ]
        for title, lead, body, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(classify_accident(title, lead, body).label, expected)

    def test_missed_actual_incident_wordings(self):
        cases = [
            ("Dòng người dầm mưa vì 2 ô tô va quệt không chịu rời đi ở TPHCM", "Một xe buýt va quệt với taxi trên đường Nguyễn Thị Thập."),
            ("Xe tải sụp hố trên đường Nguyễn Trãi", "Bánh xe lún sâu khi đang lưu thông."),
            ("Xe máy lọt hố trên đường, người lái bị thương", None),
            ("Tìm người làm đổ nhớt ra đường khiến nhiều người té ngã", "Tài xế làm đổ nhớt ra đường, khiến nhiều người té ngã."),
            ("Xe máy bị cuốn vào gầm xe tải, hai người thương vong", None),
            ("SUV lật 6 vòng trên cao tốc, hành khách thoát nạn", None),
            ("Xe buýt lật khiến nhiều người thương vong tại Brazil", None),
            ("Xe máy phóng nhanh đâm vỡ kính lái ô tô", None),
            ("Cắt ngang đầu ô tô giữa ngã tư, xe máy bị hất văng", None),
            ("Hai xe mô tô đấu đầu, một người tử vong", None),
            ("Tai nạn giao thông nghiêm trọng khiến ba người tử vong", None),
            ("Lửa bao trùm xe giường nằm đỗ bên đường", None),
            ("Xe buýt cháy rụi sau va chạm với tàu hỏa", None),
            ("Nam sinh bị xe tông sau va chạm với trâu thả rông", "Nam sinh đang đi xe máy trên đường thì va chạm với con trâu, ngã và bị xe tải tông."),
            ("Mảng vữa từ nhà ga rơi trúng xe buýt", "Xe buýt đang chạy trên đường thì bị mảng vữa rơi trúng, gây vỡ kính."),
            ("Người đi xe máy bị vướng dây nối giữa hai xe tải căng ngang đường", None),
            ("Nước chảy xiết cuốn ngã người đi xe máy trên đường", None),
            ("Ô tô lao vào khu vực thi công trên cao tốc", "Vụ tai nạn khiến ô tô hư hỏng nặng."),
            ("Cần máy xúc quật ngã hai người đi xe máy", "Xe máy đang đi trên đường thì bị cần máy xúc va chạm."),
            ("Container đứt dây chằng, hàng rơi chắn ngang đường", "Xe container đang lưu thông thì hàng hóa rơi xuống mặt đường."),
            ("Tai nạn giao thông 16/6: Xe khách cán người đi đường tử vong", "Khởi tố tài xế của một vụ cũ; một xe khách cán người trên đường sáng nay."),
        ]
        for title, lead in cases:
            with self.subTest(title=title):
                self.assertEqual(classify_accident(title, lead).label, "accident")

    def test_main_topic_exclusions_even_with_crash_in_body(self):
        body = "Hôm qua xe tải va chạm xe máy trên quốc lộ khiến hai người tử vong."
        cases = [
            "Honda sắp có xe bán tải đối đầu đối thủ?",
            "Giải mã nút có biểu tượng xe va chạm trên ô tô",
            "Xe máy điện an toàn như ô tô, có va chạm cũng không dễ văng ra",
            "Thử nghiệm va chạm để đánh giá độ an toàn xe SUV",
            "Toàn quốc xảy ra 381 vụ tai nạn giao thông trong 9 ngày nghỉ Tết",
            "Số người tử vong do TNGT giảm 23%",
            "Thăm hỏi gia đình nạn nhân vụ tai nạn giao thông",
            "Tài xế gây tai nạn lãnh 30 tháng tù giam",
            "Thủ tướng yêu cầu điều tra nguyên nhân vụ tai nạn",
            "Doanh nghiệp xe buýt chuyển đổi sang xe điện",
            "CSGT khuyến cáo sau vụ xe máy bị cuốn vào gầm container",
            "Khởi tố người điều khiển xe gây tai nạn",
            "Tai nạn đường sắt tại Tây Ban Nha, tàu cao tốc trật bánh",
            "Xe lu cán công nhân trên công trường đang thi công",
            "Xe tăng húc vào phương tiện của lực lượng gìn giữ hòa bình",
            "Cứu sống bệnh nhân chấn thương nặng sau tai nạn giao thông",
            "Cháy lớn tại bãi giữ ô tô, nhiều xe trơ khung",
            "Gặp xe hỏng, vật cản trên đường có vạch liền: Ô tô được lấn vạch để tránh?",
        ]
        for title in cases:
            with self.subTest(title=title):
                self.assertEqual(classify_accident(title, None, body).label, "not_accident")

    def test_near_miss_is_not_actual_and_real_impact_is_preserved(self):
        for title in ["Người đi xe máy suýt bị ô tô tông trúng", "Ô tô suýt bị lũ cuốn trôi", "Xe máy chở ba suýt gặp tai nạn"]:
            self.assertEqual(classify_accident(title).label, "not_accident")
        self.assertEqual(classify_accident("Ô tô lật ngửa trên đường, tài xế suýt chết").label, "accident")
        self.assertEqual(classify_accident("Xe tải húc ô tô, suýt gây họa cho người đi bộ").label, "accident")

    def test_body_and_second_description_sentence_reach_pipeline(self):
        frame = pl.DataFrame({"title": ["Ô tô tự chạy, tài xế hô hoán"],
                              "description": ["Tài xế đứng bên ngoài chiếc ô tô."],
                              "content": ["Ô tô tự chạy trên đường. Chiếc xe đâm vào xe đẩy bên đường, làm người bán hàng bị thương."]})
        self.assertEqual(filter_frame(frame)["accident_label"][0], "accident")
        self.assertEqual(classify_accident("Sự cố ở ngã tư", "Ô tô đang đi qua giao lộ. Xe máy lao tới đâm mạnh vào ô tô, làm một người bị thương.").label, "accident")
        metrics, _ = evaluate([{"sample_id": "body", "label": "accident", **frame.row(0, named=True)}])
        self.assertEqual(metrics["recall_accident"], 1)


if __name__ == "__main__":
    unittest.main()
