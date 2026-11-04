import math, re

def measured_latency(seconds):
    return min(0.4, max(0, seconds)) if isinstance(seconds, (int, float)) and math.isfinite(seconds) else 0

def retry_delay(result, request_seconds, boundary_attempt=0):
    nominal = block_wait_seconds(result)
    reason = ' '.join((str(result.get(k, '')) for k in ('error', 'message')))
    match = re.search('Block too soon:\\s*(\\d+)s since prev \\(min (\\d+)s\\)', reason, re.I)
    if match:
        elapsed, minimum = map(int, match.groups())
        if elapsed >= minimum and boundary_attempt <= 5:
            return 0
        nominal = 1 if elapsed >= minimum else max(0.125, minimum - elapsed - 0.5)
    return max(0.025, nominal - measured_latency(request_seconds))

def next_window(now, request_seconds):
    return now + 180 - measured_latency(request_seconds) + 0.02

def block_wait_seconds(result):
    reason = ' '.join((str(result.get(k, '')) for k in ('error', 'message')))
    fair = re.search('Fair mining:.*other miners have (\\d+)s to win this one first', reason, re.I)
    if fair:
        return max(1, min(3600, int(fair.group(1))))
    match = re.search('Block too soon:\\s*(\\d+)s since prev \\(min (\\d+)s\\)', reason, re.I)
    if not match:
        return 1
    elapsed, minimum = map(int, match.groups())
    if elapsed >= minimum:
        return 0.25
    return max(1, min(3600, minimum - elapsed))

def select_public_chain(blocks, rejected_heads):
    ordered = sorted(blocks, key=lambda b: b['index'])
    highest = ordered[-1]['index']
    heads = [b for b in ordered if b['index'] == highest]
    if len(heads) > 1 and any((b['hash'] not in rejected_heads for b in heads)):
        ordered = [b for b in ordered if b['index'] != highest or b['hash'] not in rejected_heads]
    return ordered

def submission_kind(status_code, result):
    if status_code == 200 and result.get('status') == 'ok':
        return 'accepted'
    reason = ' '.join((str(result.get(k, '')) for k in ('status', 'error', 'message'))).lower()
    if 'block too soon:' in reason:
        return 'wait'
    if re.search('fair mining:.*other miners have \\d+s to win this one first', reason):
        return 'wait'
    if 'block must carry waiting transactions' in reason:
        return 'refresh'
    if re.search('wrong index\\s*[^\\w]*\\s*expected\\s+\\d+', reason):
        return 'stale'
    if re.search('block index \\d+ not next expected \\(\\d+\\)', reason):
        return 'stale'
    if 'prev hash mismatch' in reason:
        return 'stale'
    if any((word in reason for word in ('already exists', 'already known', 'stale', 'previous hash', 'previous_hash'))):
        return 'stale'
    return 'fatal'
