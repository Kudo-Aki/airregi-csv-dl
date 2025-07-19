"""
Airレジ CSV 自動取得 → Google Drive(ServiceAccount) → ログアウト（失敗しても無視）
────────────────────────────────────────────
必要な Secrets
  AIRREGI_ID          : Airレジ ログイン ID（メール）
  AIRREGI_PASS        : 同パスワード
  DRIVE_FOLDER_ID     : アップロード先フォルダ ID
  GDRIVE_SA_JSON      : サービスアカウント鍵 JSON を base64 -w0 した文字列
"""

import os, re, json, base64, tempfile
from datetime import datetime, timezone, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ─── 定数 ───────────────────────────────────────
JST   = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).strftime("%Y%m%d")

LOGIN_URL = "https://connect.airregi.jp/login?client_id=ARG"
PROD_URL  = "https://airregi.jp/CLP//view/salesListByMenu/"
KPI_URL   = "https://airregi.jp/CLP//view/salesList/#/"

# ─── Drive アップロード（サービスアカウント版） ───────────────────────
def upload_to_drive(path: str, name: str, folder: str) -> None:
    """CSV を Google Drive フォルダへアップロード"""
    sa_b64 = os.getenv("GDRIVE_SA_JSON")
    if not sa_b64:
        raise SystemExit("❌ GDRIVE_SA_JSON が未設定です")

    sa_info = json.loads(base64.b64decode(sa_b64))
    creds   = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    drive   = build("drive", "v3", credentials=creds, cache_discovery=False)
    media   = MediaFileUpload(path, mimetype="text/csv", resumable=False)

    drive.files().create(
        body={"name": name, "parents": [folder]},
        media_body=media
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
def main() -> None:
    uid    = os.getenv("AIRREGI_ID")
    pw     = os.getenv("AIRREGI_PASS")
    folder = os.getenv("DRIVE_FOLDER_ID")
    if not all([uid, pw, folder, os.getenv("GDRIVE_SA_JSON")]):
        raise SystemExit("❌ Secrets が不足しています")

    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        page = (
            p.chromium
            .launch(headless=True)
            .new_context(accept_downloads=True)
            .new_page()
        )

        # ① ログイン
        page.goto(LOGIN_URL, timeout=60_000)
        page.fill("#account", uid)
        page.fill("#password", pw)
        page.click("input.primary")
        page.wait_for_url(re.compile(r"/(view/top|dashboard)"), timeout=60_000)

        # ② 商品別売上
        page.goto(PROD_URL)
        click_when(page, "#btnSearch")
        click_when(page, ".btn-CSV-DL")
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
