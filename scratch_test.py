import random
from collections import Counter

# Simulate rap song word durations
durations = [round(random.uniform(0.12, 0.24), 2) for _ in range(500)]
counts = Counter(durations)
print(counts.most_common(3))
