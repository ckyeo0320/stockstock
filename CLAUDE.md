# StockStock - AI 기반 미국주식 자동매매 시스템

## 프로젝트 개요

한국투자증권 KIS Developers API를 사용하여 미국주식(NYSE, NASDAQ, AMEX)을 AI/ML 기반으로
1시간 간격 자동매매하는 시스템. Telegram 봇으로 알림 및 명령어 인터페이스 제공.

> **토스증권은 공식 트레이딩 API를 제공하지 않아 한국투자증권으로 대체**

## 구현 현황

### 완료된 작업 (Phase 1~5 코드 작성 완료)

| 단계 | 모듈 | 상태 | 비고 |
|---|---|---|---|
| 기반 | pyproject.toml, .gitignore, 디렉토리 구조 | **완료** | Python 3.11+, setuptools |
| 설정 | config.py (pydantic-settings + .env + YAML) | **완료** | SecretStr 보호 |
| 로깅 | logging_config.py (structlog + 민감정보 마스킹) | **완료** | JSON 구조화 로깅 |
| DB | db/models.py (6개 테이블), db/repository.py (CRUD) | **완료** | SQLAlchemy 2.0 |
| 브로커 | broker/ (client, rate_limiter, account, market_data, orders) | **완료** | PyKis 래퍼 |
| 전략 | strategy/ (features, model, signals, risk, backtest) | **완료** | LightGBM + 24개 지표 |
| 스케줄러 | scheduler/jobs.py + app.py + __main__.py | **완료** | APScheduler 1시간 간격 |
| 알림 | notifications/ (bot.py, messages.py) | **완료** | Telegram 8개 명령어 |
| 스크립트 | scripts/seed_historical.py, scripts/train_model.py | **완료** | 데이터 수집 + 학습 |
| 배포 | Dockerfile | **완료** | python:3.11-slim, 비루트 실행 |
| 테스트 | tests/unit/ (6개 파일, 26개 테스트) | **완료** | 전부 통과 |
| 린트 | ruff check | **완료** | 0 에러 |

### 보안 감사 완료 (10건 수정됨)

| 심각도 | 이슈 | 수정 내용 |
|---|---|---|
| **CRITICAL** | `pickle.load()`로 모델 로드 — 임의 코드 실행 가능 | LightGBM 네이티브 포맷으로 교체 |
| **HIGH** | 원본 Exception이 Telegram으로 전송 — 내부 경로 노출 | 일반 메시지로 대체 |
| **HIGH** | 미인가 Telegram 접근 시도 로깅 없음 | `log.warning("unauthorized_telegram_access")` 추가 |
| **MEDIUM** | `_daily_loss_usd` 스레드 안전성 미확보 | `threading.Lock` 추가 |
| **MEDIUM** | `.dockerignore` 누락 | 파일 생성 (시크릿, 테스트, 개발 파일 제외) |
| **MEDIUM** | `.gitignore` 누락 항목 | `.env.*`, `token*.json`, `*.dat`, `*.meta.json` 추가 |
| **MEDIUM** | `symbols` 입력 검증 없음 | 영문 대문자 1~5자 정규식 검증 |
| **MEDIUM** | `order_type` 검증 없음 | `MARKET`/`LIMIT` 허용값 검증 |
| **MEDIUM** | `daily_summary_hour` 범위 검증 없음 | 0~23 범위 검증 |

### 코드 리뷰 완료 (7개 이슈 발견 → 전부 수정됨)

1. **미사용 import 제거** - app.py에서 `json`, `datetime`, `upsert_ohlcv` 제거
2. **캡슐화 수정** - `_throttle()` → `throttle()` public 메서드로 변경 (5개 파일)
3. **Deprecated API 교체** - `session.query().get()` → `session.get()` (SQLAlchemy 2.0)
4. **PnL 계산 로직 수정** - 부정확한 산식 대신 거래 요약으로 변경
5. **설정 병합 중복 제거** - TelegramConfig 생성자 중복 할당 삭제
6. **타입 어노테이션 추가** - `balance: AccountBalance`, `signal: TradingSignal`
7. **ruff 린트 위반 19건 수정** - `timezone.utc` → `datetime.UTC`, import 정렬, 줄 길이

### 남은 작업 (실행을 위한 사전 준비)

- [ ] 한국투자증권 계좌 개설 + KIS Developers API 키 발급
- [ ] Telegram 봇 생성 (@BotFather) + Chat ID 확인
- [ ] `.env` 파일 작성 (`.env.example` 참고)
- [ ] `python scripts/seed_historical.py` 실행 (과거 데이터 수집)
- [ ] `python scripts/train_model.py` 실행 (모델 학습)
- [ ] Paper Trading 환경에서 수일간 검증
- [ ] Live 전환 전 백테스트 결과 확인

---

## 기술 스택

- **Python 3.11+** / pip (pyproject.toml)
- **한국투자증권 KIS API** (`python-kis>=2.1.3`)
- **LightGBM** - 주가 방향 예측 (gradient boosting)
- **SQLite + SQLAlchemy 2.0** - 거래 내역, 시세 캐시
- **APScheduler 3.x** - 1시간 간격 스케줄링
- **python-telegram-bot v21** - 알림 + 명령어
- **pydantic-settings** - 설정 관리 (SecretStr 보호)
- **structlog** - JSON 구조화 로깅 + 민감정보 마스킹
- **exchange-calendars** - NYSE 마켓 캘린더
- **ta** - 기술적 분석 지표 라이브러리
- **pandas / numpy / scikit-learn** - 데이터 처리 + ML 파이프라인

## 빌드 및 실행

```bash
# 가상환경 + 의존성 설치
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 테스트
pytest tests/ -v

# 린트
ruff check src/

# 과거 데이터 수집 (KIS API 키 필요)
python scripts/seed_historical.py

# 모델 학습
python scripts/train_model.py

# 실행 (Paper Trading 기본)
python -m stockstock
```

## 프로젝트 구조

```
stockstock/
├── CLAUDE.md               # 이 파일
├── pyproject.toml           # 의존성 + 도구 설정
├── .env.example             # 시크릿 템플릿 (커밋됨)
├── .env                     # 실제 시크릿 (커밋 안됨)
├── config/
│   └── settings.yaml        # 트레이딩/모델/로깅 설정
├── src/stockstock/
│   ├── app.py               # 앱 오케스트레이터 (트레이딩 루프 통합)
│   ├── config.py            # pydantic-settings 기반 설정 관리
│   ├── logging_config.py    # structlog + 민감정보 마스킹
│   ├── utils.py             # 마켓 캘린더, 타임존, 포맷팅
│   ├── __main__.py          # 진입점 (python -m stockstock)
│   ├── broker/              # KIS API 통합
│   │   ├── client.py        # PyKis 래퍼 (인증, 레이트리밋)
│   │   ├── account.py       # 잔고/포트폴리오 조회
│   │   ├── market_data.py   # 시세, OHLCV 조회
│   │   ├── orders.py        # 매수/매도 주문 실행
│   │   └── rate_limiter.py  # 토큰 버킷 (live 20req/s, paper 5req/s)
│   ├── strategy/            # AI/ML 매매 전략
│   │   ├── features.py      # 기술적 지표 (RSI, MACD, BB 등 24개)
│   │   ├── model.py         # LightGBM 학습/예측 (TradingModel 프로토콜)
│   │   ├── signals.py       # BUY/SELL/HOLD 시그널 생성
│   │   ├── risk.py          # 포지션 관리, 손절, 일일 손실 한도
│   │   └── backtest.py      # Walk-forward 백테스팅
│   ├── scheduler/
│   │   └── jobs.py          # APScheduler 스케줄링
│   ├── notifications/
│   │   ├── bot.py           # Telegram 봇 (비동기, 별도 스레드)
│   │   └── messages.py      # 메시지 포맷팅
│   └── db/
│       ├── models.py        # SQLAlchemy ORM (6개 테이블)
│       └── repository.py    # CRUD 연산
├── scripts/
│   ├── seed_historical.py   # 과거 OHLCV 데이터 다운로드
│   └── train_model.py       # LightGBM 모델 학습 + 백테스트
├── tests/
│   ├── conftest.py          # 공통 fixture (tmp DB, sample OHLCV)
│   └── unit/
│       ├── test_rate_limiter.py  # 토큰 버킷 4개 테스트
│       ├── test_features.py     # 기술적 지표 4개 테스트
│       ├── test_signals.py      # 시그널 생성 5개 테스트
│       ├── test_risk.py         # 리스크 관리 8개 테스트
│       └── test_messages.py     # 메시지 포맷 4개 테스트
├── models/                  # ML 모델 파일 (.gitignored)
├── data/                    # SQLite DB (.gitignored)
├── notebooks/               # EDA, 모델 실험용
└── Dockerfile               # 리눅스 배포용
```

## 핵심 아키텍처

### 트레이딩 루프 (app.py)
```
APScheduler(매 1시간) → is_market_open()?
  → Yes → 잔고 조회 → 손절 체크 → 종목별:
    fetch_ohlcv → compute_features → model.predict → generate_signal
    → risk.evaluate → 승인시 orders.execute → db.log → telegram.notify
  → No → skip
```

### 설정 (config.py)
- **시크릿**: `.env` → `pydantic.SecretStr` (KIS API 키, Telegram 토큰)
- **설정값**: `config/settings.yaml` → TradingConfig, ModelConfig 등
- **기본값**: Paper Trading 모드 (Live 전환은 `config/settings.yaml`에서 `mode: live`로 변경)
- **설정 클래스 구조**: `AppConfig` → `BrokerConfig`, `TradingConfig`, `ModelConfig`, `TelegramConfig`, `LoggingConfig`

### DB 테이블 (db/models.py)
| 테이블 | 용도 | 주요 컬럼 |
|---|---|---|
| `ohlcv` | 시세 캐시 | symbol, dt, timeframe, OHLCV, volume |
| `signals` | ML 시그널 | symbol, signal, confidence, features(JSON) |
| `trades` | 거래 내역 | symbol, side, quantity, price, status, kis_order_id |
| `portfolio_snapshots` | 일일 스냅샷 | total_value, cash, holdings(JSON), pnl |
| `risk_events` | 리스크 이벤트 | event_type, symbol, details(JSON) |
| `system_state` | 시스템 상태 | key, value (키-밸류 저장) |

### ML 모델 (strategy/model.py)
- **알고리즘**: LightGBM 3-class 분류 (UP / DOWN / HOLD)
- **타겟**: 향후 5일 수익률 방향 (UP: +2% 이상, DOWN: -2% 이하)
- **피처 24개**: RSI, MACD, 볼린저밴드, SMA/EMA 크로스오버, 거래량 비율, ATR 등
- **검증**: TimeSeriesSplit 5-fold CV + Walk-forward 백테스팅
- **모델 인터페이스**: `TradingModel` Protocol → 향후 LSTM 등으로 교체 가능
- **저장**: LightGBM 네이티브 포맷 (`.txt` + `.meta.json`) — pickle 사용하지 않음

### 리스크 관리 (strategy/risk.py)
- **포지션 한도**: 단일 종목 최대 포트폴리오의 10% (`max_position_pct`)
- **손절**: 진입가 대비 5% 하락 시 시장가 강제 매도 (`stop_loss_pct`)
- **일일 손실 한도**: $500 초과 시 당일 매매 중단 (`max_daily_loss_usd`)
- **매매 중단**: Telegram `/stop` 또는 리스크 이벤트 시 `system_state`에 상태 저장

### 레이트 리밋 (broker/rate_limiter.py)
- **토큰 버킷 알고리즘**: 스레드 안전 (`threading.Lock`)
- **Paper Trading**: 5 req/s
- **Live Trading**: 20 req/s
- `BrokerClient.stock()`, `.account()` 호출 시 자동 적용
- 추가 API 호출(quote, chart, order)은 `client.throttle()` 명시 호출

## 보안 규칙

- API 키는 반드시 `.env`에만 저장 (`.gitignore`에 포함됨)
- 모든 시크릿은 `pydantic.SecretStr` 타입 → `str()` 호출 시 `********` 출력
- structlog 프로세서가 `key/secret/token/password/authorization/credential` 패턴 자동 마스킹
- Telegram `_is_authorized()` → Chat ID 화이트리스트 인증 + 미인가 접근 시 경고 로그
- pykis 토큰 파일(`secret.json`), SQLite(`*.db`), 모델 파일 모두 `.gitignore`
- Paper Trading 기본값 → Live 전환은 `config/settings.yaml`에서 명시적으로 변경 필요
- Dockerfile에서 비루트 사용자(`appuser`)로 실행 + `.dockerignore`로 시크릿 제외
- 모델 저장: LightGBM 네이티브 포맷 사용 (pickle 사용 금지 — 임의 코드 실행 방지)
- Telegram 에러 메시지: 내부 Exception 원문 전송 금지 (일반 메시지로 대체, 상세는 로그)
- 일일 손실 추적 변수 `_daily_loss_usd`: `threading.Lock`으로 스레드 안전 보장
- 설정 입력 검증: symbols(영문 대문자 1~5자), order_type(MARKET/LIMIT), daily_summary_hour(0~23)

## Telegram 봇 명령어

| 명령어 | 설명 | 콜백 위치 |
|---|---|---|
| `/start` | 자동매매 재개 | `app.py:_on_start` |
| `/stop` | 자동매매 일시중지 | `app.py:_on_stop` |
| `/status` | 시스템 상태 확인 | `app.py:_on_status` |
| `/portfolio` | 보유 종목 + P&L | `app.py:_on_portfolio` |
| `/pnl` | 거래 요약 | `app.py:_on_pnl` |
| `/trades` | 최근 거래 내역 | `app.py:_on_trades` |
| `/signals` | 최신 모델 시그널 | `bot.py:_cmd_signals` |
| `/ping` | 헬스 체크 | `bot.py:_cmd_ping` |

## 코딩 컨벤션

- **린터**: ruff (line-length 100, select: E, F, I, N, W, UP)
- **타입 체크**: mypy strict 모드
- **ML 파일 예외**: `model.py`, `backtest.py`에서 `X`, `X_train` 등 대문자 변수 허용 (N806)
- **docstring**: 모든 모듈에 한국어 docstring
- **로깅**: structlog 구조화 로깅, 이벤트명은 `snake_case` (예: `"quote_fetched"`)
- **타입 힌트**: 모든 파일에 `from __future__ import annotations`
- **import 순서**: ruff `I001` 규칙에 따라 자동 정렬

## 주요 설정 파일

### .env (시크릿)
```
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_HTS_ID=...
KIS_ACCOUNT_NUMBER=00000000-01
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### config/settings.yaml (트레이딩 설정)
```yaml
trading:
  mode: paper          # paper | live
  symbols: [AAPL, MSFT, NVDA, GOOGL, AMZN]
  check_interval_minutes: 60
  max_position_pct: 0.10
  stop_loss_pct: 0.05
  max_daily_loss_usd: 500.0
  order_type: MARKET
model:
  artifact_path: models/lgbm_v1.pkl
  confidence_threshold: 0.6
  lookback_days: 252
```

## 서버 배포 (Oracle Cloud Always Free)

### 사전 준비
1. [Oracle Cloud](https://www.oracle.com/cloud/free/) 가입 (영구 무료, 카드 등록만 필요)
2. Compute > Create Instance > **Ampere A1 (ARM)** > Ubuntu 22.04
3. SSH 키 생성/등록

### 서버 세팅
```bash
# 1. SSH 접속
ssh -i <your-key> ubuntu@<server-ip>

# 2. 시스템 업데이트 + Docker 설치
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker ubuntu
sudo systemctl enable docker
# 재접속

# 3. 프로젝트 클론 + 설정
git clone <your-repo-url>
cd stockstock
cp .env.example .env
nano .env   # KIS API 키, Telegram 토큰 입력

# 4. 데이터 수집 + 모델 학습 (첫 실행 시)
docker compose run --rm stockstock python scripts/seed_historical.py
docker compose run --rm stockstock python scripts/train_model.py

# 5. 실행
docker compose up -d

# 6. 로그 확인
docker compose logs -f
```

### 운영 명령어
```bash
docker compose up -d       # 시작
docker compose down        # 중지
docker compose restart     # 재시작
docker compose logs -f     # 로그 실시간
docker compose pull && docker compose up -d --build  # 업데이트
```
