"""Checkpoint terminal shows operations and outcomes; tables stay in the store."""
import re


def compact_message(message):
    text = str(message).strip()
    if not text or text.startswith("[SUMMARY]"):
        return None
    if text.startswith(('[CHECK RESULT]', '[STATION]', '[DATA EXTRACTED]', '[CHECK METHOD]', '[DATA SUMMARY]', '[TABLE DATA]', '[CHECKPOINT]', '[NAVIGATE]', '[SEARCH]', '[CONFIG]', '[BROWSER]', '[PIPELINE START]', '[COMPLETE]')):
        return None
    if text.startswith(('[BYPASS]', '[SETTINGS]', '[PROGRESS]', '[RESULT]', '[DETAIL]', '[WARN]', '[ERROR]', '[STOP]', '[RESUME]', '[SKIP]', '[SKIP SUCCESS]', '[INTERRUPT]', '[TIMER]', '[LOGIN ONLY]', '[Wager Cal]', '[RELOAD]', '[Tier 3]', '[LOAD]', '[NOON FAST]')):
        return text.splitlines()[0]
    # Keep error explanations emitted by older page implementations.
    if re.search(r'^(?:❌|⚠️|\[ERROR|\[WARN)', text, re.IGNORECASE):
        return text.splitlines()[0]
    return None


def issue_details(stored, color, limit=5):
    """Describe only highlighted rows, with table, company/sport and values."""
    details = []
    for table in stored.get('tables', []):
        headers = table.get('headers', [])
        for row in table.get('rows', []):
            marked = [i for i, cell in enumerate(row) if isinstance(cell, dict) and cell.get('bg') == color]
            if not marked:
                continue
            def value(cell):
                return str(cell.get('text', '') if isinstance(cell, dict) else cell)
            fields = []
            if row and 0 not in marked:
                fields.append(value(row[0]))
            for index in marked:
                label = str(headers[index]) if index < len(headers) else f'列{index+1}'
                text = value(row[index])
                if label.lower() == 'status' or text.lower() in ('warning', 'warn', 'error', 'ok'):
                    continue
                fields.append(f'{label}={text}')
            if fields:
                details.append(table.get('title', '数据项') + '：' + '，'.join(fields))
    details = list(dict.fromkeys(details))
    result = details[:limit]
    if len(details) > limit:
        result.append(f'另有 {len(details)-limit} 项，请查看 Log Viewer')
    return result
