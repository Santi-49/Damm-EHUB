# Optimizer v2 weekly benchmark

Generated at: `2026-05-24T09:25:16`

## Configuration

- `max_iterations`: 2
- `max_exact_nodes`: 15
- `enable_swaps`: True
- `max_swap_candidates`: 20
- `enable_balance_repair`: True
- `balance_delta_hours`: 8.0
- Runtime: 240.7 s

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

## Requested Makespan Comparison

Node-cost ML predicts productive running time. The simulated real metric below adds back `production_wo.total_hours - production_wo.productive_hours`, then adds route edge cost. Cleaning WOs are shown separately and added per line before taking the makespan.

- Mean v2 makespan: 85.03 h
- Mean real makespan (`WO total + edge`): 158.89 h
- Mean real simulated makespan (`node + inefficiency + edge`): 158.54 h
- Mean real cleaning hours: 13.77 h
- Mean real simulated makespan + cleaning: 163.69 h
- Mean v2 makespan + cleaning + real inefficiencies: 140.54 h
- Mean maintenance/rerun hours, extra column: 50.29 h
- Mean real simulated makespan + cleaning + maintenance/rerun: 177.22 h
- Mean v2 makespan + cleaning + maintenance/rerun + real inefficiencies: 163.07 h

  window_id  v2_makespan_hours  real_makespan_wo_total_plus_edge_hours  real_simulated_makespan_node_plus_inefficiency_plus_edge_hours  real_cleaning_hours  real_simulated_makespan_plus_cleaning_hours  v2_makespan_plus_cleaning_plus_real_inefficiencies_hours  real_maintenance_rerun_hours
2025-W01-7d          21.492449                               41.655000                                                       40.672264            13.801111                                    47.502264                                                 57.117449                     24.009167
2025-W02-7d          57.246411                              101.643611                                                      102.501794            15.056111                                   107.465405                                                110.888952                     10.993056
2025-W03-7d          64.535586                              117.750278                                                      117.753105            14.586111                                   125.581160                                                120.264753                     13.283889
2025-W04-7d          77.842147                              130.271668                                                      130.312477             9.210556                                   133.821366                                                123.657702                     39.006944
2025-W05-7d          74.060684                              124.814167                                                      135.810660             3.330000                                   135.810660                                                117.597340                     33.036667
2025-W06-7d          90.356586                              144.019722                                                      143.020170            14.098056                                   145.879336                                                139.636830                     51.302778
2025-W07-7d          64.456048                              132.114723                                                      134.639892            10.738333                                   138.964337                                                101.707714                    160.907778
2025-W08-7d         105.559606                              147.446111                                                      161.551632            20.634722                                   169.171076                                                163.320983                     15.104722
2025-W09-7d          50.408683                              104.041944                                                      105.889498            13.011111                                   110.754498                                                 92.095905                    199.132778
2025-W10-7d         112.723979                              135.122778                                                      143.675050            13.834167                                   148.029772                                                166.263693                     37.541389

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
