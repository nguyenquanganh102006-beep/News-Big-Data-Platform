"""Replay real extracted Silver into a fresh database, with external pair labels.

Labels are supplied by an annotator, never derived from matcher predictions.
Abstentions on positive pairs count as misses so recall cannot be inflated by
sending difficult reports to review.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import duckdb

from config import MatchConfig
from .adapter import json_text
from .run import load_silver_articles, run_events


def evaluate(input_dir, output_dir, labels_path=None, config=None):
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    paths = {p.stem: p for p in sorted(input_dir.glob('*.parquet'))}
    if not paths:
        paths = {p.parent.name: p for p in sorted(input_dir.glob('*/extracted.parquet'))}
    if not paths:
        raise ValueError('No extracted Silver Parquet inputs found')
    articles = load_silver_articles(paths)
    keys = {a['article_key'] for a in articles}
    labels = json.loads(Path(labels_path).read_text()) if labels_path else None
    if labels is not None:
        if not isinstance(labels.get('provenance'), str) or not labels['provenance'].strip():
            raise ValueError('Pair labels must identify their annotation provenance')
        seen = set()
        for pair in labels['pairs']:
            if type(pair['same_event']) is not bool:
                raise ValueError('same_event must be a boolean')
            if pair['left'] == pair['right'] or not {pair['left'], pair['right']} <= keys:
                raise ValueError('Pair must reference two different input article keys')
            key = tuple(sorted((pair['left'], pair['right'])))
            if key in seen:
                raise ValueError('Duplicate pair annotation')
            seen.add(key)
    checks = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.values()}
    # Never reclassify or overwrite a production/previously evaluated database.
    output_dir.mkdir(parents=True, exist_ok=False)
    config = config or MatchConfig()
    first = run_events(paths, output_dir / 'events.duckdb', output_dir / 'exports', config)
    replay = run_events(paths, output_dir / 'events.duckdb', output_dir / 'exports', config)
    if first['database'] != replay['database']:
        raise AssertionError('Replay changed event/review counts')
    with duckdb.connect(str(output_dir / 'events.duckdb'), read_only=True) as connection:
        assignments = dict(connection.execute('SELECT article_key,event_id FROM event_articles').fetchall())
        groups = connection.execute(
            'SELECT l.event_id,list(a.title ORDER BY a.title),count(*) FROM event_articles l '
            'JOIN articles a USING(article_key) GROUP BY l.event_id HAVING count(*)>1 ORDER BY l.event_id').fetchall()
    metrics, pairs = None, []
    if labels:
        tp = fp = fn = tn = abstained = 0
        for pair in labels['pairs']:
            left, right = assignments.get(pair['left']), assignments.get(pair['right'])
            predicted = left is not None and left == right
            review = left is None or right is None
            actual = pair['same_event']
            tp += predicted and actual
            fp += predicted and not actual
            fn += not predicted and actual
            tn += not predicted and not actual and not review
            abstained += review
            pairs.append({**pair, 'predicted_same_event': predicted, 'abstained': review,
                          'left_event': left, 'right_event': right})
        metrics = {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn, 'abstained_pairs': abstained,
                   'precision': tp / (tp + fp) if tp + fp else None,
                   'recall_including_abstentions': tp / (tp + fn) if tp + fn else None,
                   'annotation_provenance': labels['provenance']}
    for path, checksum in checks.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != checksum:
            raise AssertionError('Input data changed')
    result = {'config': asdict(config), 'input_sha256': checks, 'first': first, 'replay': replay,
              'groups': groups, 'metrics': metrics, 'pairs': pairs}
    (output_dir / 'results.json').write_text(json_text(result) + '\n')
    lines = ['# Đánh giá gom sự kiện trên Silver thật', '', f'Kết quả: `{json_text(first)}`', '',
             'Đầu vào giữ nguyên SHA-256; chạy lại giữ nguyên số sự kiện/liên kết/hàng chờ.', '']
    if metrics:
        lines += [f'Nguồn nhãn: {labels["provenance"]}', '', f'Đối chiếu cặp: `{json_text(metrics)}`', '',
                  'Nhãn tạm dùng để phân tích lỗi không thay thế tập kiểm định độc lập đã được người duyệt xác nhận.', '']
    for event, titles, count in groups:
        lines += [f'## {event} — {count} bài', ''] + [f'- {title}' for title in titles] + ['']
    (output_dir / 'report.md').write_text('\n'.join(lines))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='New, non-existing evaluation directory')
    parser.add_argument('--labels', type=Path)
    parser.add_argument('--semantic-model')
    parser.add_argument('--model-cache')
    args = parser.parse_args()
    result = evaluate(args.input_dir, args.output_dir, args.labels,
                      MatchConfig(semantic_model=args.semantic_model, semantic_cache_dir=args.model_cache))
    print(json_text({'first': result['first'], 'metrics': result['metrics']}))


if __name__ == '__main__':
    main()
