"""ML 모델 모듈.

LightGBM 기반 주가 방향 예측 모델을 관리합니다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from stockstock.logging_config import get_logger
from stockstock.strategy.features import get_feature_columns

log = get_logger(__name__)

# 예측 레이블: 향후 5일 수익률 기반
FORWARD_DAYS = 5
LABEL_UP_THRESHOLD = 0.02    # +2% 이상 → UP
LABEL_DOWN_THRESHOLD = -0.02  # -2% 이하 → DOWN


class TradingModel(Protocol):
    """트레이딩 모델 인터페이스."""

    def train(self, df: pd.DataFrame) -> dict: ...
    def predict(self, df: pd.DataFrame) -> tuple[str, float]: ...
    def save(self, path: str) -> None: ...
    def load(self, path: str) -> None: ...


class LGBMTradingModel:
    """LightGBM 기반 트레이딩 모델."""

    VERSION = "lgbm_v1"

    def __init__(self) -> None:
        self._model: lgb.LGBMClassifier | None = None
        self._booster: lgb.Booster | None = None  # 로드된 모델용
        self._classes: np.ndarray | None = None  # 로드된 모델의 클래스 레이블
        self._feature_cols = get_feature_columns()

    def _create_labels(self, df: pd.DataFrame) -> pd.Series:
        """향후 N일 수익률 기반 레이블을 생성합니다.

        마지막 FORWARD_DAYS 행은 미래 데이터 부재로 NaN 반환.
        """
        forward_return = df["close"].shift(-FORWARD_DAYS) / df["close"] - 1

        # NaN인 행은 레이블도 NaN (학습에서 제외됨)
        labels = pd.Series(np.nan, index=df.index, dtype=object)
        valid = forward_return.notna()
        labels[valid & (forward_return > LABEL_UP_THRESHOLD)] = "UP"
        labels[valid & (forward_return < LABEL_DOWN_THRESHOLD)] = "DOWN"
        not_up = ~(forward_return > LABEL_UP_THRESHOLD)
        not_down = ~(forward_return < LABEL_DOWN_THRESHOLD)
        hold_mask = valid & not_up & not_down
        labels[hold_mask] = "HOLD"

        return labels

    def train(self, df: pd.DataFrame) -> dict:
        """모델을 학습합니다.

        Args:
            df: 기술적 지표가 계산된 DataFrame

        Returns:
            학습 결과 메트릭 딕셔너리
        """
        labels = self._create_labels(df)

        # 레이블이 없는 마지막 N행 제거
        valid_mask = labels.isin(["UP", "DOWN", "HOLD"])
        X = df.loc[valid_mask, self._feature_cols]
        y = labels[valid_mask]

        # 시계열 교차 검증
        tscv = TimeSeriesSplit(n_splits=5)
        scores = []

        for train_idx, val_idx in tscv.split(X):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            model = lgb.LGBMClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                num_leaves=31,
                subsample=0.8,
                colsample_bytree=0.8,
                class_weight="balanced",
                random_state=42,
                verbosity=-1,
            )
            model.fit(X_train, y_train)
            score = model.score(X_val, y_val)
            scores.append(score)

        # 전체 데이터로 최종 모델 학습
        self._model = lgb.LGBMClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            class_weight="balanced",
            random_state=42,
            verbosity=-1,
        )
        self._model.fit(X, y)

        metrics = {
            "cv_scores": scores,
            "mean_cv_score": float(np.mean(scores)),
            "std_cv_score": float(np.std(scores)),
            "train_samples": len(X),
            "label_distribution": y.value_counts().to_dict(),
        }

        log.info("model_trained", **metrics)
        return metrics

    def predict(self, df: pd.DataFrame) -> tuple[str, float]:
        """최신 데이터에 대한 예측을 수행합니다.

        Returns:
            (signal, confidence) 튜플.
            signal: "UP", "DOWN", "HOLD"
            confidence: 0.0~1.0
        """
        if not self.is_loaded:
            raise RuntimeError("모델이 로드되지 않았습니다. train() 또는 load()를 먼저 호출하세요.")

        # 가장 최근 행의 피처 사용
        X = df[self._feature_cols].iloc[[-1]]

        if self._model is not None:
            # train()으로 학습된 모델 — LGBMClassifier API 사용
            prediction = self._model.predict(X)[0]
            probabilities = self._model.predict_proba(X)[0]
            classes = self._model.classes_
        else:
            # load()로 로드된 모델 — Booster API 직접 사용
            raw_pred = self._booster.predict(X)  # type: ignore[union-attr]
            # 다중 클래스: (1, n_classes) 형태의 확률 반환
            probabilities = raw_pred[0]
            pred_idx = int(np.argmax(probabilities))
            classes = self._classes  # type: ignore[assignment]
            prediction = classes[pred_idx]

        confidence = float(max(probabilities))

        log.info(
            "prediction_made",
            prediction=prediction,
            confidence=confidence,
            probabilities=dict(zip(classes, probabilities.tolist())),
        )

        return str(prediction), confidence

    def save(self, path: str) -> None:
        """모델을 파일로 저장합니다 (LightGBM 네이티브 포맷)."""
        if self._model is None:
            raise RuntimeError("저장할 모델이 없습니다.")
        model_path = Path(path)
        model_path.parent.mkdir(parents=True, exist_ok=True)

        # LightGBM 네이티브 저장 (pickle 대신 안전한 텍스트 포맷)
        self._model.booster_.save_model(str(model_path))

        # 메타데이터 별도 저장
        meta_path = model_path.with_suffix(".meta.json")
        meta = {
            "version": self.VERSION,
            "classes": list(self._model.classes_),
            "n_estimators": self._model.n_estimators,
        }
        meta_path.write_text(json.dumps(meta))
        log.info("model_saved", path=path)

    def load(self, path: str) -> None:
        """모델을 파일에서 로드합니다 (LightGBM 네이티브 포맷)."""
        model_path = Path(path)
        meta_path = model_path.with_suffix(".meta.json")

        self._booster = lgb.Booster(model_file=str(model_path))
        meta = json.loads(meta_path.read_text())
        self._classes = np.array(meta["classes"])

        log.info("model_loaded", path=path, version=meta.get("version"))

    @property
    def is_loaded(self) -> bool:
        return self._model is not None or self._booster is not None
