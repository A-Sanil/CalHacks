import os

# Keep unit tests fast — ML is tested separately in test_api::TestMLWarmstart
os.environ.setdefault("AOE_USE_ML_WARMSTART", "false")
