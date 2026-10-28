import json

from advertiser_blogger.presentation.bot.common.extract_post_submission import (
    PostSubmissionInput,
    submission_from_json,
    submission_to_json,
)


def test_submission_round_trip_with_all_fields() -> None:
    submission = PostSubmissionInput(
        channel_ident=3992737086,
        channel_username="blogger",
        post_url="https://t.me/blogger/6",
        text="post text",
    )
    restored = submission_from_json(payload=submission_to_json(submission=submission))
    assert restored == submission


def test_submission_round_trip_with_nullable_fields() -> None:
    submission = PostSubmissionInput(
        channel_ident=None,
        channel_username=None,
        post_url="https://t.me/blogger/6",
        text=None,
    )
    payload = submission_to_json(submission=submission)
    data = json.loads(payload)
    assert data["channel_ident"] is None
    assert data["channel_username"] is None
    assert data["text"] is None
    assert submission_from_json(payload=payload) == submission
