import os
from dotenv import load_dotenv

load_dotenv()

print("MAIL_USE_CREDENTIALS:", os.getenv("MAIL_USE_CREDENTIALS"))
print("MAIL_SERVER:", os.getenv("MAIL_SERVER"))
print("MAIL_PORT:", os.getenv("MAIL_PORT"))
print("MAIL_STARTTLS:", os.getenv("MAIL_STARTTLS"))
print("MAIL_SSL_TLS:", os.getenv("MAIL_SSL_TLS"))
print("MAIL_FROM:", os.getenv("MAIL_FROM"))
print("MAIL_FROM_NAME:", os.getenv("MAIL_FROM_NAME"))

service = os.getenv("MAIL_KEYRING_SERVICE")
if not service:
    # Try common defaults
    for cand in ("restailor", "restailor"):
        try:
            import keyring
            if keyring.get_password(cand, "MAIL_USERNAME") or keyring.get_password(cand, "MAIL_PASSWORD"):
                service = cand
                break
        except Exception:
            pass
    service = service or "restailor"
try:
    import keyring
except Exception as e:
    print("keyring import failed:", e)
    raise SystemExit(1)

if not service:
    print("MAIL_KEYRING_SERVICE is not set; cannot check keyring.")
else:
    u = keyring.get_password(service, "MAIL_USERNAME")
    p = keyring.get_password(service, "MAIL_PASSWORD")
    print("user_found:", bool(u))
    print("pass_found:", bool(p))
    if not u or not p:
        print("Expected keyring entries under service:", service)
        print("  username key: MAIL_USERNAME")
        print("  password key: MAIL_PASSWORD")
