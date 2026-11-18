"""Summarize only recorded real runs, verify cross-architecture facts/queries."""
import json
from pathlib import Path

import pandas as pd


def main():
    base = Path(__file__).resolve().parent
    directory = base / "results"
    runs = pd.read_csv(directory / "runs.csv")
    assert runs["run_id"].is_unique
    columns = ["total_duration_s", "throughput_articles_s", "latency_p50_ms", "latency_p95_ms",
               "peak_ram_mb", "avg_cpu_pct", "query_p95_ms", "snapshot_export_s", "drain_s"]
    comparable = runs[runs["workload"] != "smoke"]
    assert not comparable.empty
    summary = comparable.groupby(["architecture", "workload"])[columns].agg(["median", "min", "max", "std"])
    summary.columns = [f"{metric}_{statistic}" for metric, statistic in summary.columns]
    summary.insert(0, "repeats", comparable.groupby(["architecture", "workload"]).size())
    summary.to_csv(directory / "summary.csv")
    cross_checks = []
    for workload, group in runs.groupby("workload"):
        assert group["output_digest"].nunique() == 1, f"Different facts: {workload}"
        reference = None
        for run in group.itertuples():
            queries = json.loads((base / "work" / run.run_id / "queries.json").read_text(encoding="utf-8"))
            # PostgreSQL's locale collation and DuckDB's binary collation order
            # Vietnamese names differently; compare rows, not presentation order.
            facts = {key: sorted(data["rows"], key=lambda row: json.dumps(row, ensure_ascii=False))
                     for key, data in queries.items()}
            if reference is None:
                reference = facts
            assert facts == reference, f"Different analytics answers: {run.run_id}"
        cross_checks.append(f"{workload}: {len(group)} runs, deterministic output digest and all SQL answers agree")
    correct = ((runs["output_count"] == runs["input_count"]) & runs["missing_count"].eq(0)
               & runs["duplicate_count"].eq(0) & runs["failed_count"].eq(0) & runs["retry_pass"].eq(True))
    required = ["B0", "A2", "A4", "A5"]
    dod = all(((runs["architecture"] == architecture) & (runs["workload"] == workload) & correct).any()
              for architecture in required for workload in ["T1", "T2"])
    lines = ["# Benchmark baseline B0 / A2 / A4 / A5 — kết quả chạy thật", "",
             f"Definition of Done (T1/T2 đủ cả bốn cấu hình): **{'đạt' if dod else 'chưa đạt'}**.", "",
             "## Phạm vi", "",
             "Dữ liệu thật: 20.745 bài Silver từ 7 nguồn; 322 bài nhãn tai nạn, 35 chưa rõ, 20.388 bài khác. "
             "Các workload dùng cùng N bài đầu theo thứ tự thời gian/khóa. Đây không phải 20K vụ tai nạn.", "",
             "Đo broker (Redis/Kafka) → parse → cùng transform Python/Polars → storage commit. "
             "Lọc/trích xuất đã tính trước; không chạy matching hoặc embedding trong phép đo. "
             "A4/A5 dùng foreachBatch chuyển batch về một driver để chạy cùng logic, không đo khả năng mở rộng matching phân tán.", "",
             "**B0 = Redis + Python/Polars + DuckDB**: dùng trực tiếp ArticleQueue của src/streaming/queue.py "
             "(LPUSH, BRPOPLPUSH sang processing, Lua ACK sau commit), một consumer, một bài/transaction như consumer hiện hành. "
             "Chỉ payload/transform/schema dùng chung với benchmark; không chạy nguyên ArticleProcessor lọc/trích xuất/matching. "
             "A2 gom tối đa 512 bài/transaction, nên so sánh B0/A2 phản ánh cả broker và cách commit, không tách riêng tốc độ broker. "
             "Redis bật AOF everysec như compose chính; ACK không bảo đảm fsync từng message khi mất điện.", "",
             "Một partition Kafka, Spark local[1], worker 2 CPU/5 GiB. Storage/checkpoint/snapshot trên volume Linux Docker, "
             "không ghi DB qua OneDrive. T1: 1K bài @50/s; T2: 10K @200/s; T3: 20K gửi nhanh nhất có thể. "
             "Thông số phần cứng và image thực tế trong environment.json. Ingestion không gồm tải package/khởi động Spark; "
             "lần microbatch/storage đầu tiên vẫn có chi phí khởi tạo. Đây là single-host benchmark.", "",
             "## Median các lần chạy", "",
             "| Kiến trúc | Tải | Lần | Thời gian (s) | Bài/s | p95 (ms) | RAM đỉnh (MiB) | CPU (%) | Query p95 (ms) | Xuất snapshot (s) |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for (architecture, workload), row in summary.iterrows():
        fields = ["total_duration_s", "throughput_articles_s", "latency_p95_ms", "peak_ram_mb", "avg_cpu_pct", "query_p95_ms", "snapshot_export_s"]
        lines.append(f"| {architecture} | {workload} | {int(row['repeats'])} | " + " | ".join(f"{row[f + '_median']:.2f}" for f in fields) + " |")
    lines += ["", "Độ dao động min/max/std cho từng metric nằm trong summary.csv. "
              "T1/T2 bị giới hạn tốc độ producer; throughput gần 50/200 bài/s không phải trần năng lực hệ thống.", "",
              "## Correctness và giới hạn", "",
              f"- {int(correct.sum())}/{len(runs)} runs hợp lệ có đủ output, không mất/trùng bài và qua thử ghi lại batch đã commit.",
              *[f"- {line}." for line in cross_checks],
              "- Latency dùng timestamp ngay trước send đến timestamp ngay sau commit trả về, cùng clock Linux. "
              "Không dùng processed_at để giả làm committed_at.",
              "- Retry ở đây là phát lại cùng microbatch sau commit; chưa kiểm thử kill/restart tiến trình, mất broker hoặc mất điện. "
              "Không coi kết quả này là bằng chứng phục hồi production đầy đủ.",
              "- RAM/CPU là tổng worker + broker đang dùng (Redis với B0, Kafka với A2/A4/A5) + PostgreSQL trong khoảng ingestion. "
              "PostgreSQL chạy idle ở B0/A2/A5 để giữ phạm vi đo phụ trợ như trước. Kafka không được cộng vào baseline Redis. CPU 100%=một core. "
              "RAM là working set lấy mẫu, không gồm overhead VM/Windows. Các run ngắn có ít mẫu hơn; xem resource_samples/logs.",
              "- A5 ingestion dừng ở commit Delta. Xuất snapshot Parquet đo riêng; query DuckDB trên snapshot. "
              "Không gộp snapshot_export_s vào ingestion latency.",
              "- Đầu ra là schema gọn có khóa bài, tiêu đề, hash nội dung và các trường đã định nghĩa; không lưu toàn văn. "
              "Kết quả storage/query không đại diện cho kho lưu toàn bộ thân bài hay full-text search.",
              "- Các tập tải là prefix theo thời gian của cùng dataset, không phải mẫu cân bằng nguồn/tỉnh. "
              "T3 nếu chỉ có một lượt thì chưa đủ để ước lượng độ dao động; xem cột Lần trong bảng.",
              "- Spark giới hạn 512 offset/trigger, trigger 1 giây; A2 flush ngay khi đủ 512 hoặc hết thời gian chờ 1 giây. "
              "T3 vì vậy có cả ảnh hưởng lịch microbatch/cấu hình giới hạn, không phải phép đo trần riêng của từng storage engine.",
              "- Cùng ba SQL đếm bài theo nguồn, nhãn và tỉnh/ngày đăng; warm-up một lần, đo 15 lần/query. "
              "query_p95_ms là pooled p95; truy vấn theo event bị bỏ qua vì event_id chưa có nhãn đáng tin, không bịa số vụ.",
              "- Các pilot trước khi chuẩn hóa volume và trước khi chuyển A2 sang ghi batch Arrow được lưu riêng trong pilot_*.csv, không đưa vào so sánh.",
              "- Baseline Redis đệm commit ledger để tránh flush Windows bind mount sau từng bài. Các lượt Redis dùng log line-buffered "
              "được giữ trong pilot_b0_linebuffered.csv và loại khỏi bảng chính. Số đo Kafka cũ vẫn giữ nguyên; lượt A2 đối chứng "
              "với log đệm được báo cáo riêng nếu có, nhằm kiểm tra độ lệch giữa hai đợt đo.",
              "- Lỗi phát triển và smoke thất bại vẫn có log trong results/logs; failed_count trong runs.csv là số bài lỗi của run đã hoàn thành, "
              "không phải tổng mọi lần khởi động thất bại trong lúc phát triển.", "",
              "## Đề xuất", ""]
    t2 = comparable[comparable["workload"] == "T2"]
    if not t2.empty:
        best = t2.groupby("architecture")["throughput_articles_s"].median().idxmax()
        lines.append(f"Trong phép đo chung hiện tại, **{best}** có median throughput T2 cao nhất. "
                     "Chỉ áp dụng cho cấu hình và workload trên; chưa đủ để kết luận kiến trúc nào thắng khi chạy matching thật hoặc scale-out. "
                     "Nếu chênh lệch nhỏ giữa B0 và A2, cân nhắc giữ Redis đang có để giảm chi phí chuyển đổi; "
                     "nếu cần Kafka thì A2 đơn giản hơn Spark. Chưa chứng minh được ngưỡng workload mà Spark bắt đầu có lợi.")
        if "B0" in set(t2["architecture"]):
            lines.append("B0 xử lý từng bài còn A2 gom batch, vì vậy chưa thể quy chênh lệch throughput cho Redis/Kafka. "
                         "Nếu giữ stack hiện tại và cần tăng tải, nên thử gom batch/giảm số transaction trên Redis trước khi quyết định đổi broker. "
                         "Đối chiếu cả độ trễ T1, không chỉ throughput T2/T3.")
    control_file = directory / "baseline_control.csv"
    if control_file.exists():
        controls = pd.read_csv(control_file)
        reference_digest = runs.loc[runs["workload"] == "T2", "output_digest"].iloc[0]
        assert controls["output_digest"].eq(reference_digest).all()
        assert controls["output_count"].eq(controls["input_count"]).all()
        lines += ["", "## A2 đối chứng cùng đợt baseline", "",
                  f"Chạy thêm {len(controls)} lượt A2/T2 với commit ledger có đệm: "
                  f"**{controls['throughput_articles_s'].median():.2f} bài/giây**, "
                  f"p95 **{controls['latency_p95_ms'].median():.2f} ms**. "
                  "Digest đầu ra khớp T2 cũ; dữ liệu kiểm tra đầy đủ ở baseline_control.csv. "
                  "Lượt đối chứng được giữ riêng, không trộn vào median ba lượt Kafka ban đầu."]
    residual_file = directory / "baseline_residual_queues.json"
    if residual_file.exists():
        residual = json.loads(residual_file.read_text(encoding="utf-8"))
        if residual:
            memory = sum(row.get("memory_bytes") or 0 for row in residual) / 1048576
            entries = sum(row.get("entries") or 0 for row in residual)
            lines += ["", "### Trạng thái Redis và giới hạn RAM", "",
                      f"Sau đo còn **{entries} message pilot** ở namespace của lượt đã hủy, Redis báo khoảng "
                      f"**{memory:.2f} MiB** bộ nhớ key. Chúng không được tiêu thụ bởi các queue mới, không thuộc output của 7 lượt baseline. "
                      "Số RAM baseline là working set quan sát thực tế, có cả phần tồn này; không trừ hậu nghiệm hoặc coi là footprint của một Redis sạch. "
                      "Cần reset namespace pilot trước khi dùng phép đo lại để so RAM nghiêm ngặt. Chi tiết ở baseline_residual_queues.json."]
    matching_file = directory / "matching_python.csv"
    if matching_file.exists():
        matching = pd.read_csv(matching_file)
        metadata = json.loads((directory / "matching_python_manifest.json").read_text(encoding="utf-8"))
        lines += ["", "## Matching Python đo riêng", "",
                  f"Chạy {len(matching)} lần trên **322 bài nhãn tai nạn**, dùng pipeline canonical hiện có trên Windows host, "
                  f"median **{matching['duration_s'].median():.3f} giây**, **{matching['articles_s'].median():.2f} bài/giây**. "
                  f"Warm-up model/cache **{metadata['warmup_s']:.3f} giây** được ghi riêng, không cộng vào median.", "",
                  f"Model: `{metadata['config']['semantic_model']}`. Kết quả mỗi lần: "
                  f"{int(matching.iloc[0]['new_event'])} vụ mới, {int(matching.iloc[0]['matched'])} bài ghép vào vụ có sẵn, "
                  f"{int(matching.iloc[0]['needs_review'])} bài chờ review. Đây là kiểm tra kế toán và thời gian, không phải đánh giá độ chính xác matching.", "",
                  "Phép đo riêng này không có Kafka/Spark và không cùng workload/hệ điều hành với bảng A2/A4/A5. "
                  "Không dùng nó để suy ra throughput matching của Spark hay cộng cơ học các throughput. "
                  "Xem matching_python.csv và matching_python_manifest.json để biết cấu hình/model fingerprint."]
    lines += ["", "## Biểu đồ", "", "![Throughput, latency và RAM](comparison.png)", "", "## Chạy lại và nguồn", "",
              "Xem [README](../README.md) để dựng stack, chuẩn bị dữ liệu, chạy suite và xem giới hạn đo. "
              "Mọi run_id trong runs.csv có correctness.json, queries.json, commits.jsonl và metrics.json ở work/<run_id>/.", "",
              "Tài liệu chính thức: [Kafka Docker](https://kafka.apache.org/39/getting-started/docker/), "
              "[Spark Kafka](https://spark.apache.org/docs/3.5.6/structured-streaming-kafka-integration.html), "
              "[Delta foreachBatch](https://docs.delta.io/delta-streaming/)."]
    (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), layout="constrained")
    for axis, metric, label in zip(axes, ["throughput_articles_s", "latency_p95_ms", "peak_ram_mb"],
                                   ["Throughput (articles/s)", "Latency p95 (ms)", "Peak container RAM (MiB)"]):
        pivot = comparable.pivot_table(index="workload", columns="architecture", values=metric, aggfunc="median")
        pivot = pivot.reindex(columns=[c for c in ["B0", "A2", "A4", "A5"] if c in pivot])
        pivot.plot.bar(ax=axis, rot=0, color=["#7851a9", "#167c80", "#527bb4", "#c6933a"])
        axis.set_title(label)
        if metric == "latency_p95_ms":
            axis.set_yscale("log")
            axis.set_title("Latency p95 (ms, log scale)")
        axis.set_xlabel("Workload")
        axis.grid(axis="y", alpha=.2)
    fig.suptitle("Redis/Kafka → common transform → committed storage · single host")
    fig.savefig(directory / "comparison.png", dpi=180)
    plt.close(fig)
    print(summary.to_string())
    print("DoD:", dod)


if __name__ == "__main__":
    main()
