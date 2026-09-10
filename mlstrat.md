# ML Strategy Research — Advanced Quant Studio

**Date**: 2026-09-10
**Sources**: López de Prado, Ernie Chan, BEAR, arXiv, Microsoft Qlib, AlphaAgent

---

## Key Resources

### Must-Clone
1. **Microsoft Qlib** — github.com/microsoft/qlib
2. **AlphaAgent** — arXiv:2502.16789
3. **ABIDES** — Agent-based market simulator
4. **FinRL-Meta** — Market environments for RL
5. **LOBSTER data** — Order book events (HuggingFace)

### Must-Read
1. **Trades, Quotes and Prices** — Bouchaud et al. (microstructure)
2. **Algorithmic and HF Trading** — Cartea, Jaimungal
3. **Probabilistic ML: Advanced Topics** — Murphy
4. **Expected Returns** — Antti Ilmanen
5. **Trading and Exchanges** — Larry Harris
6. **Advances in Financial ML** — López de Prado

### Must-Subscribe (Research Feeds)
- arXiv: q-fin.ST, q-fin.TR, q-fin.PM
- Oxford-Man Institute
- AQR Research
- NBER Financial Economics

---

## Strategy Framework

### Anti-Overfitting Pipeline
```
candidate alpha → naive Sharpe → cost-adjusted Sharpe → Deflated Sharpe → CSCV/PBO → factor orthogonality → subperiod stability → cross-asset replication → parameter perturbation → live shadow trading
```

### Key Insight from AlphaAgent
> Everyone generates variations of the same factors. Originality is enforced using AST similarity against existing alphas.

### Key Insight from López de Prado
> Meta-labeling: Don't predict direction. Predict probability of success.

### Key Insight from Ernie Chan
> Keep it simple. Over-complexity kills. Mean reversion + momentum simultaneously.

---

## Stock Type × Strategy Matrix

| Stock Type | Best Strategies | Worst |
|------------|-----------------|-------|
| Growth | 🐂 Bull, 🦈 Shark | 🐢 Turtle |
| Value | 🦅 Eagle, 🦉 Owl | 🐆 Cheetah |
| Defensive | 🐝 Bee, 🦉 Owl | 🐂 Bull |
| Speculative | 🐺 Wolf, 🦈 Shark | 🐢 Turtle |
| Cyclical | 🐍 Snake, 🦅 Eagle | 🐝 Bee |
| Turnaround | 🐻 Bear, 🐍 Snake | 🐂 Bull |
