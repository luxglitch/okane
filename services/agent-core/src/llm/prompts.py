SIGNAL_ENHANCEMENT_PROMPT = """\
You are an expert prediction market analyst reviewing a trading signal on Kalshi.

Market: {title}
Current YES contract price: {yes_price:.2f} ({yes_pct:.0f}% implied probability that YES resolves correct)
NOTE: Prices are 0.00–1.00 representing probability, NOT dollar values of the underlying asset.
Strategy: {strategy_name} generated confidence: {confidence:.0%}
Strategy reasoning: {reasoning}

Historical context from similar markets:
{rag_context}

Analyze this trading signal:
1. Is the current market price reasonable given the event description?
2. Does the historical context support or contradict this signal?
3. What is your adjusted confidence (0.0-1.0)?
4. What are the key risks to this position?

Respond ONLY with valid JSON, no markdown, no explanation outside JSON:
{{
  "adjusted_confidence": 0.0,
  "direction_confirmed": true,
  "key_risks": ["risk1"],
  "reasoning": "2-3 sentence analysis"
}}"""


POST_MORTEM_PROMPT = """\
You are analyzing a completed prediction market trade for a self-learning trading system.

Market: {title}
Trade: {side} @ ${entry_price:.2f} × {contracts} contracts
Outcome: Market resolved {result} — position was {outcome}
P&L: ${pnl:+.2f}
Agent's original reasoning: {original_reasoning}

Historical context from similar trades:
{rag_context}

Provide a structured post-mortem analysis:
1. Why was the agent's prediction correct/incorrect?
2. What signals were most useful?
3. What should the agent do differently next time?
4. Key lesson learned (1 sentence).

Respond ONLY with valid JSON:
{{
  "was_correct": true,
  "key_factors": ["factor1", "factor2"],
  "lessons_learned": "1-sentence lesson",
  "analysis": "2-4 sentence analysis",
  "signal_quality": "high|medium|low"
}}"""
