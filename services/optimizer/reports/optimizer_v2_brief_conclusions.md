# Optimizer v2 Brief Conclusions

Source dataset: `services/optimizer/reports/optimizer_v2_makespan_comparison.csv`

Scope: 53 weekly windows. All v2 solutions are valid: every graph node is visited once, no incompatible line assignments, no drops.

## Mean Results

| Metric | Mean hours/week |
|---|---:|
| v2 makespan | 85.03 |
| Real simulated: node + inefficiency + edge | 158.54 |
| Real cleaning hours | 13.77 |
| Real maintenance/rerun hours | 50.29 |

## Corrected Savings

If the same weekly inefficiency, cleaning, or maintenance burden is added to both real and v2 **after** makespan, it cancels mathematically.

| Comparison | Mean saving |
|---|---:|
| Raw v2 vs real simulated | 73.52 h/week |
| Same-burden adjusted incl. cleaning | 73.52 h/week |
| Same-burden adjusted incl. cleaning + maintenance/rerun | 73.52 h/week |

## Conservative Stress Test

If historical inefficiency and cleaning are replayed **per line before taking the max**, the bottleneck line can change. This is not a cancelling adjustment; it is a pessimistic line-bottleneck stress test.

| Stress test | Mean saving | Weeks won |
|---|---:|---:|
| v2 + line-specific cleaning + inefficiencies | 23.15 h/week | 49 / 53 |
| Same, incl. line-specific maintenance/rerun | 14.15 h/week | 38 / 53 |

## Mixed Comparison

If we compare **v2 adjusted** against **real not simulated** (`real WO total + edge`), the saving changes because only v2 receives the simulated burden.

| Comparison | Mean saving | Weeks won |
|---|---:|---:|
| Real not simulated vs v2 + cleaning + real inefficiencies | 18.35 h/week | 43 / 53 |

Do not mix this up with the same-burden comparison above. This is useful as a conservative check, but it is not a pure cancellation test.

## Conclusion

The clean routing/productive-time result is **73.52 h/week saved**, winning **53 of 53** weeks.

If the business wants to add the same historical burden to both plans, the saving remains **73.52 h/week** because the burden cancels.

Use **23.15 h/week** only as a conservative stress-test result where historical line-specific inefficiencies are imposed before the makespan calculation.

Use **18.35 h/week** when comparing adjusted v2 against real observed (`WO total + edge`) without simulating the real side.

Best demo wording: **LineWise v2 saves about 73.5 productive routing hours per week; under a pessimistic line-specific inefficiency replay, it still saves about 23.2 operating hours per week.**
