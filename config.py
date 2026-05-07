# Subreddits to monitor — selected based on empirical CUN audit (clinical_unmet_need %)
# Full audit results (n=200 each unless noted):
#   psychiatry        23% CUN, 31% signal — strongest pure clinical signal
#   rheumatology      20% CUN, 28% signal — needs patient-post filter (68% noise)
#   oncology          16% CUN, 18% signal — mostly physician, rich trial discussion
#   cardiology        13% CUN, 14% signal — physician-heavy, clinical decision gaps
#   ophthalmology     14% CUN, 16% signal — physician/surgeon, retinal cases, OR technique, reimbursement
#   anesthesiology    11% CUN, 27% signal — airway, medication errors, technique debates
#   nephrology        11% CUN, 12% signal — n=132, physician-heavy
#   gastroenterology   7% CUN,  9% signal — mixed patient/physician
#   neurology         ~10% CUN (batch 2 manual) — batch 1 inflated to 36% by flair auto-labeler
# Dropped (low CUN):
#   infectiousdisease 25% CUN but n=48 only, heavily patient-contaminated (HSV advocacy)
#   generalsurgery     2% CUN — 90% residency matching/career noise, almost no clinical discussion
#   emergencymedicine  2% CUN — trauma/procedure heavy, little unmet need discussion
#   hospitalist        2% CUN — workflow/admin dominant
#   criticalcare       2% CUN — career/training noise dominant
#   dermatology        4% CUN — overwhelmed by student/patient/career posts
#   hematology         1% CUN — lab tech morphology subreddit, not clinical discussion
#   pharmacy           2% CUN — PBM/policy noise dominant
#   endocrinology      1% CUN — almost entirely patient posts
#   Noctor             0% CUN — professional_debate only (scope of practice)
#   palliativecare     0% CUN — too small (n=18)
SUBREDDITS = [
    "psychiatry",         # 23% CUN — strongest pure clinical signal
    "rheumatology",       # 20% CUN — diagnostic/treatment gaps, needs patient-post filter
    "oncology",           # 16% CUN — rich trial/treatment discussion, physician-heavy
    "cardiology",         # 13% CUN — physician-heavy, procedure and protocol decision gaps
    "ophthalmology",      # 14% CUN — retinal cases, OR technique gaps, reimbursement pressure
    "anesthesiology",     # 11% CUN — airway, medication errors, technique debates
    "nephrology",         # 11% CUN — physician-heavy, treatment protocol gaps
    "gastroenterology",   # 7% CUN — mixed but meaningful physician clinical content
]

# Scraper settings
POSTS_PER_SUBREDDIT = 500
SORT = "top"
TIME_FILTER = "year"        # top posts from the past year (hour/day/week/month/year/all)
TOP_COMMENTS = 10           # top-level comments only, by score
MAX_COMMENT_WORDS = 150     # truncate each comment before sending to LLM

# Rule-based pre-filter thresholds
MIN_BODY_WORDS = 30

# LLM settings
FILTER_BATCH_SIZE = 20      # posts per Haiku call
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"
SYNTHESIS_CONCURRENCY = 2   # concurrent Sonnet requests

# Embedding settings
EMBEDDING_MODEL = "voyage-3-lite"   # 512 dims, $0.02/1M tokens
EMBEDDING_BATCH_SIZE = 128          # Voyage API max per request

# Paths
RAW_DATA_DIR = "data/raw"
SYNTHESIS_DIR = "data/synthesis"
OUTPUT_DIR = "data/output"
CACHE_FILE = "data/processed_ids.json"
CHROMA_DIR = "data/chroma"          # persistent vector store
CHROMA_COLLECTION = "med-insights"
