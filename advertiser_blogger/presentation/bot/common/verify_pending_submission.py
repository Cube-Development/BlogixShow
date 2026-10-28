from advertiser_blogger.application.common.cache.models import GetRedisData, InsertRedisData
from advertiser_blogger.infrastructure.cache.cache_client import RedisCacheSystem
from advertiser_blogger.presentation.bot.common.extract_post_submission import (
    PostSubmissionInput,
    submission_from_json,
    submission_to_json,
)

VERIFY_PENDING_SUBMISSION_NAME = "VerifyPendingSubmission"
VERIFY_PENDING_SUBMISSION_TTL = 1800


async def save_verify_pending_submission(
        cache: RedisCacheSystem,
        telegram_id: int,
        submission: PostSubmissionInput,
) -> None:
    await cache.set(
        payload=InsertRedisData(
            name=VERIFY_PENDING_SUBMISSION_NAME,
            user_id=str(telegram_id),
            value=submission_to_json(submission=submission),
            expires=VERIFY_PENDING_SUBMISSION_TTL,
        ),
    )


async def load_verify_pending_submission(
        cache: RedisCacheSystem,
        telegram_id: int,
) -> PostSubmissionInput | None:
    payload = await cache.get(
        payload=GetRedisData(name=VERIFY_PENDING_SUBMISSION_NAME, user_id=str(telegram_id)),
    )
    if payload is None:
        return None
    return submission_from_json(payload=payload)


async def delete_verify_pending_submission(cache: RedisCacheSystem, telegram_id: int) -> None:
    await cache.delete(
        payload=GetRedisData(name=VERIFY_PENDING_SUBMISSION_NAME, user_id=str(telegram_id)),
    )
