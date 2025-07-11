"""
Airレジ 商品別売上 & 売上集計 CSV を毎日 1 回だけ取得し
Google ドライブ指定フォルダへアップロードするスクリプト
──────────────────────────────────
■ 事前準備（GitHub Actions の Secrets など）
  AIRREGI_ID        : Airレジログイン ID
  AIRREGI_PASS      : Airレジログイン PW
  DRIVE_FOLDER_ID   : アップロード先フォルダ ID
  SA_JSON           : Google サービスアカウント JSON 文字列

■ 依存ライブラリ
  pip install playwright google-api-python-client google-auth
  playwright install chromium
──────────────────────────────────
"""

import os, re, json, tempfile
from datetime import datetime, timezone, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery     import build
from playwright.sync_api           import sync_playwright

# ─── 定数 ───────────────────────────────────────
JST   = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).strftime("%Y%m%d")   # 例: 20250711 → ファイル名に使用

LOGIN_URL = "https://connect.airregi.jp/login?client_id=ARG"
PROD_URL  = "https://airregi.jp/CLP//view/salesListByMenu/"
KPI_URL   = "https://airregi.jp/CLP//view/salesList/#/"

# ─── Google Drive へアップロード ────────────────
def upload_to_drive(local_path: str, file_name: str,
                    folder_id: str, sa_json: str):
    creds = Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    drive = build("drive", "v3", credentials=creds)
    file_meta = {"name": file_name, "parents": [folder_id]}
    media     = {"mimeType": "text/csv", "body": open(local_path, "rb")}
    drive.files().create(body=file_meta, media_body=media).execute()
    print(f"✔ Google Drive へアップ: {file_name}")

# ─── Airレジ ログイン ────────────────────────────
def login(page, uid, pw):
    page.goto(LOGIN_URL, timeout=60000)
    page.fill("#account", uid)
    page.fill("#password", pw)
    page.click("input.primary")
    page.wait_for_url(re.compile(r"/(view/top|dashboard)"), timeout=60000)

# ─── カレンダーを「開始=終了=YYYYMMDD」へ合わせる ──
def set_calendar(page, ymd: str):
    y, m, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])
    page.click(".input-container")  # 日付欄
    while True:
        txt = page.text_content(".dates .switch")  # '2025年07月'
        yy, mm = int(txt[:4]), int(txt[5:7])
        if (yy, mm) == (y, m):
            break
        page.click("//tr[contains(@class,'movement')]/td[1]"
                   if (yy, mm) > (y, m)
                   else "//tr[contains(@class,'movement')]/td[last()]")
        page.wait_for_timeout(300)
    # 当月セルを開始・終了で 2 回クリック
    sel = (f"//table[contains(@class,'dates-table')]"
           f"//td[not(contains(@class,'old')) and not(contains(@class,'new'))]"
           f"/div[text()='{d}']")
    page.click(sel)
    page.click(sel)
    page.click(".btn-confirm")

# ─── 任意ボタン → 期待するダウンロードを保存 ──────────
def download_csv(page, click_selector: str, save_as: str,
                 timeout_ms: int = 60000):
    with page.expect_download(timeout=timeout_ms) as dl_info:
        page.click(click_selector)
    dl = dl_info.value
    dl.save_as(save_as)
    print(f"  ✔ ダウンロード完了: {save_as}")

# ─── メイン処理 ─────────────────────────────────
def main():
    uid       = os.getenv("AIRREGI_ID")
    pw        = os.getenv("AIRREGI_PASS")
    folder_id = os.getenv("DRIVE_FOLDER_ID")
    sa_json   = os.getenv("SA_JSON")
    if not all([uid, pw, folder_id, sa_json]):
        raise SystemExit("環境変数が足りません。Secrets を確認してください。")

    with tempfile.TemporaryDirectory() as tmpdir, sync_playwright() as p:
        browser  = p.chromium.launch(headless=True)
        context  = browser.new_context(accept_downloads=True)
        page     = context.new_page()
        login(page, uid, pw)

        # ① 商品別売上ページ
        page.goto(PROD_URL)
        set_calendar(page, TODAY)
        # (a) 検索 → CSV ボタンが現れるまで待機
        page.click("#btnSearch")
        page.wait_for_selector(".btn-CSV-DL", timeout=60000)
        # (b) CSV ダウンロード
        download_csv(page,
                     ".btn-CSV-DL",
                     f"{tmpdir}/商品別売上_{TODAY}-{TODAY}.csv",
                     timeout_ms=120000)

        # ② KPI（売上集計）ページ
        page.goto(KPI_URL)
        # ボタン１: まとめ CSV
        download_csv(page,
                     "button.pull-right.csv-download-button",
                     f"{tmpdir}/売上集計_{TODAY}.csv")
        # ボタン２: 詳細 CSV
        download_csv(page,
                     "button.salse-csv-dl",
                     f"{tmpdir}/売上集計詳細_{TODAY}.csv")

        # ③ Google Drive へ全ファイルアップロード
        for fn in os.listdir(tmpdir):
            upload_to_drive(os.path.join(tmpdir, fn), fn, folder_id, sa_json)

        context.close()
        browser.close()

# ─── エントリーポイント ─────────────────────────
if __name__ == "__main__":
    main()
