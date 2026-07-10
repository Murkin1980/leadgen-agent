import redis

from app.config import settings

redis_conn = redis.from_url(settings.redis_url, decode_responses=True)
