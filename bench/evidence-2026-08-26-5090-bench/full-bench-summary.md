# Full bench summary (run 2, 2026-08-26, afternoon/thermal)

Source log: /tmp/bench-club3090-full-int8-default-20260826-run2.log
Protocol: 3 warm + 5 measured (narrative/code), 3 measured (prefill), cache-busted.

  warm-1     wall=  9.55s  ttft=   158ms  toks=1000  wall_TPS=104.75  decode_TPS=106.51
  warm-2     wall= 10.36s  ttft=   158ms  toks= 998  wall_TPS= 96.32  decode_TPS= 97.81
  warm-3     wall= 11.54s  ttft=   170ms  toks= 983  wall_TPS= 85.18  decode_TPS= 86.46
  run-1      wall=  9.27s  ttft=   136ms  toks=1000  wall_TPS=107.91  decode_TPS=109.52
  run-2      wall= 10.96s  ttft=   157ms  toks=1000  wall_TPS= 91.26  decode_TPS= 92.59
  run-3      wall= 10.61s  ttft=   132ms  toks=1000  wall_TPS= 94.24  decode_TPS= 95.43
  run-4      wall=  9.72s  ttft=   116ms  toks=1000  wall_TPS=102.85  decode_TPS=104.09
  run-5      wall= 10.61s  ttft=   169ms  toks=1000  wall_TPS= 94.24  decode_TPS= 95.77
=== summary [narrative] (n=5) ===
  wall_TPS       mean=  98.10   std=  6.99   CV= 7.1%   min=91.26   max=107.91
  decode_TPS     mean=  99.48   std=  7.06   CV= 7.1%   min=92.59   max=109.52
  TTFT          mean=   142ms  std=   21ms  min=116ms  max=169ms
                 the trustworthy prefill number is the client-side `prefill tok/s` summary (prompt_tokens/TTFT, cache-busted)
  warm-1     wall=  2.56s  ttft=   107ms  toks= 499  wall_TPS=195.07  decode_TPS=203.57
  warm-2     wall=  4.60s  ttft=   120ms  toks= 800  wall_TPS=173.86  decode_TPS=178.52
  warm-3     wall=  5.27s  ttft=   104ms  toks= 800  wall_TPS=151.73  decode_TPS=154.77
  run-1      wall=  2.95s  ttft=   126ms  toks= 489  wall_TPS=165.67  decode_TPS=173.03
  run-2      wall=  2.82s  ttft=   115ms  toks= 540  wall_TPS=191.82  decode_TPS=200.02
  run-3      wall=  2.77s  ttft=   127ms  toks= 550  wall_TPS=198.77  decode_TPS=208.32
  run-4      wall=  4.15s  ttft=   126ms  toks= 800  wall_TPS=192.87  decode_TPS=198.90
  run-5      wall=  4.13s  ttft=   109ms  toks= 775  wall_TPS=187.73  decode_TPS=192.82
=== summary [code] (n=5) ===
  wall_TPS       mean= 187.37   std= 12.76   CV= 6.8%   min=165.67   max=198.77
  decode_TPS     mean= 194.62   std= 13.27   CV= 6.8%   min=173.03   max=208.32
  TTFT          mean=   121ms  std=    8ms  min=109ms  max=127ms
                 the trustworthy prefill number is the client-side `prefill tok/s` summary (prompt_tokens/TTFT, cache-busted)
[bench] prefill-10k run 1/3: 10375 prompt tok, 7305.6 prefill tok/s, ttft 1420ms
[bench] prefill-10k run 2/3: 10375 prompt tok, 7631.1 prefill tok/s, ttft 1360ms
[bench] prefill-10k run 3/3: 10375 prompt tok, 7364.2 prefill tok/s, ttft 1409ms
=== summary [prefill-10k] (n=3) ===
  prefill tok/s  mean=7433.62   std=173.48   CV= 2.3%   min=7305.57   max=7631.05
  TTFT          mean=  1396ms  std=   32ms  min=1360ms  max=1420ms
                 the `prefill tok/s` line above is the client-side measurement for this depth
[bench] prefill-90k run 1/3: 89998 prompt tok, 3117.1 prefill tok/s, ttft 28872ms
[bench] prefill-90k run 2/3: 86665 prompt tok, 3188.8 prefill tok/s, ttft 27178ms
[bench] prefill-90k run 3/3: 89998 prompt tok, 3105.2 prefill tok/s, ttft 28983ms
=== summary [prefill-90k] (n=3) ===
  prefill tok/s  mean=3137.06   std= 45.23   CV= 1.4%   min=3105.19   max=3188.83
  TTFT          mean= 28344ms  std= 1012ms  min=27178ms  max=28983ms
  PP tok/s (engine log, windowed — indicative only) mean=8751.57   std=218.10   CV= 2.5%   min=8588.90   max=8999.40
