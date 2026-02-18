# StockStock - AI 기반 미국주식 자동매매 시스템

## 프로젝트 개요

한국투자증권 KIS Developers API를 사용하여 미국주식(NYSE, NASDAQ, AMEX)을 AI/ML 기반으로
1시간 간격 자동매매하는 시스템. Telegram 봇으로 알림 및 명령어 인터페이스 제공.

> **토스증권은 공식 트레이딩 API를 제공하지 않아 한국투자증권으로 대체**

## 구현 현황

### 완료된 작업 (Phase 1~5 + Phase 7 코드 작성 완료)

| 단계 | 모듈 | 상태 | 비고 |
|---|---|---|---|
| 기반 | pyproject.toml, .gitignore, 디렉토리 구조 | **완료** | Python 3.11+, setuptools |
| 설정 | config.py (pydantic-settings + .env + YAML) | **완료** | SecretStr 보호 |
| 로깅 | logging_config.py (structlog + 민감정보 마스킹) | **완료** | JSON 구조화 로깅 |
| DB | db/models.py (8개 테이블), db/repository.py (CRUD) | **완료** | SQLAlchemy 2.0 |
| 브로커 | broker/ (client, rate_limiter, account, market_data, orders) | **완료** | PyKis 래퍼 |
| 전략 | strategy/ (features, model, signals, risk, backtest) | **완료** | LightGBM + 24개 기술 + 10개 매크로 지표 |
| 매크로 | macro/ (fred_client, market_data, sector_rotation, macro_score) | **완료** | FRED + yfinance |
| 스케줄러 | scheduler/jobs.py + app.py + __main__.py | **완료** | APScheduler, 매크로 시 일일 리밸런싱 |
| 알림 | notifications/ (bot.py, messages.py) | **완료** | Telegram 9개 명령어 (/macro 추가) |
| 스크립트 | scripts/seed_historical.py, scripts/train_model.py | **완료** | 데이터 수집 + 학습 |
| 배포 | Dockerfile | **완료** | python:3.11-slim, 비루트 실행 |
| 테스트 | tests/unit/ (10개 파일, 55개 테스트) | **완료** | 전부 통과 |
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
- [ ] FRED API Key 발급 (https://fred.stlouisfed.org/docs/api/api_key.html)
- [ ] `.env` 파일 작성 (`.env.example` 참고, `FRED_API_KEY` 포함)
- [ ] `python scripts/seed_historical.py` 실행 (과거 데이터 수집)
- [ ] `python scripts/train_model.py` 실행 (모델 학습)
- [ ] Paper Trading 환경에서 수일간 검증
- [ ] Live 전환 전 백테스트 결과 확인 (SPY 대비 초과수익 검증)

---

## 기술 스택

- **Python 3.11+** / pip (pyproject.toml)
- **한국투자증권 KIS API** (`python-kis>=2.1.3`)
- **LightGBM** - 주가 방향 예측 (gradient boosting)
- **SQLite + SQLAlchemy 2.0** - 거래 내역, 시세 캐시, 매크로 데이터
- **APScheduler 3.x** - 스케줄링 (매크로 활성 시 일일 리밸런싱)
- **python-telegram-bot v21** - 알림 + 명령어
- **pydantic-settings** - 설정 관리 (SecretStr 보호)
- **structlog** - JSON 구조화 로깅 + 민감정보 마스킹
- **exchange-calendars** - NYSE 마켓 캘린더
- **ta** - 기술적 분석 지표 라이브러리
- **fredapi** - FRED 경제 데이터 (금리, 인플레이션, 고용)
- **yfinance** - Yahoo Finance (섹터 ETF, VIX, 원자재, 환율)
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
│   ├── app.py               # 앱 오케스트레이터 (매크로 + 섹터 로테이션 루프)
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
│   ├── macro/               # 거시경제 데이터 + 섹터 로테이션
│   │   ├── fred_client.py   # FRED API (금리, 인플레이션, 고용)
│   │   ├── market_data.py   # VIX, 원자재, 환율 (yfinance)
│   │   ├── sector_rotation.py # 섹터 ETF 모멘텀/상대강도/순위
│   │   └── macro_score.py   # 종합 매크로 점수 (-1.0 ~ +1.0)
│   ├── strategy/            # AI/ML 매매 전략
│   │   ├── features.py      # 기술적 지표 24개 + 매크로 피처 10개
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
│       ├── models.py        # SQLAlchemy ORM (8개 테이블)
│       └── repository.py    # CRUD 연산
├── scripts/
│   ├── seed_historical.py   # 과거 OHLCV 데이터 다운로드
│   └── train_model.py       # LightGBM 모델 학습 + 백테스트
├── tests/
│   ├── conftest.py          # 공통 fixture (tmp DB, sample OHLCV)
│   └── unit/
│       ├── test_rate_limiter.py    # 토큰 버킷 4개 테스트
│       ├── test_features.py       # 기술적 지표 4개 테스트
│       ├── test_signals.py        # 시그널 생성 5개 테스트
│       ├── test_risk.py           # 리스크 관리 9개 테스트
│       ├── test_messages.py       # 메시지 포맷 4개 테스트
│       ├── test_macro_score.py    # 매크로 점수 계산 8개 테스트
│       ├── test_sector_rotation.py # 섹터 로테이션 11개 테스트
│       ├── test_macro_messages.py # 매크로 리포트 포맷 4개 테스트
│       └── test_macro_features.py # 매크로 피처 통합 5개 테스트
├── models/                  # ML 모델 파일 (.gitignored)
├── data/                    # SQLite DB (.gitignored)
├── notebooks/               # EDA, 모델 실험용
└── Dockerfile               # 리눅스 배포용
```

## 핵심 아키텍처

### 트레이딩 루프 (app.py)

**매크로 활성 시 (기본):**
```
APScheduler(매일 장 시작 후) → is_market_open()?
  → Yes →
    1. FRED + Yahoo Finance 매크로 데이터 수집 → DB 캐싱
    2. 매크로 점수 계산 (-1.0 ~ +1.0) → 주식 비중 결정
    3. 섹터 ETF 모멘텀/상대강도 순위 → 상위 3개 선정
    4. 보유 ETF 손절 체크
    5. 리밸런싱 (하위 섹터 매도 → 상위 섹터 매수)
    6. 매크로 리포트 Telegram 전송
  → No → skip
```

**매크로 비활성 시 (폴백):**
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
- **설정 클래스 구조**: `AppConfig` → `BrokerConfig`, `TradingConfig`, `ModelConfig`, `TelegramConfig`, `LoggingConfig`, `MacroConfig`, `FredApiConfig`

### DB 테이블 (db/models.py)
| 테이블 | 용도 | 주요 컬럼 |
|---|---|---|
| `ohlcv` | 시세 캐시 | symbol, dt, timeframe, OHLCV, volume |
| `signals` | ML 시그널 | symbol, signal, confidence, features(JSON) |
| `trades` | 거래 내역 | symbol, side, quantity, price, status, kis_order_id |
| `portfolio_snapshots` | 일일 스냅샷 | total_value, cash, holdings(JSON), pnl |
| `risk_events` | 리스크 이벤트 | event_type, symbol, details(JSON) |
| `system_state` | 시스템 상태 | key, value (키-밸류 저장) |
| `macro_data` | 매크로 데이터 캐시 | series_id, dt, value, source (fred/yahoo) |
| `sector_snapshots` | 섹터 분석 스냅샷 | snapshot_date, sector, etf_ticker, momentum, RS, rank |

### ML 모델 (strategy/model.py)
- **알고리즘**: LightGBM 3-class 분류 (UP / DOWN / HOLD)
- **타겟**: 향후 5일 수익률 방향 (UP: +2% 이상, DOWN: -2% 이하)
- **피처 24개 기술적 + 10개 매크로**: RSI, MACD, BB, SMA/EMA, ATR + 금리, VIX, 섹터 모멘텀 등
- **검증**: TimeSeriesSplit 5-fold CV + Walk-forward 백테스팅
- **모델 인터페이스**: `TradingModel` Protocol → 향후 LSTM 등으로 교체 가능
- **저장**: LightGBM 네이티브 포맷 (`.txt` + `.meta.json`) — pickle 사용하지 않음

### 리스크 관리 (strategy/risk.py)
- **포지션 한도**: 단일 ETF 최대 포트폴리오의 35% (`max_position_pct`, 상위 3개 섹터 기준)
- **손절**: 진입가 대비 8% 하락 시 시장가 강제 매도 (`stop_loss_pct`, ETF는 개별 종목보다 넓게)
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
| `/macro` | 거시경제 분석 리포트 | `app.py:_on_macro` |
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
FRED_API_KEY=...
```

### config/settings.yaml (트레이딩 설정)
```yaml
trading:
  mode: paper
  symbols: [AAPL, MSFT, NVDA, GOOGL, AMZN]  # 매크로 비활성 시 사용
  check_interval_minutes: 60
  max_position_pct: 0.35       # 단일 ETF 최대 비중 (1/3)
  stop_loss_pct: 0.08          # ETF 손절 기준 (8%)
  max_daily_loss_usd: 500.0
  order_type: MARKET
macro:
  enabled: true
  fred_series: [T10Y2Y, BAMLH0A0HYM2, FEDFUNDS, CPIAUCSL, UNRATE]
  sector_etfs: [XLK, XLV, XLF, XLE, XLP, XLY, XLI, XLU, SOXX]
  benchmark: SPY
  commodities: [GC=F, CL=F, DX-Y.NYB, HG=F]
  rebalance_frequency: daily   # daily | weekly
  top_sectors: 3               # 상위 N개 섹터에 투자
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

---

## Phase 7: 거시경제 기반 섹터 ETF 로테이션 전략 (설계)

### 개요

개별 종목 스크리닝 대신 **섹터 ETF를 직접 매매**합니다.
거시경제 데이터(FRED 금리 + VIX + 원자재/환율)로 매크로 환경을 판단하고,
**모멘텀 상위 섹터 ETF에 자금을 배분**하는 섹터 로테이션 전략입니다.

개별 종목 대비 장점:
- 종목 스크리닝 복잡도 제거 (시가총액/거래량 필터 불필요)
- KIS API 호출 대폭 감소 (12개 ETF vs 수백 개 종목)
- ETF는 자체 분산 효과 → 개별 종목 리스크 감소
- yfinance로 ETF 데이터 충분히 수집 가능 → API 의존도 낮음

### 변경되는 트레이딩 루프

```
APScheduler(매일 장 시작 후 1회) → is_market_open()?
  → Yes →
    1. 거시경제 데이터 수집 (FRED, Yahoo Finance)
    2. 매크로 점수 계산 → 전체 포지션 비중 결정
    3. 섹터 ETF 모멘텀/상대강도 순위 계산
    4. 상위 3개 섹터 ETF 선정
    5. ETF별:
       fetch_ohlcv → compute_features(기술적 + 매크로)
       → model.predict → generate_signal
       → risk.evaluate → 리밸런싱 주문 → db.log → telegram.notify
    6. 하위 섹터 ETF 보유 중이면 → 매도
    7. 거시경제 분석 리포트 Telegram 전송
  → No → skip
```

**핵심 변경: 1시간 간격 → 1일 1회 리밸런싱**
- 거시경제 데이터는 일간/월간 업데이트 → 시간 단위 확인 불필요
- 거래 비용(수수료 + 슬리피지) 절감
- 과매매(overtrading) 방지

### 거시경제 데이터 소스

#### 1. 금리 & 채권 (FRED API)
| 지표 | FRED Series ID | 설명 | 업데이트 주기 |
|---|---|---|---|
| 2-10년 스프레드 | `T10Y2Y` | 경기침체 선행지표 (역전 시 주의) | 일간 |
| 하이일드 스프레드 | `BAMLH0A0HYM2` | 신용 위험 지표 | 일간 |
| 연방기금금리 | `FEDFUNDS` | Fed 기준금리 | 월간 |
| CPI (소비자물가) | `CPIAUCSL` | 인플레이션 | 월간 |
| 실업률 | `UNRATE` | 고용 시장 | 월간 |

- **API**: `fredapi` 라이브러리 (FRED API Key 필요, 무료)
- **호출 제한**: 120 req/min
- **캐싱**: DB `macro_data` 테이블에 저장, 일간 데이터는 1일 1회만 갱신
- **중복 피처 제거**: 2년/10년 국채 개별값 대신 스프레드만 사용, CPI와 PCE 중 CPI만 사용

#### 2. 변동성 (Yahoo Finance)
| 지표 | 티커 | 설명 |
|---|---|---|
| VIX | `^VIX` | 시장 공포 지수 (20 이하: 안정, 30 이상: 공포) |

- **API**: `yfinance` 라이브러리 (무료, API 키 불필요)
- VIX9D, Put/Call Ratio 제거 — VIX 하나로 충분

#### 3. 매매 대상 섹터 ETF (Yahoo Finance)
| 섹터 | ETF | 설명 |
|---|---|---|
| 기술 | `XLK` | Technology Select Sector |
| 헬스케어 | `XLV` | Health Care Select Sector |
| 금융 | `XLF` | Financial Select Sector |
| 에너지 | `XLE` | Energy Select Sector |
| 필수소비재 | `XLP` | Consumer Staples |
| 임의소비재 | `XLY` | Consumer Discretionary |
| 산업재 | `XLI` | Industrial Select Sector |
| 유틸리티 | `XLU` | Utilities Select Sector |
| 반도체 | `SOXX` | iShares Semiconductor ETF |
| S&P500 | `SPY` | 벤치마크 + 중립 포지션용 |

- 소재(`XLB`), 부동산(`XLRE`), 통신(`XLC`) 제거 — 유동성/규모가 상대적으로 작음
- `SPY` 추가 — 벤치마크 비교 + 매크로 중립 시 기본 투자 대상

#### 4. 원자재 & 환율 (Yahoo Finance)
| 지표 | 티커 | 설명 |
|---|---|---|
| 금 | `GC=F` | Gold Futures (안전자산 수요) |
| 원유 WTI | `CL=F` | Crude Oil (에너지 섹터 연동) |
| 달러 인덱스 | `DX-Y.NYB` | USD 강세/약세 (수출주 영향) |
| 구리 | `HG=F` | Dr. Copper (경기 선행지표) |

### 섹터 로테이션 로직

#### 의사결정 파이프라인
```
1. 매크로 점수 계산 (macro_score: -1.0 ~ +1.0)
   - yield_spread: 스프레드 축소 추세 = 부정적, 확대 추세 = 긍정적
   - high_yield_spread: 상승 = 부정적 (신용 위험 증가)
   - VIX: < 20 = 긍정적, 20~30 = 중립, > 30 = 부정적
   - 구리/금 비율: 상승 = 경기 확장, 하락 = 경기 수축
   → 가중 평균으로 종합 점수 산출

2. 전체 포지션 비중 결정 (macro_score 기반)
   - 매크로 점수에 따라 주식 vs 현금 비율 조절

3. 섹터 순위 결정
   - 각 섹터 ETF의 20일 수익률 순위 (모멘텀)
   - 섹터 vs SPY 상대 강도 (relative strength)
   - 매크로-섹터 상관관계 가중치:
     금리 상승기 → XLF↑, XLK↓
     유가 상승 → XLE↑, XLY↓
     달러 약세 → XLI↑ (수출 수혜)
   → 종합 점수로 상위 3개 섹터 선정

4. 자금 배분
   - 상위 3개 섹터 ETF에 균등 배분 (각 33%)
   - 매크로 점수로 전체 투자 비중 조절
   - 나머지는 현금 (또는 매크로 중립 시 SPY)

5. 리밸런싱 (1일 1회)
   - 기존 보유 ETF와 새 선정 ETF 비교
   - 변동이 있을 때만 매매 실행 (불필요한 거래 방지)
```

#### 매크로 환경별 포지션 전략
| 매크로 점수 | 전략 | 주식 비중 | 투자 대상 |
|---|---|---|---|
| +0.5 이상 (강세) | 적극 매수 | 90% | 상위 3 섹터 ETF |
| 0 ~ +0.5 (약한 강세) | 선별 매수 | 70% | 상위 3 섹터 ETF |
| -0.5 ~ 0 (약한 약세) | 방어적 | 40% | SPY + 방어 섹터(XLP, XLU) |
| -0.5 이하 (약세) | 현금 보유 | 20% | XLP 또는 현금 |

### ML 피처 (축소: 기존 24개 기술적 + 매크로 10개 = 34개)

#### 매크로 피처 (신규 10개 — 상관관계 높은 피처 제거)
| 카테고리 | 피처 | 설명 |
|---|---|---|
| 금리 | `yield_spread_2_10` | 2-10년 스프레드 |
| 금리 | `yield_spread_change_20d` | 스프레드 20일 변화량 |
| 금리 | `high_yield_spread` | 하이일드 스프레드 |
| 변동성 | `vix` | VIX 현재값 |
| 변동성 | `vix_percentile_60d` | VIX 60일 백분위 (상대적 수준) |
| 섹터 | `sector_momentum_20d` | 해당 ETF 20일 수익률 |
| 섹터 | `sector_relative_strength` | 섹터 vs SPY 상대 강도 |
| 원자재 | `copper_gold_ratio_change` | 구리/금 비율 변화 (경기 지표) |
| 환율 | `dxy_change_20d` | 달러 인덱스 20일 변화율 |
| 매크로 | `macro_score` | 종합 거시경제 점수 |

**피처 수 34개 vs 학습 데이터**: ETF 9개 × 일봉 252일/년 × 3년 = ~6,800행 → 피처 대비 충분

### 벤치마크 비교 (필수)

모든 백테스트에서 아래 벤치마크와 비교:
- **SPY Buy & Hold**: 동일 기간 SPY 매수 후 보유
- **동일 가중 섹터 ETF**: 9개 섹터 ETF 균등 배분 + 월간 리밸런싱

비교 지표:
- 연환산 수익률 (CAGR)
- 최대 낙폭 (MDD)
- 샤프 비율 (Sharpe Ratio)
- 초과수익 (Alpha) vs SPY

**SPY를 일관되게 이기지 못하면 전략을 폐기하고 SPY 매수 후 보유로 전환**

### 새로운 모듈 구조

```
src/stockstock/
├── macro/                          # 거시경제 데이터 모듈 (신규)
│   ├── __init__.py
│   ├── fred_client.py              # FRED API 클라이언트 (금리, 인플레이션, 고용)
│   ├── market_data.py              # VIX, 원자재, 환율 수집 (yfinance)
│   ├── sector_rotation.py          # 섹터 ETF 모멘텀/상대강도 + 순위 결정
│   └── macro_score.py              # 종합 매크로 점수 계산
├── strategy/
│   ├── features.py                 # 기존 24개 + 매크로 10개 피처 통합 (수정)
│   ├── model.py                    # 피처 확장 반영 (수정)
│   └── ...
└── ...
```

### 새로운 DB 테이블

```sql
-- 거시경제 데이터 캐시
CREATE TABLE macro_data (
    id INTEGER PRIMARY KEY,
    series_id VARCHAR(50) NOT NULL,    -- FRED series ID 또는 Yahoo 티커
    dt VARCHAR(10) NOT NULL,           -- YYYY-MM-DD
    value FLOAT NOT NULL,
    source VARCHAR(20) NOT NULL,       -- 'fred', 'yahoo'
    fetched_at DATETIME,
    UNIQUE(series_id, dt)
);

-- 섹터 분석 스냅샷
CREATE TABLE sector_snapshots (
    id INTEGER PRIMARY KEY,
    snapshot_date VARCHAR(10) NOT NULL,
    sector VARCHAR(30) NOT NULL,
    etf_ticker VARCHAR(10) NOT NULL,
    momentum_20d FLOAT,
    momentum_60d FLOAT,
    relative_strength FLOAT,           -- vs SPY
    macro_sector_score FLOAT,          -- 매크로-섹터 상관 점수
    rank INTEGER,
    UNIQUE(snapshot_date, sector)
);
```

### 새로운 설정 (config/settings.yaml 확장)

```yaml
macro:
  enabled: true
  fred_series:
    - T10Y2Y
    - BAMLH0A0HYM2
    - FEDFUNDS
    - CPIAUCSL
    - UNRATE
  sector_etfs:                         # 매매 대상 섹터 ETF
    - XLK
    - XLV
    - XLF
    - XLE
    - XLP
    - XLY
    - XLI
    - XLU
    - SOXX
  benchmark: SPY                       # 벤치마크 + 중립 포지션
  commodities:
    - GC=F
    - CL=F
    - DX-Y.NYB
    - HG=F

trading:
  mode: live
  rebalance_frequency: daily           # daily | weekly
  top_sectors: 3                       # 상위 N개 섹터에 투자
  check_interval_minutes: 60           # 장 오픈 체크 간격 (리밸런싱은 1일 1회)
  max_position_pct: 0.35               # 단일 ETF 최대 비중 (1/3)
  stop_loss_pct: 0.08                  # ETF 손절 (개별 종목보다 넓게)
  max_daily_loss_usd: 500.0
  order_type: MARKET
```

### 새로운 환경변수 (.env 추가)

```
FRED_API_KEY=...                       # FRED API 키 (https://fred.stlouisfed.org/docs/api/api_key.html)
```

### 추가 의존성

```toml
# pyproject.toml에 추가
dependencies = [
    # 기존 의존성...
    "fredapi>=0.5.2",                  # FRED API 클라이언트
    "yfinance>=0.2.31",               # Yahoo Finance (섹터 ETF, VIX, 원자재)
]
```

### Telegram 거시경제 리포트

리밸런싱 실행 후 자동 전송 + `/macro` 명령어로 수동 조회 가능.

```
📊 거시경제 리포트 (2026-02-18)

■ 매크로 점수: +0.32 (약한 강세)
  → 주식 비중: 70%

■ 금리 환경
  2-10Y 스프레드: 0.45% (▲0.08)
  하이일드 스프레드: 3.21% (▼0.15)
  연방기금금리: 4.50%

■ 시장 변동성
  VIX: 18.5 (60일 백분위: 35%)

■ 원자재/환율
  구리/금 비율: ▲2.1% (경기 확장 신호)
  달러 인덱스: ▼1.3% (20일)
  원유 WTI: $72.40

■ 섹터 순위 (상위 3 → 매수)
  1. XLK (기술)    +4.2% | RS 1.15
  2. SOXX (반도체)  +3.8% | RS 1.12
  3. XLF (금융)    +2.9% | RS 1.05
  ---
  7. XLU (유틸리티) -1.2% | RS 0.88
  8. XLP (필수소비) -1.8% | RS 0.82
  9. XLE (에너지)  -2.5% | RS 0.75

■ 리밸런싱
  매수: XLK 30주, SOXX 15주
  매도: XLE 20주
  현금 비중: 30%
```

### 구현 순서

1. ~~**macro/fred_client.py** — FRED API 연동 + DB 캐싱~~ **완료**
2. ~~**macro/market_data.py** — VIX, 원자재, 환율 수집 (yfinance)~~ **완료**
3. ~~**macro/sector_rotation.py** — 섹터 ETF 모멘텀/상대강도/순위 계산~~ **완료**
4. ~~**macro/macro_score.py** — 종합 매크로 점수 계산 엔진~~ **완료**
5. ~~**db/models.py** — 새 테이블 2개 추가~~ **완료**
6. ~~**strategy/features.py** — 매크로 피처 통합 (기존 24개 + 신규 10개)~~ **완료**
7. **strategy/model.py** — ETF 대상 모델 재학습 (TODO)
8. ~~**app.py** — 트레이딩 루프 변경 (1일 1회 리밸런싱 + 섹터 로테이션)~~ **완료**
9. ~~**config.py** — MacroConfig 추가, TradingConfig 수정~~ **완료**
10. ~~**settings.yaml** — macro 섹션 추가, trading 섹션 수정~~ **완료**
11. **strategy/backtest.py** — SPY 벤치마크 비교 추가 (TODO)
12. **scripts/train_model.py** — 매크로 피처 + ETF 대상 재학습 (TODO)
13. ~~**테스트** — 각 모듈별 단위 테스트 추가~~ **완료** (55개)
