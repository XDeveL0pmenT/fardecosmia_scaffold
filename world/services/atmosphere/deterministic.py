def deterministic_unit(seed, step_index, cell_index, channel=0):
    """Stable pseudo-random value in [0, 1), independent of Python hash seed."""
    mask = (1 << 64) - 1
    value = (
        int(seed)
        ^ ((int(step_index) + 0x9E3779B97F4A7C15) & mask)
        ^ (((int(cell_index) + 1) * 0xBF58476D1CE4E5B9) & mask)
        ^ (((int(channel) + 1) * 0x94D049BB133111EB) & mask)
    ) & mask
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & mask
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & mask
    value ^= value >> 31
    return value / float(1 << 64)


def deterministic_signed(seed, step_index, cell_index, channel=0):
    return deterministic_unit(seed, step_index, cell_index, channel) * 2.0 - 1.0

