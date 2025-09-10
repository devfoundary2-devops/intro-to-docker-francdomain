from fastapi import FastAPI, HTTPException
import redis
from redis.exceptions import ConnectionError, RedisError
import psycopg2
from psycopg2 import OperationalError
import time
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Get environment variables with defaults
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "fnctech")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password1357")

# Redis initialization with retries and error handling
def init_redis():
    max_retries = 10
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            r = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            r.ping()
            logger.info(f"✅ Redis connected successfully to {REDIS_HOST}:{REDIS_PORT}")
            return r
        except (ConnectionError, RedisError) as e:
            if attempt < max_retries - 1:
                logger.warning(f"Redis not ready (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(retry_delay)
            else:
                logger.error("❌ Failed to connect to Redis after maximum retries")
                return None

# PostgreSQL initialization with retries
def init_postgres():
    max_retries = 10
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                dbname=POSTGRES_DB,
                connect_timeout=5
            )
            # Test connection
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1;")
            logger.info(f"✅ PostgreSQL connected successfully to {POSTGRES_HOST}:{POSTGRES_PORT}")
            return conn
        except OperationalError as e:
            if attempt < max_retries - 1:
                logger.warning(f"PostgreSQL not ready (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(retry_delay)
            else:
                logger.error("❌ Failed to connect to PostgreSQL after maximum retries")
                return None

# Initialize connections
r = init_redis()
pg_conn = init_postgres()

@app.get("/cache/{key}")
def cache_get(key: str):
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    try:
        val = r.get(key)
        if val is None:
            raise HTTPException(status_code=404, detail=f"Key '{key}' not found")
        return {"key": key, "value": val}
    except (ConnectionError, RedisError) as e:
        raise HTTPException(status_code=503, detail=f"Redis error: {str(e)}")

@app.post("/cache/{key}/{value}")
def cache_set(key: str, value: str):
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    try:
        r.set(key, value)
        return {"status": "ok", "key": key, "value": value}
    except (ConnectionError, RedisError) as e:
        raise HTTPException(status_code=503, detail=f"Redis error: {str(e)}")

@app.get("/db")
def db_test():
    if not pg_conn:
        raise HTTPException(status_code=503, detail="PostgreSQL service unavailable")
    try:
        with pg_conn.cursor() as cursor:
            cursor.execute("SELECT version();")
            result = cursor.fetchone()
        return {"postgres_version": result[0], "status": "success"}
    except OperationalError as e:
        raise HTTPException(status_code=503, detail=f"PostgreSQL error: {str(e)}")

@app.get("/health")
def health_check():
    redis_status = "unhealthy"
    postgres_status = "unhealthy"

    # Check Redis
    if r:
        try:
            r.ping()
            redis_status = "healthy"
        except:
            redis_status = "unhealthy"

    # Check PostgreSQL
    if pg_conn:
        try:
            with pg_conn.cursor() as cursor:
                cursor.execute("SELECT 1;")
            postgres_status = "healthy"
        except:
            postgres_status = "unhealthy"

    return {
        "status": "healthy" if redis_status == "healthy" and postgres_status == "healthy" else "degraded",
        "redis": redis_status,
        "postgresql": postgres_status,
        "redis_host": REDIS_HOST,
        "postgres_host": POSTGRES_HOST
    }

@app.get("/")
def root():
    return {
        "message": "Hello from Bootcamp Day 3",
        "services": {
            "redis": "available" if r else "unavailable",
            "postgresql": "available" if pg_conn else "unavailable"
        },
        "endpoints": {
            "health_check": "/health",
            "cache_get": "/cache/{key}",
            "cache_set": "/cache/{key}/{value}",
            "db_test": "/db"
        }
    }