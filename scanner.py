#!/usr/bin/env python3
"""
scanner.py — P3-Edge-Eye
========================
Mac のカメラ（または Raspberry Pi のカメラ）でリアルタイムに QR コードをスキャンし、
P3-Analyzer-Hub の /scan エンドポイントへ自動送信するスクリプト。

使い方:
    python scanner.py

依存:
    pip install -r requirements.txt

設定:
    .env.example をコピーして .env を作成し、各値を設定すること。
"""

import os
import sys
import time
import json
import logging
from datetime import datetime

import cv2
import requests
from dotenv import load_dotenv

# ============================================================
# 設定読み込み
# ============================================================

load_dotenv()

ANALYZER_HUB_URL  = os.environ.get('ANALYZER_HUB_URL',  'http://localhost:8001/scan')
RASPI_API_TOKEN   = os.environ.get('RASPI_API_TOKEN',   '')
CAMERA_INDEX      = int(os.environ.get('CAMERA_INDEX',   '0'))
COOLDOWN_SECONDS  = float(os.environ.get('COOLDOWN_SECONDS', '5'))

# ============================================================
# ロガー設定
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('P3-Edge-Eye')

# ============================================================
# API 送信
# ============================================================

def send_to_hub(address_token: str) -> bool:
    """
    P3-Analyzer-Hub の /scan エンドポイントへ POST する。

    Args:
        address_token: QR コードから読み取ったトークン文字列

    Returns:
        True: 送信成功（HTTP 2xx）
        False: 送信失敗（ネットワークエラー・非 2xx）
    """
    headers = {
        'X-Raspi-Token': RASPI_API_TOKEN,
        'Content-Type':  'application/json',
    }
    payload = {
        'address_token':     address_token,
        'payment_signature': 'DUMMY_SIG',   # Phase 2 で実際の署名に差し替え
    }

    try:
        resp = requests.post(
            ANALYZER_HUB_URL,
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False),
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                log.info(
                    '[SUCCESS] Token: %s - Label generation triggered. '
                    '(package_id=%s, label=%s)',
                    address_token[:16] + '...',
                    data.get('package_id', 'N/A'),
                    data.get('label_path', 'N/A'),
                )
            else:
                log.warning(
                    '[WARN] Token: %s - Hub returned error: %s',
                    address_token[:16] + '...',
                    data.get('error', '不明なエラー'),
                )
            return True

        else:
            log.error(
                '[ERROR] Token: %s - HTTP %d: %s',
                address_token[:16] + '...',
                resp.status_code,
                resp.text[:200],
            )
            return False

    except requests.exceptions.ConnectionError:
        log.error(
            '[ERROR] Analyzer Hub に接続できません: %s\n'
            '        → uvicorn api.raspi_api:app --port 8001 が起動しているか確認してください。',
            ANALYZER_HUB_URL,
        )
        return False

    except requests.exceptions.Timeout:
        log.error('[ERROR] Analyzer Hub へのリクエストがタイムアウトしました。')
        return False

    except Exception as e:
        log.error('[ERROR] 予期しないエラー: %s', e)
        return False


# ============================================================
# QR スキャンループ
# ============================================================

def run_scanner():
    """
    カメラを開いてリアルタイムで QR コードをスキャンするメインループ。

    - OpenCV の QRCodeDetector でフレームごとに QR を検知
    - 検知したトークンを send_to_hub() で送信
    - COOLDOWN_SECONDS 秒間は同一トークンを無視（二重送信防止）
    - 'q' キーで終了
    """
    log.info('P3-Edge-Eye 起動中...')
    log.info('  Analyzer Hub URL : %s', ANALYZER_HUB_URL)
    log.info('  Camera Index     : %d', CAMERA_INDEX)
    log.info('  Cooldown         : %.1f 秒', COOLDOWN_SECONDS)
    log.info('  終了するには "q" キーを押してください。')

    # カメラオープン
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        log.error(
            'カメラ（index=%d）を開けませんでした。\n'
            '  → CAMERA_INDEX を .env で変更するか、カメラの接続を確認してください。',
            CAMERA_INDEX,
        )
        sys.exit(1)

    # QR デコーダー初期化
    detector = cv2.QRCodeDetector()

    # クールダウン管理: {token_str: last_sent_timestamp}
    cooldown_map: dict[str, float] = {}

    log.info('スキャン開始。カメラウィンドウに QR コードをかざしてください。')

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                log.warning('フレームの取得に失敗しました。カメラを確認してください。')
                time.sleep(0.5)
                continue

            # QR コード検出
            data, bbox, _ = detector.detectAndDecode(frame)

            now = time.monotonic()

            if data:
                token = data.strip()

                # クールダウンチェック
                last_sent = cooldown_map.get(token, 0.0)
                if now - last_sent < COOLDOWN_SECONDS:
                    remaining = COOLDOWN_SECONDS - (now - last_sent)
                    # クールダウン中はフレームに表示するだけ（ログは出さない）
                    _draw_cooldown(frame, bbox, remaining)
                else:
                    # 送信
                    log.info('[SCAN] QR 検出: %s...', token[:24])
                    cooldown_map[token] = now
                    send_to_hub(token)
                    _draw_success(frame, bbox)
            else:
                _draw_idle(frame)

            # ウィンドウ表示
            cv2.imshow('P3-Edge-Eye  |  press Q to quit', frame)

            # 'q' キーで終了
            if cv2.waitKey(1) & 0xFF == ord('q'):
                log.info('終了します。')
                break

    except KeyboardInterrupt:
        log.info('Ctrl+C を受信しました。終了します。')

    finally:
        cap.release()
        cv2.destroyAllWindows()


# ============================================================
# 描画ヘルパー
# ============================================================

def _draw_success(frame, bbox):
    """スキャン成功時: 緑の枠 + SUCCESS テキスト"""
    if bbox is not None:
        _draw_bbox(frame, bbox, color=(0, 255, 0))
    cv2.putText(
        frame, 'SENT TO HUB',
        (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2,
    )


def _draw_cooldown(frame, bbox, remaining: float):
    """クールダウン中: 黄色の枠 + 残り秒数"""
    if bbox is not None:
        _draw_bbox(frame, bbox, color=(0, 220, 255))
    cv2.putText(
        frame, f'COOLDOWN {remaining:.1f}s',
        (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 220, 255), 2,
    )


def _draw_idle(frame):
    """待機中: 右下に待機メッセージ"""
    h, w = frame.shape[:2]
    cv2.putText(
        frame, 'Waiting for QR...',
        (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1,
    )


def _draw_bbox(frame, bbox, color=(0, 255, 0)):
    """QR コードの検出枠を描画"""
    import numpy as np
    pts = bbox.astype(int).reshape((-1, 1, 2))
    cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=3)


# ============================================================
# エントリーポイント
# ============================================================

if __name__ == '__main__':
    # 設定チェック
    if not RASPI_API_TOKEN:
        log.warning(
            'RASPI_API_TOKEN が設定されていません。\n'
            '  → .env に RASPI_API_TOKEN=<トークン> を設定してください。'
        )

    run_scanner()
