"""Validate shard audit coverage and collect disagreements without relabelling data."""
from collections import Counter
import json
from pathlib import Path

import polars as pl

from config import DATA_ARTIFACTS_DIR


def main():
    directory = Path(DATA_ARTIFACTS_DIR) / "filter_review_20261117" / "full_review"
    frames = []
    coverage = []
    for index in range(1, 4):
        shard = pl.read_parquet(directory / f"shard_{index}.parquet")
        path = directory / f"review_{index}.csv"
        if not path.exists():
            coverage.append({"shard": index, "expected": shard.height, "submitted": 0})
            continue
        review = pl.read_csv(path)
        required = {"article_key", "review_label", "review_reason", "review_basis"}
        if not required.issubset(review.columns):
            raise ValueError(f"{path.name}: missing {required - set(review.columns)}")
        review = review.select(sorted(required))
        assist_path = directory / f"review_{index}_assist.csv"
        if assist_path.exists():
            assist = pl.read_csv(assist_path).select(sorted(required))
            review = pl.concat([review, assist], how="vertical_relaxed")
        root_remaining_path = directory / "review_root_remaining.csv"
        if root_remaining_path.exists():
            root_remaining = pl.read_csv(root_remaining_path).filter(pl.col("shard") == index).select(sorted(required))
            review = pl.concat([review, root_remaining], how="vertical_relaxed")
        if review["article_key"].n_unique() != review.height:
            raise ValueError(f"{path.name}: duplicate article keys")
        extra = set(review["article_key"]) - set(shard["article_key"])
        if extra:
            raise ValueError(f"{path.name}: article keys outside assigned shard")
        invalid = review.filter(~pl.col("review_label").is_in(["accident", "not_accident", "uncertain"]))
        if invalid.height:
            raise ValueError(f"{path.name}: invalid labels")
        joined = shard.join(review.select(sorted(required)), on="article_key", how="left")
        joined = joined.with_columns(pl.lit(index).alias("review_shard"))
        frames.append(joined)
        coverage.append({"shard": index, "expected": shard.height,
                         "submitted": review.height,
                         "basis": dict(Counter(review["review_basis"].to_list()))})
    summary = {"shards": coverage, "expected": 20745,
               "submitted": sum(item["submitted"] for item in coverage),
               "note": "Agent screening is not independent human ground truth. Missing or automated-only rows are not manually reviewed."}
    if frames:
        all_rows = pl.concat(frames, how="diagonal_relaxed")
        all_rows.write_parquet(directory / "all_reviews.parquet")
        compact = all_rows.drop("content")
        compact.write_csv(directory / "all_reviews.csv")
        differences = compact.filter(pl.col("review_label").is_not_null() &
                                     (pl.col("review_label") != pl.col("current_label")))
        differences.write_csv(directory / "disagreements.csv")
        compact.filter((pl.col("current_label") != "accident") &
                       (pl.col("review_label") == "accident")).write_csv(directory / "potential_misses.csv")
        summary["labels"] = dict(Counter(compact["review_label"].drop_nulls().to_list()))
        summary["disagreements"] = differences.height
        adjudications_path = directory / "root_adjudications.csv"
        adjudicated = all_rows
        if adjudications_path.exists():
            adjudications = pl.read_csv(adjudications_path).select(
                "article_key", pl.col("review_label").alias("root_label"),
                pl.col("review_reason").alias("root_reason"),
                pl.col("review_basis").alias("root_basis"))
            if adjudications["article_key"].n_unique() != adjudications.height:
                raise ValueError("Duplicate root adjudications")
            adjudicated = all_rows.join(adjudications, on="article_key", how="left")
            adjudicated = adjudicated.with_columns(
                pl.coalesce("root_label", "review_label").alias("final_review_label"),
                pl.coalesce("root_reason", "review_reason").alias("final_review_reason"),
                pl.coalesce("root_basis", "review_basis").alias("final_review_basis"))
        else:
            adjudicated = adjudicated.with_columns(
                pl.col("review_label").alias("final_review_label"),
                pl.col("review_reason").alias("final_review_reason"),
                pl.col("review_basis").alias("final_review_basis"))
        adjudicated.write_parquet(directory / "adjudicated_reviews.parquet")
        compact_final = adjudicated.drop("content")
        compact_final.filter(
            (pl.col("final_review_label") != pl.col("current_label")) |
            (pl.col("final_review_label") == "uncertain")
        ).write_csv(directory / "priority_review.csv")
        compact_final.filter((pl.col("current_label") != "accident") &
                             (pl.col("final_review_label") == "accident")
                             ).write_csv(directory / "misses_after_adjudication.csv")
        compact_final.filter((pl.col("current_label") == "accident") &
                             (pl.col("final_review_label") == "not_accident")
                             ).write_csv(directory / "excluded_after_adjudication.csv")
        summary["after_adjudication"] = dict(Counter(
            compact_final["final_review_label"].drop_nulls().to_list()))
        summary["complete_row_coverage"] = summary["submitted"] == summary["expected"]
        summary["final_basis"] = dict(Counter(compact_final["final_review_basis"].drop_nulls().to_list()))
        summary["confirmed_additional_positives"] = compact_final.filter(
            (pl.col("current_label") != "accident") & (pl.col("final_review_label") == "accident")).height
        summary["old_positives_excluded"] = compact_final.filter(
            (pl.col("current_label") == "accident") & (pl.col("final_review_label") == "not_accident")).height
        summary["old_positives_to_uncertain"] = compact_final.filter(
            (pl.col("current_label") == "accident") & (pl.col("final_review_label") == "uncertain")).height
        root_path = directory / "review_root_remaining.csv"
        summary["root_continuation_rows"] = pl.read_csv(root_path).height if root_path.exists() else 0
        rules_path = directory / "rules_summary.json"
        if rules_path.exists():
            summary["automatic_rules"] = json.loads(rules_path.read_text(encoding="utf-8"))
        if summary["complete_row_coverage"]:
            if compact_final["final_review_label"].null_count():
                raise ValueError("Complete coverage cannot contain null final labels")
            reviewed = adjudicated.rename({name: "baseline_" + name for name in (
                "accident_label", "filter_reason", "filter_evidence", "filter_version") if name in adjudicated.columns})
            reviewed = reviewed.with_columns(
                pl.col("final_review_label").alias("accident_label"),
                pl.col("final_review_reason").alias("filter_reason"),
                pl.col("final_review_reason").alias("filter_evidence"),
                pl.lit("multiagent-root-reviewed-20261117").alias("filter_version"))
            reviewed.write_parquet(directory / "reviewed_classified.parquet")
            compact_final.filter(pl.col("final_review_label") == "accident").write_csv(directory / "reviewed_accidents.csv")
            compact_final.filter(pl.col("final_review_label") == "uncertain").write_csv(directory / "reviewed_uncertain.csv")
    (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report = ["# Rà soát toàn bộ tập bài — 17/11/2026", "",
              f"Đã có bản ghi sàng lọc cho **{summary['submitted']:,}/20.745 bài**.", "",
              "Ba agent GPT-6 Luna, mức suy luận max, rà các phần không trùng nhau; "
              "agent chính tiếp quản 5.080 bài còn lại khi các agent Luna chạm hạn mức. "
              "Nhãn agent là kết quả sàng lọc, không phải nhãn chuẩn do con người thẩm định độc lập.", "",
              "## Mức độ đọc", "",
              "`title_only`: agent đọc tiêu đề; `title_lead`: đọc tiêu đề và mô tả; "
              "`full_body`: đọc thân bài hoặc trang nguồn; `body_excerpt`: đọc trích đoạn thân bài. "
              "Không đồng nhất việc quét máy toàn văn với đọc kỹ toàn văn từng bài.", ""]
    for item in coverage:
        report.append(f"- Phần {item['shard']}: {item['submitted']}/{item['expected']}; "
                      f"mức đọc: {item.get('basis', {})}.")
    report.extend(["", "## Kết quả và giới hạn", "",
                   f"Sau đối chiếu bổ sung: `{summary.get('after_adjudication', {})}`.", "",
                   f"So với kết quả trước lượt rà này: thêm **{summary.get('confirmed_additional_positives', 0)} bài bị bỏ sót**, "
                   f"loại **{summary.get('old_positives_excluded', 0)} bài nhận nhầm**, "
                   f"chuyển **{summary.get('old_positives_to_uncertain', 0)} bài dương tính cũ** sang cần xem xét.", "",
                   f"Mức đọc sau kiểm tra chéo: `{summary.get('final_basis', {})}`.", "",
                   f"Bộ quy tắc tự động v5: `{summary.get('automatic_rules', {}).get('after', {})}`. "
                   "Đây là số nhãn do quy tắc tự sinh, khác với nhãn sau rà phạm vi ở trên. "
                   "Không dùng số đo trên tập vừa rà để tuyên bố độ chính xác 100%.", "",
                   "Phạm vi: tin tường thuật sự cố tai nạn đường bộ thực tế; loại bài thuần tố tụng, "
                   "thăm hỏi, điều trị, tư vấn, thống kê hoặc sự cố không liên quan người/xe đường bộ. "
                   "Một bản tin tổng hợp có mục tường thuật vụ tai nạn cụ thể được phân biệt với bài "
                   "tư vấn chỉ nhắc vụ cũ làm ví dụ. Không chỉ dựa vào chữ ‘điều tra’ hay ‘sà lan’ để loại.", "",
                   "Đầu vào có 1.724 bài thiếu thân bài. Các trường hợp thiếu bằng chứng hoặc nghi vấn "
                   "phạm vi được giữ riêng; không thể tuyên bố đã loại hết mọi khả năng bỏ sót.", "",
                   "Các tệp trong `data_artifacts/filter_review_20261117/full_review/`:", "",
                   "- `all_reviews.csv`: nhãn và căn cứ ban đầu của agent.",
                   "- `reviewed_classified.parquet`: đủ 20.745 bài, nhãn cuối ở `accident_label`; giữ nhãn cũ với tiền tố `baseline_`.",
                   "- `reviewed_accidents.csv`, `reviewed_uncertain.csv`: danh sách cuối có URL và lý do.",
                   "- `adjudicated_reviews.parquet`: đủ nội dung và kết luận sau kiểm tra chéo.",
                   "- `misses_after_adjudication.csv`: ứng viên tai nạn bộ lọc hiện tại bỏ sót.",
                   "- `excluded_after_adjudication.csv`: bài đang nhận là tai nạn nhưng bị loại sau rà.",
                   "- `priority_review.csv`: bất đồng và trường hợp chưa chắc chắn.",
                   "- `root_adjudications.csv`, `source_evidence/`: căn cứ kiểm tra chéo.", "",
                   "Đây là đầu ra audit riêng; chưa thay dữ liệu Bronze/Silver/Gold hay dashboard. "
                   "Trạng thái hoàn tất chỉ dựa trên đủ mã bài, không phải lời khẳng định recall 100%.", ""])
    Path("docs/ra_soat_toan_bo_20745_2026_11_17.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
