# Optimizer v1 vs v2 Comparison

Generated at: `2026-05-24T10:05:50`

## Configuration

- v1 source: `services/optimizer/graph/line_partitioner.py`
- v2 source: `services/optimizer/app/implementacion_v2.py` via existing `optimizer_v2_makespan_comparison.csv`
- v1 `time_budget_s`: 4.0
- v1 `move_strategy`: first_improvement
- v1 `delta_balance_h`: 0.5
- v1 `max_no_improve`: 20
- Runtime: 267.3 s

## Mean Results

                         metric  v1_mean_h  v2_mean_h  v1_minus_v2_h
                   raw makespan  82.277753  85.025311      -2.747558
              optimal simulated 139.915971 140.539507      -0.623536
optimal simulated + maintenance 163.177556 163.070000       0.107556

Positive `v1_minus_v2_h` means v1 is slower; negative means v1 is better.

## Win Counts

- Raw makespan: v1 wins 37/53, v2 wins 16/53, ties 0.
- Optimal simulated: v1 wins 32/53, v2 wins 21/53, ties 0.
- Valid v1 windows: 53/53
- Valid v2 windows: 53/53

## Best v1 Advantages

  window_id  v1_optimal_simulated_makespan_hours  v2_optimal_simulated_makespan_hours  optimal_simulated_delta_v1_minus_v2_hours
2025-W10-7d                           145.411540                           166.263693                                 -20.852153
2025-W14-7d                           167.294900                           182.327922                                 -15.033022
2025-W19-7d                           202.263466                           212.212254                                  -9.948788
2025-W16-7d                           154.303984                           160.812907                                  -6.508923
2025-W38-7d                           204.783858                           210.086927                                  -5.303069
2025-W35-7d                           199.237737                           204.164196                                  -4.926459
2025-W23-7d                           148.108325                           152.809843                                  -4.701518
2025-W04-7d                           119.812040                           123.657702                                  -3.845662

## Best v2 Advantages

  window_id  v1_optimal_simulated_makespan_hours  v2_optimal_simulated_makespan_hours  optimal_simulated_delta_v1_minus_v2_hours
2025-W28-7d                           229.381484                           216.287341                                  13.094143
2025-W27-7d                           161.788393                           150.633284                                  11.155109
2025-W42-7d                           182.029837                           176.066122                                   5.963715
2025-W11-7d                           124.061409                           118.254910                                   5.806499
2025-W51-7d                           123.444464                           117.790270                                   5.654195
2025-W41-7d                           157.069146                           152.458085                                   4.611060
2025-W45-7d                           132.397620                           128.714984                                   3.682635
2025-W47-7d                           115.318213                           112.066377                                   3.251836

