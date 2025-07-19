"""
Airレジ CSV 自動取得 → Google Drive(OAuth) → ログアウト（失敗しても無視）
────────────────────────────────────────────
Secrets
  AIRREGI_ID, AIRREGI_PASS, DRIVE_FOLDER_ID,
  OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, OAUTH_REFRESH_TOKEN
"""

import os, re, tempfile
from datetime import datetime, timezone, timedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ─── 定数 ───────────────────────────────────────
JST   = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).strftime("%Y%m%d")

LOGIN_URL = "https://connect.airregi.jp/login?client_id=ARG"
PROD_URL  = "https://airregi.jp/CLP//view/salesListByMenu/"
KPI_URL   = "https://airregi.jp/CLP//view/salesList/#/"

# ─── Drive アップロード ─────────────────────────
def upload_to_drive(path, name, folder):
    creds = Credentials(
        None,
        refresh_token=os.getenv("OAUTH_REFRESH_TOKEN"),
        client_id=os.getenv("OAUTH_CLIENT_ID"),
        client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    creds.refresh(Request())
    drive = build("drive", "v3", credentials=creds)
    media = MediaFileUpload(path, mimetype="text/csv", resumable=False)
    drive.files().create(
        body={"name": name, "parents": [folder]},
        media_body=media,
        fields="id"
    ).execute()
    print(f"✔ Drive: {name}")

# ─── Playwright helper ─────────────────────────
def click_when(page, sel, timeout=60_000):
    page.wait_for_selector(sel, timeout=timeout)
    page.click(sel)

def download_csv(page, sel, save_as):
    with page.expect_download(timeout=120_000) as dl:
        page.click(sel)
    dl.value.save_as(save_as)
    print(f"  ✔ DL: {os.path.basename(save_as)}")

# ─── メイン ────────────────────────────────────
def main():
    uid = os.getenv("AIRREGI_ID"); pw = os.getenv("AIRREGI_PASS")
    folder = os.getenv("DRIVE_FOLDER_ID")
    oauth_ok = all(os.getenv(k) for k in (
        "OAUTH_CLIENT_ID", "OAUTH_CLIENT_SECRET", "OAUTH_REFRESH_TOKEN"))
    if not all([uid, pw, folder, oauth_ok]):
        raise SystemExit("❌ Secrets が不足しています")

    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        page = p.chromium.launch(headless=True)\
                 .new_context(accept_downloads=True).new_page()

        # ① ログイン
        page.goto(LOGIN_URL, timeout=60_000)
        page.fill("#account", uid); page.fill("#password", pw)
        page.click("input.primary")
        page.wait_for_url(re.compile(r"/(view/top|dashboard)"), timeout=60_000)

        # ② 商品別売上
        page.goto(PROD_URL)
        click_when(page, "#btnSearch"); click_when(page, ".btn-CSV-DL")
        download_csv(page, ".btn-CSV-DL",
                     f"{tmp}/商品別売上_{TODAY}-{TODAY}.csv")

        # ③ 日別売上
        click_when(page, 'a[data-sc="LinkSalesList"]')
        page.wait_for_url(re.compile(r"/view/salesList"), timeout=60_000)
        click_when(page, "button.pull-right.csv-download-button")
        click_when(page, "button.salse-csv-dl")
        download_csv(page, "button.salse-csv-dl",
                     f"{tmp}/売上集計_{TODAY}.csv")

        # ④ Drive へアップロード
        for fn in os.listdir(tmp):
            upload_to_drive(os.path.join(tmp, fn), fn, folder)

        # ⑤ ログアウト（失敗しても続行）
        try:
            click_when(page, "li.cmn-hdr-account")
            click_when(page, "a.cmn-hdr-logout-link")
            page.wait_for_selector("#account", timeout=30_000)
            print("✔ ログアウト完了")
        except PWTimeout:
            print("⚠ ログアウト確認をスキップ（タイムアウト）")

        page.context.close()
        page.context.browser.close()
        print("✔ すべて完了しました")

if __name__ == "__main__":
    main()
