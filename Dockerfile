FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 소스 코드 + 설정 복사
COPY pyproject.toml ./
COPY src/ src/
COPY config/ config/

# Python 의존성 설치
RUN pip install --no-cache-dir .

# 모델 디렉토리 복사
COPY models/ models/

# 보안: 비루트 사용자 생성 + 디렉토리 권한 설정
RUN useradd --create-home appuser \
    && mkdir -p data logs \
    && chown -R appuser:appuser /app

USER appuser

CMD ["python", "-m", "stockstock"]
