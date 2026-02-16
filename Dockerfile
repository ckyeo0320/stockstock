FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# 소스 코드 복사
COPY src/ src/
COPY config/ config/
COPY models/ models/

# 데이터 디렉토리 생성
RUN mkdir -p data logs

# 보안: 비루트 사용자로 실행
RUN useradd --create-home appuser
RUN chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "stockstock"]
