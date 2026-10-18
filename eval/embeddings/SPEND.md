# OpenRouter spend

From data/ledger.jsonl via spend.py.

| model | purpose | calls | inputs | reported tokens | cost $ | cost / 1.3x estimate |
|---|---|---|---|---|---|---|
| google/gemini-embedding-2 | ALL | 1133 | 104,481 | 6,111,665 | 1.2223 | 0.77 |
| google/gemini-embedding-2 | core | 261 | 24,965 | 1,412,294 | 0.2825 | 0.77 |
| google/gemini-embedding-2 | full | 748 | 71,730 | 3,834,795 | 0.7670 | 0.77 |
| google/gemini-embedding-2 | latency | 25 | 25 | 287 | 0.0001 | 0.85 |
| google/gemini-embedding-2 | probe | 6 | 18 | 225 | 0.0000 | 0.80 |
| google/gemini-embedding-2 | probe-b64 | 2 | 4 | 14 | 0.0000 | 0.77 |
| google/gemini-embedding-2 | probe2 | 4 | 12 | 202 | 0.0000 | 0.85 |
| google/gemini-embedding-2 | queries | 7 | 110 | 1,198 | 0.0002 | 0.76 |
| google/gemini-embedding-2 | threads | 80 | 7,617 | 862,650 | 0.1725 | 0.78 |
| openai/text-embedding-3-large | ALL | 855 | 104,463 | 5,638,085 | 0.7330 | 0.77 |
| openai/text-embedding-3-large | core | 196 | 24,965 | 1,303,053 | 0.1694 | 0.77 |
| openai/text-embedding-3-large | full | 561 | 71,730 | 3,521,014 | 0.4577 | 0.77 |
| openai/text-embedding-3-large | latency | 25 | 25 | 117 | 0.0000 | 0.77 |
| openai/text-embedding-3-large | probe | 4 | 12 | 144 | 0.0000 | 0.77 |
| openai/text-embedding-3-large | probe-b64 | 2 | 4 | 14 | 0.0000 | 0.77 |
| openai/text-embedding-3-large | queries | 7 | 110 | 480 | 0.0001 | 0.77 |
| openai/text-embedding-3-large | threads | 60 | 7,617 | 813,263 | 0.1057 | 0.77 |
| openai/text-embedding-3-small | ALL | 854 | 104,460 | 5,638,049 | 0.1128 | 0.77 |
| openai/text-embedding-3-small | core | 196 | 24,965 | 1,303,053 | 0.0261 | 0.77 |
| openai/text-embedding-3-small | full | 561 | 71,730 | 3,521,014 | 0.0704 | 0.77 |
| openai/text-embedding-3-small | latency | 25 | 25 | 117 | 0.0000 | 0.77 |
| openai/text-embedding-3-small | probe | 3 | 9 | 108 | 0.0000 | 0.77 |
| openai/text-embedding-3-small | probe-b64 | 2 | 4 | 14 | 0.0000 | 0.77 |
| openai/text-embedding-3-small | queries | 7 | 110 | 480 | 0.0000 | 0.77 |
| openai/text-embedding-3-small | threads | 60 | 7,617 | 813,263 | 0.0163 | 0.77 |
| qwen/qwen3-embedding-8b | ALL | 860 | 104,478 | 5,800,109 | 0.0580 | 0.79 |
| qwen/qwen3-embedding-8b | core | 196 | 24,965 | 1,339,582 | 0.0134 | 0.79 |
| qwen/qwen3-embedding-8b | full | 561 | 71,730 | 3,626,321 | 0.0363 | 0.79 |
| qwen/qwen3-embedding-8b | latency | 25 | 25 | 788 | 0.0000 | 0.80 |
| qwen/qwen3-embedding-8b | probe | 4 | 12 | 156 | 0.0000 | 0.83 |
| qwen/qwen3-embedding-8b | probe-b64 | 2 | 4 | 18 | 0.0000 | 0.99 |
| qwen/qwen3-embedding-8b | probe2 | 5 | 15 | 251 | 0.0000 | 0.82 |
| qwen/qwen3-embedding-8b | queries | 7 | 110 | 3,428 | 0.0000 | 0.80 |
| qwen/qwen3-embedding-8b | threads | 60 | 7,617 | 829,565 | 0.0083 | 0.78 |
| voyageai/voyage-4-large | ALL | 861 | 104,481 | 5,574,096 | 0.6689 | 0.76 |
| voyageai/voyage-4-large | core | 196 | 24,965 | 1,286,460 | 0.1544 | 0.76 |
| voyageai/voyage-4-large | full | 561 | 71,730 | 3,473,573 | 0.4168 | 0.76 |
| voyageai/voyage-4-large | latency | 25 | 25 | 87 | 0.0000 | 0.57 |
| voyageai/voyage-4-large | probe | 6 | 18 | 210 | 0.0000 | 0.75 |
| voyageai/voyage-4-large | probe-b64 | 2 | 4 | 10 | 0.0000 | 0.55 |
| voyageai/voyage-4-large | probe2 | 4 | 12 | 180 | 0.0000 | 0.74 |
| voyageai/voyage-4-large | queries | 7 | 110 | 342 | 0.0000 | 0.55 |
| voyageai/voyage-4-large | threads | 60 | 7,617 | 813,234 | 0.0976 | 0.77 |

**Total spend: $2.7949** (cap $4.50, hard budget $5.00)
