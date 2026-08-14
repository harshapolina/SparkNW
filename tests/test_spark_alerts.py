from instascope_shared.services.spark_alerts import (
    AUTH_MILESTONES,
    ENGAGEMENT_REVIEW_MAX_RATE,
    ENGAGEMENT_REVIEW_MIN_FOLLOWERS,
    FOLLOWER_SPIKE_48H,
    VIEW_SPIKE_48H,
)


def test_anti_gaming_thresholds():
    assert FOLLOWER_SPIKE_48H == 3000
    assert VIEW_SPIKE_48H == 10_000
    assert ENGAGEMENT_REVIEW_MIN_FOLLOWERS == 10_000
    assert ENGAGEMENT_REVIEW_MAX_RATE == 1.0
    assert AUTH_MILESTONES == (10_000, 30_000, 50_000)
