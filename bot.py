import asyncio
import json
import logging
import re
import os
from datetime import datetime
from telegram.ext import Application
from playwright.async_api import async_playwright

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
IVASMS_EMAIL = os.getenv("IVASMS_EMAIL")
IVASMS_PASSWORD = os.getenv("IVASMS_PASSWORD")
LOGIN_URL = os.getenv("LOGIN_URL")
SMS_URL = os.getenv("SMS_URL")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 15))

# ================= Logging =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

STATE_FILE = "sent_sms.json"

# ================= Helpers =================
def load_sent():
    try:
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_sent(data):
    with open(STATE_FILE, "w") as f:
        json.dump(list(data), f)

def extract_code(text):
    m = re.search(r"\b\d{4,8}\b", text)
    return m.group() if m else "N/A"

# ================= Fetch SMS =================
async def fetch_sms():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(LOGIN_URL)
        await page.fill('input[name="email"]', IVASMS_EMAIL)
        await page.fill('input[name="password"]', IVASMS_PASSWORD)
        await page.click('button[type="submit"]')

        try:
            await page.wait_for_selector("text=Logout", timeout=10000)
            logging.info("Login successful")
        except:
            logging.error("Login failed")
            await browser.close()
            return []

        await page.goto(SMS_URL)
        await page.wait_for_selector("div.card-body p")

        elements = await page.query_selector_all("div.card-body p")
        messages = []

        for el in elements:
            text = await el.inner_text()
            uid = hash(text)

            messages.append({
                "id": uid,
                "text": text.strip(),
                "code": extract_code(text),
                "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            })

        await browser.close()
        return messages

# ================= Telegram Job =================
async def job(app):
    sent = load_sent()
    messages = await fetch_sms()

    for msg in messages:
        if msg["id"] in sent:
            continue

        text = (
            "OTP Received\n\n"
            f"Code: `{msg['code']}`\n"
            f"Time: `{msg['time']}`\n\n"
            f"Message:\n{msg['text']}"
        )

        await app.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode="Markdown"
        )

        sent.add(msg["id"])
        save_sent(sent)

# ================= Main =================
async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set")

    app = Application.builder().token(BOT_TOKEN).build()
    logging.info("Bot started")

    while True:
        try:
            await job(app)
        except Exception as e:
            logging.error(f"Error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
