# Turning Machine — NM i AI 2026

Norway's national AI championship. Four days, three challenges, one team.

**March 19–23, 2026**

---

## The Challenges

### NorgesGruppen Data — Grocery Shelf Detection
Detect and classify **356 grocery product categories** on retail shelf images. Dense scenes with 90+ objects per image, only 248 training images, and extreme class imbalance.

**Approach:** YOLOv8x with stratified multi-label splitting, 4-phase progressive training pipeline, FP16 ONNX ensemble with Weighted Boxes Fusion.

`norgesgruppen-data/`

---

### Astar Island — Viking Civilization Prediction
Predict how a Norse Viking civilization evolves across a 40x40 grid over 50 simulated years. Observe initial snapshots, infer expansion parameters, then simulate probable futures across settlements, ports, ruins, and forests.

**Approach:** Monte Carlo forward simulation with vectorized NumPy, 300 parallel simulations under 10 seconds.

`astar-island/`

---

### Tripletex Agent — AI Accounting Automation
Automate 20+ accounting workflows — invoices, payments, bank reconciliation, salary payroll, ledger corrections — by interpreting natural language prompts and executing the correct API call sequences.

**Approach:** Kotlin agentic system powered by Claude Sonnet, with task-specific classifiers, REST API tool use, and multi-step reasoning loops.

`tripletex-agent/`

---

## Team

**Turning Machine**

## Setup

```bash
# Competition MCP docs
claude mcp add --transport http nmiai https://mcp-docs.ainm.no/mcp
```
