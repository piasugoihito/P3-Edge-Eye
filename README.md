# P3-Edge-Eye

**P3 プロトコルのエッジ側スキャンアプリ**。Mac のカメラまたは Raspberry Pi のカメラで QR コードをリアルタイムスキャンし、P3-Analyzer-Hub へ自動送信する。

---

## システム全体における位置づけ

```
[ラズパイ / Mac カメラ]
        │  QR スキャン
        ▼
[P3-Edge-Eye]  ← このリポジトリ
   └─ POST /scan → [P3-Analyzer-Hub]
                        ├─ GET /api/internal/packet-recovery/ → [P3 ウェブサーバー]
                        ├─ HMAC 検証 + RSA+AES 復号
                        └─ ラベル PNG 生成 → 印刷
```

---

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

```bash
cp .env.example .env
# .env を編集して各値を設定する
```

| 変数 | デフォルト | 説明 |
|---|---|---|
| `ANALYZER_HUB_URL` | `http://localhost:8001/scan` | P3-Analyzer-Hub の /scan エンドポイント |
| `RASPI_API_TOKEN` | （必須） | 認証トークン（Analyzer Hub の `RASPI_API_TOKEN` と一致させること） |
| `CAMERA_INDEX` | `0` | カメラデバイス番号（外付けカメラなら `1` など） |
| `COOLDOWN_SECONDS` | `5` | 同一トークンの二重送信防止クールダウン秒数 |

### 3. P3-Analyzer-Hub を先に起動しておく

```bash
# P3-Analyzer-Hub ディレクトリで
uvicorn api.raspi_api:app --host 0.0.0.0 --port 8001
```

### 4. スキャナー起動

```bash
python scanner.py
```

カメラウィンドウが開きます。QR コードをかざすと自動的に送信されます。終了は `q` キー。

---

## 動作フロー

1. カメラフレームを取得
2. `cv2.QRCodeDetector` で QR コードを検出
3. 同一トークンのクールダウン（デフォルト 5 秒）チェック
4. `POST http://localhost:8001/scan` へ送信
5. 結果をターミナルに表示

```
14:30:22 [INFO] [SCAN] QR 検出: TtuFCn0iIlHhSEIVrWgv...
14:30:23 [INFO] [SUCCESS] Token: TtuFCn0iIlHhSEIVrWgv... - Label generation triggered. (package_id=7, label=./output/label_000007_20260509_143023.png)
```

---

## ディレクトリ構成

```
P3-Edge-Eye/
├── scanner.py       # メインスクリプト
├── requirements.txt
├── .env.example     # 環境変数テンプレート
├── .gitignore
└── README.md
```

---

## Raspberry Pi への移植

Mac で動作確認後、ラズパイへの移植は以下の手順で行う。

```bash
# ラズパイ上で
git clone https://github.com/piasugoihito/P3-Edge-Eye.git
cd P3-Edge-Eye
pip install -r requirements.txt
cp .env.example .env
# .env の ANALYZER_HUB_URL をラップトップの IP に変更
# 例: ANALYZER_HUB_URL=http://192.168.1.10:8001/scan
python scanner.py
```

`CAMERA_INDEX=0` はラズパイカメラモジュール（`/dev/video0`）に対応する。
