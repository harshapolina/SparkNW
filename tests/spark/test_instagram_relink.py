"""Changing a student's Instagram link must stick, and must drop the old account (no DB).

The bug: a scrape holds its in-memory profile for minutes, and Beanie's save()
writes every field back — so a progress save during the scrape reverted an
Instagram link the admin had just changed, and the next Refresh scraped the old
account again.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import instascope_shared.services.scrape_core as core
from instascope_shared.models import JobStatus
from instascope_shared.services.scrape_pipeline import reset_account_state


class _Store:
    """One stored profile document, standing in for Mongo."""

    def __init__(self, **doc):
        self.doc = dict(doc)
        self.set_calls: list[dict] = []


def _fake_profile_model(store: _Store):
    class _Update:
        async def update(self, op):
            fields = dict(op["$set"])
            store.set_calls.append(fields)
            store.doc.update(fields)

    class FakeProfile:
        id = "id-field"  # makes `Profile.id == x` a harmless expression

        @staticmethod
        async def get(_pid):
            return SimpleNamespace(**store.doc)

        @staticmethod
        def find_one(*_args, **_kwargs):
            return _Update()

    return FakeProfile


class _Job:
    def __init__(self):
        self.status = JobStatus.RUNNING
        self.meta = {}
        self.error_message = None
        self.finished_at = None
        self.updated_at = None

    async def save(self):
        return self


def _in_memory_profile(username: str):
    """What the runner holds for the whole scrape. save() would clobber the store."""
    calls = {"save": 0}

    async def save():
        calls["save"] += 1

    return (
        SimpleNamespace(
            id="p1",
            username=username,
            user_id="admin",
            posts_count=10,
            followers=500,
            scrape_progress=None,
            save=save,
        ),
        calls,
    )


def _result():
    return SimpleNamespace(posts=[], posts_count=0, raw={}, to_dict=lambda: {"posts": []})


@pytest.fixture
def harness(monkeypatch):
    def build(*, rename_mid_scrape: bool):
        store = _Store(id="p1", username="old_handle", followers=500, posts_count=10)
        applied: list = []
        scraped: list[str] = []

        async def fake_scrape(username, **_kwargs):
            scraped.append(username)
            if rename_mid_scrape:
                # Admin saves a new Instagram link while this scrape is running.
                store.doc["username"] = "new_handle"
            return _result()

        async def fake_apply(*, job, profile, result):
            applied.append(profile)

        async def fake_resolve_job(*_args, **_kwargs):
            return _Job()

        monkeypatch.setattr(core, "Profile", _fake_profile_model(store))
        monkeypatch.setattr(core, "scrape_profile", fake_scrape)
        monkeypatch.setattr(core, "apply_scrape_result", fake_apply)
        monkeypatch.setattr(core, "_resolve_job", fake_resolve_job)
        monkeypatch.setattr(core, "pool_size", lambda: 0)
        return store, applied, scraped

    return build


@pytest.mark.asyncio
async def test_link_changed_mid_scrape_discards_old_result_and_keeps_new_link(harness):
    store, applied, scraped = harness(rename_mid_scrape=True)
    profile, calls = _in_memory_profile("old_handle")

    job = await core.run_profile_scrape(profile, source="single")

    assert scraped == ["old_handle"]
    assert applied == [], "old account's result must not be written"
    assert job.status == JobStatus.CANCELLED
    assert "link changed" in (job.error_message or "")
    assert store.doc["username"] == "new_handle", "new link was reverted"
    assert calls["save"] == 0, "a full save() would write the stale handle back"


@pytest.mark.asyncio
async def test_progress_writes_touch_only_progress_fields(harness):
    store, _applied, _scraped = harness(rename_mid_scrape=True)
    profile, _calls = _in_memory_profile("old_handle")

    await core.run_profile_scrape(profile, source="single")

    assert store.set_calls, "expected progress writes"
    for fields in store.set_calls:
        assert set(fields) <= {"scrape_progress", "updated_at", "last_error"}
        assert "username" not in fields


@pytest.mark.asyncio
async def test_unchanged_link_applies_on_fresh_copy(harness):
    store, applied, scraped = harness(rename_mid_scrape=False)
    profile, _calls = _in_memory_profile("old_handle")

    await core.run_profile_scrape(profile, source="single")

    assert scraped == ["old_handle"]
    assert len(applied) == 1
    # Applied to a copy re-read from the store, not the minutes-old one.
    assert applied[0] is not profile
    assert applied[0].username == "old_handle"


def test_reset_account_state_clears_old_account_keeps_student_data():
    profile = SimpleNamespace(
        ig_user_id="999",
        full_name="Old Account",
        bio="old bio",
        website="https://old.example",
        avatar_url="https://cdn/old.jpg",
        is_verified=True,
        is_private=True,
        is_business=True,
        category="Creator",
        highlight_reel_count=4,
        follower_following_ratio=3.2,
        followers=8000,
        following=12,
        posts_count=91,
        avg_likes=10.0,
        avg_views=20.0,
        avg_comments=3.0,
        engagement_rate=1.5,
        growth_pct_today=2.0,
        insights={
            "top_hashtags": ["#old"],
            "best_post_shortcode": "OLD",
            "spark_bonus_points": 325,
            "spark_bonus_log": [{"points": 325}],
            "spark_collaborations": 50,
            "team": "Alpha",
        },
        scrape_progress={"phase": "done"},
        last_scraped_at="x",
        last_success_at="x",
        student={"student_id": "N25H01A0308", "full_name": "Harideep"},
        youtube_channel_id="UC123",
        youtube_connected=True,
    )

    reset_account_state(profile)

    assert profile.followers == 0 and profile.posts_count == 0
    assert profile.ig_user_id is None and profile.avatar_url is None and profile.bio is None
    assert profile.last_success_at is None and profile.scrape_progress is None
    # Admin-owned points and the team survive; scraped metrics do not.
    assert profile.insights == {
        "spark_bonus_points": 325,
        "spark_bonus_log": [{"points": 325}],
        "spark_collaborations": 50,
        "team": "Alpha",
    }
    # Roster and YouTube belong to the student, not the Instagram account.
    assert profile.student == {"student_id": "N25H01A0308", "full_name": "Harideep"}
    assert profile.youtube_connected is True and profile.youtube_channel_id == "UC123"
