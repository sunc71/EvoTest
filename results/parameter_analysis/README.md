# Parameter Sensitivity Analysis (RQ3)

This directory contains data for RQ3 (§5.5) — sensitivity analysis of EvoTest's three key parameters.

## Files

| File | Description |
|------|-------------|
| `parameter_sensitivity.json` | All parameter sweep statistics (merge rates, retrieval rates) |
| `jit_relevance_manual.json` | Manual relevance annotation for triggered JIT retrieval cases |

## Field → Paper Mapping

### `parameter_sensitivity.json`

| JSON Path | Paper Reference | Description |
|-----------|----------------|-------------|
| `parameters.constraint_memory_merge_threshold.merge_rates` | **Figure 6(a)** | θ_c vs merge rate (%) |
| `parameters.constraint_memory_merge_threshold.unique_counts` | **Figure 6(a)** | θ_c vs unique entry count |
| `parameters.refinement_memory_merge_threshold.merge_rates` | **Figure 6(b)** | θ_r vs merge rate (%) |
| `parameters.refinement_memory_merge_threshold.unique_counts` | **Figure 6(b)** | θ_r vs unique entry count |
| `parameters.jit_retrieval_threshold.retrieval_rates` | **Figure 7** | τ vs retrieval rate (%) |
| `jit_relevance_analysis.data[0]` (τ=0.50) | **§5.5 Table** | Manual relevance: 5/124 triggered, 3/8 relevant (37.5%) |
| `jit_relevance_analysis.data[1]` (τ=0.60) | **§5.5 Table** | Manual relevance: 2/20 triggered, 6/6 relevant (100%) |

### `jit_relevance_manual.json`

Same content as `jit_relevance_analysis` above, provided as a standalone file for direct consumption.

## Reproducing Paper Numbers

```bash
# Figure 6(a): θ_c sensitivity
python3 -c "
import json
d = json.load(open('parameter_sensitivity.json'))
p = d['parameters']['constraint_memory_merge_threshold']
for t, m, u in zip(p['thresholds'], p['merge_rates'], p['unique_counts']):
    print(f'θ_c={t:.2f}  merge={m:.1f}%  unique={u}')
"

# Figure 6(b): θ_r sensitivity
python3 -c "
import json
d = json.load(open('parameter_sensitivity.json'))
p = d['parameters']['refinement_memory_merge_threshold']
for t, m, u in zip(p['thresholds'], p['merge_rates'], p['unique_counts']):
    print(f'θ_r={t:.2f}  merge={m:.1f}%  unique={u}')
"

# Figure 7: τ retrieval rate
python3 -c "
import json
d = json.load(open('parameter_sensitivity.json'))
p = d['parameters']['jit_retrieval_threshold']
for t, r in zip(p['thresholds'], p['retrieval_rates']):
    print(f'τ={t:.2f}  retrieval={r:.2f}%')
"
```

## Key Findings

| Parameter | Default | Paper Justification |
|-----------|:-------:|---------------------|
| θ_c = 0.80 | §5.5 | Balances storage efficiency (34.9% merge) with pattern diversity (97 unique entries) |
| θ_r = 0.85 | §5.5 | Conservative choice, retains 99.7% of debugging insights |
| τ = 0.60 | §5.5 | Balances retrieval frequency (3.96%) with precision (100% relevant at τ=0.60) |
