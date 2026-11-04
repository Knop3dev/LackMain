TARGET_SECONDS = 0.008

def align_batch(value, maximum, worksize):
    return max(worksize, min(maximum, int(value) // worksize * worksize))

def initial_batch(head_size, tail_size, digits, maximum, worksize):
    blocks = (head_size % 64 + digits + tail_size + 9 + 63) // 64
    predicted_rate = 750000000 * 6 / max(1, blocks)
    return align_batch(predicted_rate * TARGET_SECONDS, maximum, worksize)

def adjust_batch(count, seconds, maximum, worksize):
    desired = count * TARGET_SECONDS / max(1e-06, seconds)
    growth = min(count * 1.25, desired)
    if growth > count:
        growth = max(growth, count + worksize)
    return align_batch(growth, maximum, worksize)
