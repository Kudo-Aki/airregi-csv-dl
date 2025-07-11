"""
Airレジ 商品別売上 & 売上集計 CSV を毎日 1 回だけ取得し
Google ドライブ指定フォルダへアップロードするスクリプト
──────────────────────────────────
■ 事前準備
  環境変数:
    AIRREGI_ID        : Airレジログイン ID
    AIRREGI_PASS      : Airレジログイン PW
    DRIVE_FOLDER_ID   : アップロード先フォルダ ID
    SA_JSON           : Google サービスアカウント JSON 文字列
──────────────────────────────────
pip install python-dotenv playwright google-api-python-client google-auth
playwright install chromium
"""

import os, re, time, asyncio, base64, json, tempfile
from datetime import datetime, timezone, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery     import build
from playwright.sync_api           import sync_playwright

JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).strftime("%Y%m%d")   # 20250711 → ファイル名に使用

LOGIN_URL      = "https://connect.airregi.jp/login?client_id=ARG"
PROD_URL       = "https://airregi.jp/CLP//view/salesListByMenu/"
KPI_URL        = "https://airregi.jp/CLP//view/salesList/#/"

def upload_to_drive(path: str, file_name: str, folder_id: str, sa_json: str):
    creds = Credentials.from_service_account_info(json.loads(sa_json), scopes=["https://www.googleapis.com/auth/drive.file"])
    drive = build("drive", "v3", credentials=creds)
    file_metadata = {"name": file_name, "parents": [folder_id]}
    media_body = {"mimeType": "text/csv", "body": open(path, "rb")}
    drive.files().create(body=file_metadata, media_body=media_body).execute()
    print(f"✔ Google Drive へアップロード完了: {file_name}")

def login(page, uid, pw):
    page.goto(LOGIN_URL, timeout=60000)
    page.fill("#account", uid)
    page.fill("#password", pw)
    page.click("input.primary")
    page.wait_for_url(re.compile(r"/(view/top|dashboard)"), timeout=60000)

def set_calendar(page, ymd:str):
    """カレンダーを『開始=終了=今日』に合わせる"""
    y, m, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])
    page.click(".input-container")              # 日付欄
    while True:
        txt = page.text_content(".dates .switch")   # '2025年07月'
        yy, mm = int(txt[:4]), int(txt[5:7])
        if (yy, mm) == (y, m):
            break
        page.click("//tr[contains(@class,'movement')]/td[1]" if (yy, mm) > (y, m)
                   else "//tr[contains(@class,'movement')]/td[last()]")
        page.wait_for_timeout(300)

    page.click(f"//table[contains(@class,'dates-table')]"
               f"//td[not(contains(@class,'old')) and not(contains(@class,'new'))]/div[text()='{d}']")
    page.click(f"//table[contains(@class,'dates-table')]"
               f"//td[not(contains(@class,'old')) and not(contains(@class,'new'))]/div[text()='{d}']")
    page.click(".btn-confirm")

def download_csv(page, wait_for, save_as):
    """CSV ダウンロードボタン → 実ファイル保存"""
    with page.expect_download() as dl_info:
        page.click(wait_for)
    dl = dl_info.value
    tmp_path = dl.path()
    dl.save_as(save_as)
    print(f"  ✔ ダウンロード完了: {save_as}")

def main():
    uid = os.getenv("AIRREGI_ID")
    pw  = os.getenv("AIRREGI_PASS")
    folder_id = os.getenv("DRIVE_FOLDER_ID")
    sa_json   = os.getenv("SA_JSON")
    if not all([uid, pw, folder_id, sa_json]):
        raise SystemExit("環境変数が足りません")

    with tempfile.TemporaryDirectory() as tmpdir, sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page    = context.new_page()
        login(page, uid, pw)

        # ① 商品別売上
        page.goto(PROD_URL)
        set_calendar(page, TODAY)
        download_csv(page, "#btnSearch", f"{tmpdir}/商品別売上_{TODAY}-{TODAY}.csv")

        # ② KPI（売上集計）
        page.goto(KPI_URL)
        download_csv(page,
                     "button.pull-right.csv-download-button",
                     f"{tmpdir}/売上集計_{TODAY}.csv")
        download_csv(page,
                     "button.salse-csv-dl",
                     f"{tmpdir}/売上集計詳細_{TODAY}.csv")

        # ③ Google Drive へアップ
        for fn in os.listdir(tmpdir):
            upload_to_drive(f"{tmpdir}/{fn}", fn, folder_id, sa_json)

        context.close()
        browser.close()

if __name__ == "__main__":
    main()
