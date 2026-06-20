from app.drift import DriftTracker


def test_recent_mean_and_drift_track_observations():
    tracker = DriftTracker(window=10)
    tracker._baseline = 0.2
    for _ in range(5):
        tracker.observe(0.8)
    assert tracker.recent_mean == 0.8
    assert tracker.drift == abs(0.8 - 0.2)


def test_window_is_bounded():
    tracker = DriftTracker(window=3)
    tracker._baseline = 0.0
    for score in [0.1, 0.2, 0.3, 0.9, 0.9, 0.9]:
        tracker.observe(score)
    # Only the last 3 (all 0.9) remain.
    assert tracker.recent_mean == 0.9


def test_empty_tracker_has_zero_mean():
    tracker = DriftTracker()
    assert tracker.recent_mean == 0.0
