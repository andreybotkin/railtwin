def interpolate_progress(raw_reference: list[float | None]) -> list[float]:
    total_stops = len(raw_reference)
    if all(p is None for p in raw_reference):
        return [float(i) / max(1, total_stops - 1) for i in range(total_stops)]
    
    result = list(raw_reference)
    for i in range(total_stops):
        if result[i] is None:
            left_idx = i - 1
            while left_idx >= 0 and raw_reference[left_idx] is None:
                left_idx -= 1
            right_idx = i + 1
            while right_idx < total_stops and raw_reference[right_idx] is None:
                right_idx += 1
                
            left_val = raw_reference[left_idx] if left_idx >= 0 else None
            right_val = raw_reference[right_idx] if right_idx < total_stops else None
            
            if left_val is not None and right_val is not None:
                span = right_idx - left_idx
                result[i] = left_val + (right_val - left_val) * ((i - left_idx) / span)
            elif left_val is not None:
                result[i] = left_val
            elif right_val is not None:
                result[i] = right_val
    return result

print(interpolate_progress([1.0, 0.5, None, 0.0]))
print(interpolate_progress([1.0, None, 0.0]))
print(interpolate_progress([None, 0.8, 0.6, None]))
print(interpolate_progress([None, None, 0.5]))
