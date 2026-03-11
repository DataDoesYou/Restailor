import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Use the same sender as the app
from services.emailer import send_login_code_email

TO = os.getenv("SMTP_SMOKE_TO") or os.getenv("MAIL_FROM")

async def main():
    if not TO:
        print("Set SMTP_SMOKE_TO in env to a recipient email.")
        return
    ok = await send_login_code_email(TO, "123456", 10)
    print("send_ok=", ok)

if __name__ == "__main__":
    asyncio.run(main())
