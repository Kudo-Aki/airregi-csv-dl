"""
Airレジ 商品別売上 + 日別売上(集計・詳細) CSV を取得し
Google ドライブへアップロード後、ログアウトしてブラウザを閉じる
──────────────────────────────────
■ 必要 Secrets / 環境変数
  AIRREGI_ID        : Airレジ ログイン ID
  AIRREGI_PASS      : Airレジ パスワード
  DRIVE_FOLDER_ID   : 置きたいフォルダ ID
  SA_JSON           : サービスアカウント鍵 JSON 文字列
──────────────────────────────────
pip install playwright google-api-python-client google-auth
playwright install chromium
"""

import os, re, json, tempfile
from datetime import datetime, timezone, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery     import build
from playwright.sync_api           import sync_playwright

# ─── 定数 ───────────────────────────────────────
JST   = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).strftime("%Y%m%d")  # 例: 20250711

LOGIN_URL = "https://connect.airregi.jp/login?client_id=ARG"
PROD_URL  = "https://airregi.jp/CLP//view/salesListByMenu/"
KPI_URL   = "https://airregi.jp/CLP//view/salesList/#/"

# ─── Google Drive ───────────────────────────────
def upload_to_drive(local_path, file_name, folder_id, sa_json):
    creds = Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    drive = build("drive", "v3", credentials=creds)
    meta  = {"name": file_name, "parents": [folder_id]}
    media = {"mimeType": "text/csv", "body": open(local_path, "rb")}
    drive.files().create(body=meta, media_body=media).execute()
    print(f"✔ Drive にアップ: {file_name}")

# ─── Playwright ユーティリティ ─────────────────
def wait_and_click(page, selector, timeout=60000):
    page.wait_for_selector(selector, timeout=timeout)
    page.click(selector)

def download_csv(page, click_sel, save_as, timeout=120000):
    with page.expect_download(timeout=timeout) as dl_info:
        page.click(click_sel)
    dl_info.value.save_as(save_as)
    print(f"  ✔ DL: {os.path.basename(save_as)}")

# ─── メイン ───────────────────────────────────
def main():
    uid = os.getenv("AIRREGI_ID")
    pw  = os.getenv("AIRREGI_PASS")
    folder_id = os.getenv("DRIVE_FOLDER_ID")
    sa_json   = os.getenv("SA_JSON")
    if not all([uid, pw, folder_id, sa_json]):
        raise SystemExit("Secrets が不足しています。")

    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(accept_downloads=True)
        page    = ctx.new_page()

        # ── ① ログイン ────────────────────────
        page.goto(LOGIN_URL, timeout=60000)
        page.fill("#account", uid)
        page.fill("#password", pw)
        page.click("input.primary")
        page.wait_for_url(re.compile(r"/(view/top|dashboard)"), timeout=60000)

        # ── ② 商品別売上 ────────────────────
        page.goto(PROD_URL)
        wait_and_click(page, "#btnSearch")                # デフォルト日付で検索
        wait_and_click(page, ".btn-CSV-DL")               # CSV ボタンが出現
        download_csv(page,
                     ".btn-CSV-DL",
                     f"{tmp}/商品別売上_{TODAY}-{TODAY}.csv")

        # ── ③ ナビメニューから日別売上へ遷移 ─────
        # a[data-sc="LinkSalesList"] がサイドメニューの「日別売上」
        wait_and_click(page, 'a[data-sc="LinkSalesList"]')
        page.wait_for_url(re.compile(r"/view/salesList/?"), timeout=60000)

        # ── ④ 日別売上 CSV（集計 + 詳細）────────
        download_csv(page,
                     "button.pull-right.csv-download-button",
                     f"{tmp}/売上集計_{TODAY}.csv")
        download_csv(page,
                     "button.salse-csv-dl",
                     f"{tmp}/売上集計詳細_{TODAY}.csv")

        # ── ⑤ Drive へアップロード ─────────────
        for fn in os.listdir(tmp):
            upload_to_drive(os.path.join(tmp, fn), fn, folder_id, sa_json)

        # ── ⑥ ログアウト ─────────────────────
        wait_and_click(page, "li.cmn-hdr-account")
        wait_and_click(page, "a.cmn-hdr-logout-link")
        page.wait_for_url(re.compile(r"/login"), timeout=60000)
        print("✔ ログアウト完了")

        ctx.close()
        browser.close()
        print("✔ ブラウザを閉じました")

# ─── エントリーポイント ──────────────────────
if __name__ == "__main__":
    main()
