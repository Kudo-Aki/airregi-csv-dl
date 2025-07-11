"""
Airレジ 商品別売上 & 日別売上(売上集計) CSV を取得し
Google ドライブへアップロード → ログアウト → ブラウザ終了
──────────────────────────────────
必要 Secrets:
  AIRREGI_ID, AIRREGI_PASS, DRIVE_FOLDER_ID, SA_JSON
pip install playwright google-api-python-client google-auth
playwright install chromium
"""

import os, re, json, tempfile
from datetime import datetime, timezone, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery     import build
from playwright.sync_api           import sync_playwright

# ─── 共通定数 ────────────────────────────────────
JST   = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).strftime("%Y%m%d")

LOGIN_URL = "https://connect.airregi.jp/login?client_id=ARG"
PROD_URL  = "https://airregi.jp/CLP//view/salesListByMenu/"
KPI_URL   = "https://airregi.jp/CLP//view/salesList/#/"

# ─── Google Drive アップロード ───────────────────
def upload_to_drive(path, name, folder_id, sa_json):
    creds = Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    drive = build("drive", "v3", credentials=creds)
    meta  = {"name": name, "parents": [folder_id]}
    media = {"mimeType": "text/csv", "body": open(path, "rb")}
    drive.files().create(body=meta, media_body=media).execute()
    print(f"✔ Drive: {name}")

# ─── Playwright ユーティリティ ──────────────────
def click_when(page, sel, timeout=60000):
    page.wait_for_selector(sel, timeout=timeout)
    page.click(sel)

def download_csv(page, sel, save_as, timeout=120000):
    with page.expect_download(timeout=timeout) as dl_info:
        page.click(sel)
    dl_info.value.save_as(save_as)
    print(f"  ✔ DL: {os.path.basename(save_as)}")

# ─── メイン処理 ──────────────────────────────────
def main():
    uid, pw  = os.getenv("AIRREGI_ID"), os.getenv("AIRREGI_PASS")
    folder, sj = os.getenv("DRIVE_FOLDER_ID"), os.getenv("SA_JSON")
    if not all([uid, pw, folder, sj]):
        raise SystemExit("Secrets 未設定")

    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(accept_downloads=True)
        page    = ctx.new_page()

        # ① ログイン
        page.goto(LOGIN_URL, timeout=60000)
        page.fill("#account", uid)
        page.fill("#password", pw)
        page.click("input.primary")
        page.wait_for_url(re.compile(r"/(view/top|dashboard)"), timeout=60000)

        # ② 商品別売上
        page.goto(PROD_URL)
        click_when(page, "#btnSearch")          # デフォルト日付で検索
        click_when(page, ".btn-CSV-DL")
        download_csv(page,
                     ".btn-CSV-DL",
                     f"{tmp}/商品別売上_{TODAY}-{TODAY}.csv")

        # ③ サイドバー → 日別売上
        click_when(page, 'a[data-sc="LinkSalesList"]')
        page.wait_for_url(re.compile(r"/view/salesList/?"), timeout=60000)

        # ④ 青ボタンを押し、緑ボタン出現を待つ
        click_when(page, "button.pull-right.csv-download-button")
        click_when(page, "button.salse-csv-dl")   # まだダウンロードしない
        download_csv(page,
                     "button.salse-csv-dl",
                     f"{tmp}/売上集計_{TODAY}.csv")

        # ⑤ Drive へアップロード
        for fn in os.listdir(tmp):
            upload_to_drive(os.path.join(tmp, fn), fn, folder, sj)

        # ⑥ ログアウト
        click_when(page, "li.cmn-hdr-account")
        click_when(page, "a.cmn-hdr-logout-link")
        page.wait_for_url(re.compile(r"/login"), timeout=60000)
        print("✔ ログアウト完了")

        ctx.close(); browser.close(); print("✔ 完了")

# ────────────────────────────────────────────────
if __name__ == "__main__":
    main()
