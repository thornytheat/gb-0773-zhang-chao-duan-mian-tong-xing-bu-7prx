import hashlib
import json

from app.config import RULES


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def batch_sha256(reports):
    content = {name: [row['raw'] for row in table] for name, table in reports['readings']['tables'].items()}
    return digest(canonical(content))


def manifest(sources, reports, started, elapsed_ms):
    inputs = {name: digest(content) for name, content in sources.items()}
    batch = batch_sha256(reports)
    run_id = digest(canonical([RULES, batch]))
    return dict(run_id=run_id, intake_id=digest(canonical(sources)), inputs=inputs, batch_sha256=batch,
                rule_version=RULES, result_sha256=digest(canonical(reports)),
                started_at=started, elapsed_ms=elapsed_ms)
