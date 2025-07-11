"""
Airレジ 商品別売上 & 売上集計 CSV を毎日 1 回だけ取得し
Google ドライブ指定フォルダへアップロードするスクリプト
──────────────────────────────────
■ 事前準備（GitHub Actions の Secrets 等）
  AIRREGI_ID        : Airレジログイン ID
  AIRREGI_PASS      : Airレジログイン PW
  DRIVE_FOLDER_ID   : アップロード先フォルダ ID
  SA_JSON           : Google サービスアカウント JSON 文字列
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
TODAY = datetime.now(JST).strftime("%Y%m%d")

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

# ─── ログイン ───────────────────────────────────
def login(page, uid, pw):
    page.goto(LOGIN_URL, timeout=60000)
    page.fill("#account", uid)
    page.fill("#password", pw)
    page.click("input.primary")
    page.wait_for_url(re.compile(r"/(view/top|dashboard)"), timeout=60000)

# ─── カレンダーを指定日に合わせる ───────────────
def set_calendar(page, ymd):
    y, m, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])
    page.click(".input-container")
    while True:
        txt = page.text_content(".dates .switch")  # '2025年07月'
        yy, mm = int(txt[:4]), int(txt[5:7])
        if (yy, mm) == (y, m):
            break
        page.click("//tr[contains(@class,'movement')]/td[1]" if (yy, mm) > (y, m)
                   else "//tr[contains(@class,'movement')]/td[last()]")
        page.wait_for_timeout(300)
    sel = (f"//table[contains(@class,'dates-table')]"
           f"//td[not(contains(@class,'old')) and not(contains(@class,'new'))]/div[text()='{d}']")
    page.click(sel)
    page.click(sel)
    page.click(".btn-confirm")

# ─── 汎用 DL ───────────────────────────────────
def download_csv(page, click_sel, save_as, timeout=120000):
    with page.expect_download(timeout=timeout) as dl_info:
        page.click(click_sel)
    dl_info.value.save_as(save_as)
    print(f"  ✔ DL: {os.path.basename(save_as)}")

# ─── メイン ───────────────────────────────────
def main():
    uid, pw  = os.getenv("AIRREGI_ID"), os.getenv("AIRREGI_PASS")
    folder, sj = os.getenv("DRIVE_FOLDER_ID"), os.getenv("SA_JSON")
    if not all([uid, pw, folder, sj]):
        raise SystemExit("Secrets が不足しています。")

    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(accept_downloads=True)
        page    = ctx.new_page()
        login(page, uid, pw)

        # ① 商品別売上
        page.goto(PROD_URL)
        set_calendar(page, TODAY)
        page.click("#btnSearch")                       # ←★検索
        page.wait_for_selector(".btn-CSV-DL", timeout=60000)
        download_csv(page, ".btn-CSV-DL",
                     f"{tmp}/商品別売上_{TODAY}-{TODAY}.csv")

        # ② 売上集計  ←★新: 検索→CSV を 2 回
        page.goto(KPI_URL)
        set_calendar(page, TODAY)
        page.click("#btnSearch")
        page.wait_for_selector("button.pull-right.csv-download-button",
                               timeout=60000)
        # 集計 CSV
        download_csv(page,
                     "button.pull-right.csv-download-button",
                     f"{tmp}/売上集計_{TODAY}.csv")
        # 詳細 CSV
        download_csv(page,
                     "button.salse-csv-dl",
                     f"{tmp}/売上集計詳細_{TODAY}.csv")

        # ③ Drive アップロード
        for fn in os.listdir(tmp):
            upload_to_drive(os.path.join(tmp, fn), fn, folder, sj)

        ctx.close()
        browser.close()

# ──────────────────────────────────────────────
if __name__ == "__main__":
    main()
