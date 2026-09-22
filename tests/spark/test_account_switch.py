"""A new Instagram account behind a student must save, and must replace the old one (no DB).

Real case: @jabeerrr07's link was changed to a brand-new account whose whole
history (40 posts, 22 Jul → 19 Sep) sits inside the programme window. The scrape
never reached the 15 Jul floor, so the full 40/40 result was refused as
"incomplete", and the old account's 433 followers / 21 posts stayed on screen.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import instascope_shared.services.scrape_pipeline as sp


def test_whole_timeline_read_is_complete_even_without_reaching_the_floor(monkeypatch):
    monkeypatch.setenv("SCRAPE_STOP_AT_COHORT", "1")
    # The @jabeerrr07 numbers: 40 of 40, floor never hit.
    assert sp._is_complete_enough(40, 40, 77, hit_cohort_floor=False, timeline_complete=False) is False
    assert sp._is_complete_enough(40, 40, 77, hit_cohort_floor=False, timeline_complete=True) is True


def test_first_page_sample_is_still_refused(monkeypatch):
    monkeypatch.setenv("SCRAPE_STOP_AT_COHORT", "1")
    # A 12-post sample that neither hit the floor nor was confirmed complete.
    assert sp._is_complete_enough(91, 12, 8934) is False


@pytest.mark.parametrize(
    ("stored", "scraped", "changed"),
    [
        ("40346599755", "41769303127", True),  # the real @jabeerrr07 switch
        ("40346599755", "40346599755", False),  # same account (handle rename keeps the id)
        (None, "41769303127", False),  # first scrape
        ("40346599755", None, False),  # scrape did not resolve an id
    ],
)
def test_account_changed_uses_instagrams_permanent_user_id(stored, scraped, changed):
    profile = SimpleNamespace(ig_user_id=stored)
    assert sp._account_changed(profile, {"ig_user_id": scraped}) is changed


@pytest.mark.asyncio
async def test_forget_previous_account_drops_posts_and_history(monkeypatch):
    deleted: list[str] = []

    class _Query:
        def __init__(self, name):
            self.name = name

        async def delete(self):
            deleted.append(self.name)

    class _Model:
        def __init__(self, name):
            self.name = name
            self.profile_id = "profile_id-field"

        def find(self, *_args, **_kwargs):
            return _Query(self.name)

    monkeypatch.setattr(sp, "Post", _Model("posts"))
    monkeypatch.setattr(sp, "ProfileSnapshot", _Model("snapshots"))
    profile = SimpleNamespace(
        id="p1",
        ig_user_id="40346599755",
        followers=433,
        following=193,
        posts_count=21,
        insights={"sampled_posts": 21, "spark_bonus_points": 25},
    )
    for attr in (
        "full_name bio website avatar_url is_verified is_private is_business category "
        "highlight_reel_count follower_following_ratio avg_likes avg_views avg_comments "
        "engagement_rate growth_pct_today scrape_progress last_scraped_at last_success_at"
    ).split():
        setattr(profile, attr, None)

    await sp.forget_previous_account(profile)

    assert sorted(deleted) == ["posts", "snapshots"]
    assert profile.followers == 0 and profile.posts_count == 0 and profile.ig_user_id is None
    # Bonus points belong to the student, not the account.
    assert profile.insights == {"spark_bonus_points": 25}


@pytest.mark.asyncio
async def test_profile_response_keeps_admin_points_alongside_live_metrics(monkeypatch):
    """The admin card read 0 bonus because insights were replaced by post metrics."""
    import instascope_shared.services.profiles as prof

    class _Empty:
        async def to_list(self):
            return []

    class _Model:
        profile_id = "profile_id-field"

        @staticmethod
        def find(*_args, **_kwargs):
            return _Empty()

    monkeypatch.setattr(prof, "Post", _Model)
    monkeypatch.setattr(prof, "ProfileSnapshot", _Model)
    ledger = [{"points": 25, "reason": "Challenge 02 (August)"}]
    stored = prof.Profile.model_construct(
        id="6a74d147dfd56bc43bc6a34b",
        user_id="u",
        username="jabeerrr07",
        profile_url="https://www.instagram.com/jabeerrr07/",
        insights={"sampled_posts": 21, "spark_bonus_points": 25, "spark_bonus_log": ledger},
    )

    resp = await prof.to_profile_response_cohort(stored)

    assert resp.insights["spark_bonus_points"] == 25
    assert resp.insights["spark_bonus_log"] == ledger
    # Live programme-window metrics still win for everything else.
    assert resp.insights.get("sampled_posts", 0) == 0
