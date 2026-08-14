"""Live anti-gaming / integrity alerts for the admin Alerts console."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from instascope_shared.models import (
    Profile,
    ProfileSnapshot,
    YouTubeChannel,
    YouTubeSnapshot,
)

FOLLOWER_SPIKE_48H = 3_000
VIEW_SPIKE_48H = 10_000  # Instagram avg_views delta in ~48h
YT_SUB_SPIKE_48H = 3_000
YT_VIEW_SPIKE_48H = 50_000
ENGAGEMENT_REVIEW_MIN_FOLLOWERS = 10_000
ENGAGEMENT_REVIEW_MAX_RATE = 1.0
AUTH_MILESTONES = (10_000, 30_000, 50_000)


def _iso(dt: datetime | None) -> str:
    return (dt or datetime.utcnow()).isoformat()


def _row(
    *,
    id: str,
    type: str,
    category: str,
    severity: str,
    title: str,
    body: str,
    profile: Profile,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    student = dict(getattr(profile, "student", None) or {})
    payload = {
        "id": id,
        "type": type,
        "category": category,
        "severity": severity,
        "title": title,
        "body": body,
        "profile_id": str(profile.id),
        "username": profile.username,
        "full_name": getattr(profile, "full_name", None) or student.get("full_name"),
        "created_at": _iso(profile.last_success_at or profile.updated_at),
        "followers": int(profile.followers or 0),
        "engagement_rate": float(profile.engagement_rate or 0),
        "avg_views": float(profile.avg_views or 0),
    }
    if extra:
        payload.update(extra)
    return payload


async def build_integrity_alerts(
    profiles: list[Profile],
    yt_channels: list[YouTubeChannel],
) -> list[dict[str, Any]]:
    """Follower spikes, low engagement at 10K+, authenticity milestones, bot heuristic."""
    if not profiles:
        return []

    floor = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d")
    pids = [str(p.id) for p in profiles if p.id]

    ig_snaps = await ProfileSnapshot.find({"snapshot_date": {"$gte": floor}}).to_list()
    ig_by: dict[str, list[ProfileSnapshot]] = defaultdict(list)
    for s in ig_snaps:
        if s.profile_id in set(pids):
            ig_by[s.profile_id].append(s)

    yt_snaps = await YouTubeSnapshot.find({"snapshot_date": {"$gte": floor}}).to_list()
    yt_by: dict[str, list[YouTubeSnapshot]] = defaultdict(list)
    for s in yt_snaps:
        yt_by[s.profile_id].append(s)

    yt_map = {c.profile_id: c for c in yt_channels}

    alerts: list[dict[str, Any]] = []

    for p in profiles:
        pid = str(p.id)
        followers = int(p.followers or 0)
        eng = float(p.engagement_rate or 0)
        views = float(p.avg_views or 0)
        ig_hist = sorted(ig_by.get(pid, []), key=lambda x: x.snapshot_date)
        ig_base = ig_hist[0] if ig_hist else None
        prev_f = int(ig_base.followers) if ig_base else None
        prev_v = float(ig_base.avg_views) if ig_base else None
        f_delta = (followers - prev_f) if prev_f is not None else None
        v_delta = (views - prev_v) if prev_v is not None else None

        spike_followers = bool(f_delta is not None and f_delta >= FOLLOWER_SPIKE_48H)
        spike_views = bool(v_delta is not None and v_delta >= VIEW_SPIKE_48H)
        low_eng_scale = followers >= ENGAGEMENT_REVIEW_MIN_FOLLOWERS and eng < ENGAGEMENT_REVIEW_MAX_RATE

        if spike_followers or spike_views:
            parts = []
            if spike_followers:
                parts.append(f"+{int(f_delta):,} followers in 48h (audit ≥ {FOLLOWER_SPIKE_48H:,})")
            if spike_views:
                parts.append(f"+{int(v_delta):,.0f} avg views in 48h (audit ≥ {VIEW_SPIKE_48H:,})")
            alerts.append(
                _row(
                    id=f"spike-{pid}",
                    type="follower_spike_48h" if spike_followers else "views_spike_48h",
                    category="growth_anomaly",
                    severity="high",
                    title=f"@{p.username} sudden spike — manual audit",
                    body=" · ".join(parts) + f" · now {followers:,} followers, {int(views):,} avg views.",
                    profile=p,
                    extra={
                        "followers_delta_48h": f_delta,
                        "views_delta_48h": v_delta,
                        "action": "manual_audit",
                    },
                )
            )

        if low_eng_scale:
            alerts.append(
                _row(
                    id=f"eng-{pid}",
                    type="low_engagement",
                    category="engagement_review",
                    severity="medium",
                    title=f"@{p.username} below 1% engagement at 10K+",
                    body=(
                        f"{eng:.2f}% engagement with {followers:,} followers "
                        "(review threshold: <1% at 10K+)."
                    ),
                    profile=p,
                    extra={"action": "review"},
                )
            )

        if prev_f is not None:
            for mark in AUTH_MILESTONES:
                if prev_f < mark <= followers:
                    alerts.append(
                        _row(
                            id=f"auth-{pid}-{mark}",
                            type="authenticity_milestone",
                            category="authenticity",
                            severity="medium",
                            title=f"@{p.username} crossed {mark // 1000}K — verify authenticity",
                            body=(
                                f"Hit {followers:,} followers (was {prev_f:,}). "
                                "Verify follower authenticity (Modash / HypeAuditor) at 10K, 30K, 50K."
                            ),
                            profile=p,
                            extra={"milestone": mark, "action": "verify_authenticity"},
                        )
                    )

        if spike_followers and eng < ENGAGEMENT_REVIEW_MAX_RATE:
            alerts.append(
                _row(
                    id=f"bot-{pid}",
                    type="bot_purchase_suspected",
                    category="bot_integrity",
                    severity="critical",
                    title=f"@{p.username} suspected bot purchase",
                    body=(
                        f"+{int(f_delta):,} followers in 48h with {eng:.2f}% engagement. "
                        "Detected bot purchases: −500 pts + final warning; second detection: disqualification."
                    ),
                    profile=p,
                    extra={
                        "followers_delta_48h": f_delta,
                        "action": "penalty_warning",
                        "penalty_points": -500,
                    },
                )
            )

        ch = yt_map.get(pid)
        if ch and ch.connected:
            yt_hist = sorted(yt_by.get(pid, []), key=lambda x: x.snapshot_date)
            yt_base = yt_hist[0] if yt_hist else None
            subs = int(ch.subscriber_count or 0)
            yt_views = int(ch.view_count or 0)
            prev_subs = int(yt_base.subscribers or 0) if yt_base and yt_base.subscribers is not None else None
            prev_yt_views = int(yt_base.total_views) if yt_base else None
            sub_delta = (subs - prev_subs) if prev_subs is not None else None
            yt_v_delta = (yt_views - prev_yt_views) if prev_yt_views is not None else None
            if (sub_delta is not None and sub_delta >= YT_SUB_SPIKE_48H) or (
                yt_v_delta is not None and yt_v_delta >= YT_VIEW_SPIKE_48H
            ):
                bits = []
                if sub_delta is not None and sub_delta >= YT_SUB_SPIKE_48H:
                    bits.append(f"+{sub_delta:,} subscribers in 48h")
                if yt_v_delta is not None and yt_v_delta >= YT_VIEW_SPIKE_48H:
                    bits.append(f"+{yt_v_delta:,} channel views in 48h")
                alerts.append(
                    _row(
                        id=f"yt-spike-{pid}",
                        type="youtube_spike_48h",
                        category="growth_anomaly",
                        severity="high",
                        title=f"@{p.username} YouTube spike — manual audit",
                        body=" · ".join(bits) + ".",
                        profile=p,
                        extra={
                            "platform": "youtube",
                            "subscribers_delta_48h": sub_delta,
                            "views_delta_48h": yt_v_delta,
                            "action": "manual_audit",
                        },
                    )
                )

    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    alerts.sort(key=lambda a: rank.get(str(a.get("severity")), 9))
    return alerts
