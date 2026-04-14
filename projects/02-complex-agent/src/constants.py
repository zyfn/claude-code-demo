"""Internal constants — not user-configurable.

All magic numbers in one place. If you're looking for a threshold
or limit, it's here.
"""

# ━━ Query loop ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Max times to inject recovery prompt when model hits output token limit
MAX_OUTPUT_RECOVERY_LIMIT = 3

# Escalated max_tokens when first attempt returns empty (8k default → 64k)
ESCALATED_MAX_TOKENS = 64_000

# Token buffer before blocking limit (reserve space for the model to respond)
BLOCKING_BUFFER = 2_000

# ━━ Compaction ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Auto-compact triggers when token_count >= context_limit - this buffer
AUTO_COMPACT_BUFFER = 13_000

# Stop retrying auto-compact after this many consecutive failures
AUTO_COMPACT_MAX_FAILURES = 3

# Max chars for a single tool result before truncation
TOOL_RESULT_BUDGET = 50_000

# ━━ Retry ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RETRY_BASE_DELAY_MS = 500
RETRY_MAX_BACKOFF_MS = 32_000
RETRY_MAX_RETRIES = 5

# ━━ Tool execution ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAX_CONCURRENT_TOOLS = 10
