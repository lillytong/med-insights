# Subreddits to monitor — Tier 1 high-signal physician communities
SUBREDDITS = [
    "medicine",
    "emergencymedicine",
    "hospitalist",
    "residency",
    "anesthesiology",
]

# Scraper settings
POSTS_PER_SUBREDDIT = 30
TIME_FILTER = "month"       # last 30 days
TOP_COMMENTS = 10           # top-level comments only, by score
MAX_COMMENT_WORDS = 150     # truncate each comment before sending to LLM

# Rule-based pre-filter thresholds
MIN_SCORE = 10
MIN_COMMENTS = 5
MIN_BODY_WORDS = 30

# LLM settings
FILTER_BATCH_SIZE = 20      # posts per Haiku call
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"
SYNTHESIS_CONCURRENCY = 5   # concurrent Sonnet requests

# Paths
RAW_DATA_DIR = "data/raw"
OUTPUT_DIR = "data/output"
CACHE_FILE = "data/processed_ids.json"
