# BirOvoz — repository working instructions

## Current scope

This repository contains both a Central Asian voice research benchmark and
an existing FastAPI/static HTML voice demo under `product/`. The initial
research-only scope from August is obsolete. Use `HANDOFF.md` for current
status and `product/README.md` for setup.

## Evidence standards

- **CONFIRMED**: verified by a working call, test, recorded result or official documentation.
- **CLAIMED**: asserted but not verified in the current environment.
- **UNKNOWN**: insufficient evidence; do not turn it into a guess.

CPU model substitutes verify orchestration, not real audio quality, GPU
compatibility or latency. Keep frozen benchmark results separate from demo
measurements and label mock results truthfully.

## Workflow

Inspect current code and reproduce failures before changing the pipeline.
Make focused fixes, run targeted tests, then the full CPU suite:

```bash
python -m pytest tests product/backend/tests -q
```

The production Route B path uses `RouteBDaemonClient` and `--daemon`.
The older offload adapter/cache helpers are tested as separate components;
removed `ROUTE_B_PERSISTENT_*` environment settings have no effect.

## Boundaries

Keep secrets, checkpoints, external model checkouts and voice references out
of Git. Do not train models, rerun paid benchmarks automatically, replace
frozen research data, or rewrite the frontend/framework without a concrete
user request. Use one backend process per GPU. Follow the Windows/provider
acceptance checklist before declaring the real demo finished.
