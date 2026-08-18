"""Public Top 10 snapshot helpers (no DB)."""

from datetime import datetime

from instascope_shared.services.spark import _jsonable, top10_payload_from_board


def test_jsonable_datetimes_become_iso():
    dt = datetime(2026, 8, 18, 12, 30, 0)
    out = _jsonable({"when": dt, "nested": [{"n": dt}]})
    assert out["when"] == "2026-08-18T12:30:00"
    assert out["nested"][0]["n"] == "2026-08-18T12:30:00"


def test_top10_payload_keeps_ten_and_strips_history():
    board = [
        {
            "id": str(i),
            "name": f"Creator {i}",
            "points": 1000 - i,
            "task_history": [{"id": "x", "points": 1}],
        }
        for i in range(15)
    ]
    start = datetime(2026, 7, 15)
    end = datetime(2026, 8, 18)
    payload = top10_payload_from_board(board, start=start, end=end)
    assert payload["total_creators"] == 15
    assert len(payload["items"]) == 10
    assert payload["from_date"] == "2026-07-15"
    assert payload["to_date"] == "2026-08-18"
    assert "task_history" not in payload["items"][0]
    assert payload["items"][0]["name"] == "Creator 0"
    assert payload["items"][-1]["name"] == "Creator 9"
