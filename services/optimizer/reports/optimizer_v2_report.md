# Optimizer v2 weekly benchmark

Generated at: `2026-05-24T09:11:20`

## Configuration

- `max_iterations`: 2
- `max_exact_nodes`: 15
- `enable_swaps`: True
- `max_swap_candidates`: 20
- `enable_balance_repair`: True
- `balance_delta_hours`: 8.0
- Runtime: 168.8 s

## Coverage validation

- Weeks evaluated: 53
- Valid v2 solutions: 53/53
- Invalid v2 solutions: 0
- Mean nodes per week: 32.0

A solution is valid only when every planning-graph node is visited exactly once, no node appears on an incompatible line, and no SKU is dropped.

## Global time summary

- Mean v2 makespan: 85.03 h
- Mean real makespan: 109.60 h
- Mean makespan saved: 24.58 h
- Mean v2 total line-hours: 241.51 h
- Mean real total line-hours: 255.46 h
- Mean total line-hours saved: 13.94 h
- Mean changeover hours saved: 9.47 h

## Historical wall-clock sensitivity

`real_makespan_hours` above is the route-comparison metric: production running time plus estimated changeovers. The rows below add historical inefficiency layers from `wo_master.total_hours`.

- Mean real production wall-clock makespan: 139.60 h
- Mean real full wall-clock makespan: 158.15 h
- Mean real production wall-clock + changeover makespan: 158.89 h
- Mean real full wall-clock + changeover makespan: 177.15 h
- Mean wall-clock makespan saved vs v2: 73.13 h
- Mean production inefficiency hours per week: 124.29 h
- Mean cleaning WO hours per week: 13.77 h
- Mean maintenance/rerun WO hours per week: 50.29 h

## Production-line totals

 line_id  mean_v2_total_hours  max_v2_total_hours  mean_real_total_hours  max_real_total_hours  mean_real_all_wo_wall_hours  max_real_all_wo_wall_hours  mean_line_saved_hours  mean_wall_line_saved_hours
      14            79.383525          129.656141              77.076845            193.334167                   132.597500                  236.721111              -2.306680                   53.213975
      17            82.243900          139.115038              80.634413            132.071944                   134.399261                  184.005278              -1.609487                   52.155361
      19            79.886222          119.784149              97.745398            195.786389                   130.305692                  244.346667              17.859177                   50.419470

## Top makespan savings

  window_id  valid_solution  v2_makespan_hours  real_makespan_hours  makespan_saved_hours  total_saved_hours
2025-W43-7d            True          72.851061           193.334167            120.483105          77.007935
2025-W42-7d            True         106.746264           195.786389             89.040125          50.462273
2025-W21-7d            True          55.454878           118.264167             62.809289          -4.048070
2025-W33-7d            True          96.030829           150.131945             54.101115          32.338169
2025-W28-7d            True         139.115038           189.352500             50.237463          34.581819
2025-W45-7d            True          80.352832           128.955556             48.602724          19.931474
2025-W40-7d            True          98.399100           145.670833             47.271734          39.374368
2025-W30-7d            True         100.102383           144.916945             44.814562          18.799774
2025-W35-7d            True         129.656141           172.713056             43.056915          31.532593
2025-W32-7d            True         105.629678           146.984167             41.354489          47.038592

## Worst makespan deltas

  window_id  valid_solution  v2_makespan_hours  real_makespan_hours  makespan_saved_hours  total_saved_hours
2025-W10-7d            True         112.723979            98.348333            -14.375646         -15.627056
2025-W16-7d            True         107.015401           105.216389             -1.799012          14.818717
2025-W20-7d            True         108.740110           107.642778             -1.097331           8.641232
2025-W52-7d            True          27.261979            27.180000             -0.081979          -5.385345
2025-W01-7d            True          21.492449            22.049444              0.556995          -6.036579
2025-W27-7d            True         100.408517           101.379722              0.971205          34.265398
2025-W48-7d            True          78.541559            79.686389              1.144830           3.271935
2025-W08-7d            True         105.559606           107.952500              2.392894         -15.436169
2025-W14-7d            True          97.958199           102.171944              4.213745          23.289009
2025-W05-7d            True          74.060684            80.439722              6.379039           3.526922
