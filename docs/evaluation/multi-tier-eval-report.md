# Multi-tier evaluation report

Generated: 2026-07-18T11:57:50.477119+00:00

- Backend: `oemer-stock`
- Device: `cuda`
- Quality profile: `quality`
- Limit per tier: 5
- Full gates: True
- Tier 0 gate: pass
- Tier 1 gate: pass
- Overall release gate: pass

## Tier results

| Tier | Completed | Parse rate | Gate |
|------|-----------|------------|------|
| tier0-fixtures | 3/3 | 100% | pass |

OMR-NED (`tier0-fixtures`): n=3, avg=0.2213, min=0.1603, max=0.2978; musicdiff completed on 3 sample(s).
| tier1a-openscore | 3/3 | 100% | pass |
| tier1b-musescore-com | 15/15 | 100% | pass |

OMR-NED (`tier1b-musescore-com`): n=12, avg=0.6125, min=0.2316, max=0.9790; musicdiff completed on 15 sample(s).