---
name: quantitative-decision-model
description: Reverse a financial or capacity goal into a transparent, checkable operating model.
---

# Quantitative Decision Model

Use when the user asks how much output, area, time, money, or capacity is needed for a target.

1. Start from the user's target and accepted constraints. Explicitly discard earlier assistant
   examples that the user rejected or corrected.
2. List each input with its status: user-provided, independently sourced, or scenario assumption.
   A retail shelf price is not the producer's realized sale price. A gross margin is not net profit.
3. Reverse the model in order: target profit and costs -> sold quantity -> harvest quantity ->
   harvest batches -> planting positions and area -> gross land. Keep delivery frequency separate
   from harvest frequency. Include growth and turnaround time when counting concurrent blocks.
4. Call `brainstormer_calculate_capacity` when all required numeric inputs are available. It
   checks arithmetic only; do not describe its output as verified market or agronomic evidence.
   If an input is missing, give the equation with that variable and ask only for the key missing
   observation, or show clearly labelled sensitivity scenarios.
5. Check units and recompute after every corrected premise. State which conclusion changes.
   Never claim a precise land requirement from unverified yield or price assumptions.
