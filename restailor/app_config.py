from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import os
from dataclasses import dataclass

try:  # Python 3.11+
    import tomllib as _toml  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    try:
        import tomli as _toml  # type: ignore[no-redef]
    except Exception:
        _toml = None  # type: ignore


def _load_toml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    if _toml is None:
        # Fallback if no TOML parser available
        return {}
    # tomllib/tomli both support bytes file objects
    with path.open('rb') as f:
        return _toml.load(f)  # type: ignore[attr-defined]


def load_config() -> Dict[str, Any]:
    root = Path(__file__).resolve().parent.parent
    cfg_path = root / 'config' / 'app.toml'
    data = _load_toml(cfg_path)
    # Apply lightweight defaults if file is missing or fields absent
    app = data.setdefault('app', {})
    # App name (used in emails/UI). Allow override via env APP_NAME; default to current name.
    app.setdefault('name', os.getenv('APP_NAME', 'Restailor'))
    app.setdefault('auth_required', True)
    app.setdefault('client_id_header', 'X-Client-Id')
    app.setdefault('job_token_header', 'X-Job-Token')
    app.setdefault('sse_keepalive_ms', 15000)

    limits = data.setdefault('limits', {})
    text = limits.setdefault('text', {})
    text.setdefault('char_cap_resume', 120000)
    text.setdefault('char_cap_jd', 80000)
    text.setdefault('max_urls_per_request', 0)
    text.setdefault('max_duplicate_lines', 100)
    text.setdefault('max_repeat_run', 5000)

    tokens = limits.setdefault('tokens', {})
    tokens.setdefault('input_token_cap', 50000)
    tokens.setdefault('daily_token_budget', 1200000)

    role_out = limits.setdefault('role_outputs', {})
    role_out.setdefault('tailor', 4096)
    role_out.setdefault('fit', 4096)
    role_out.setdefault('judge', 16384)

    rate = limits.setdefault('rate', {})
    rate.setdefault('ip_rate_minute', 60)
    rate.setdefault('ip_rate_hour', 600)
    rate.setdefault('tailor_minute', 30)
    rate.setdefault('tailor_hour', 200)
    rate.setdefault('fit_minute', 60)
    rate.setdefault('fit_hour', 400)

    conc = limits.setdefault('concurrency', {})
    conc.setdefault('per_user', 2)
    conc.setdefault('global', 100)
    conc.setdefault('dedupe_ttl_sec', 600)
    conc.setdefault('similarity_cutoff', 0.98)

    timeouts = data.setdefault('timeouts', {})
    timeouts.setdefault('connect_ms', 10000)
    timeouts.setdefault('write_ms', 60000)
    timeouts.setdefault('first_byte_ms', 120000)
    timeouts.setdefault('overall_ms', 600000)
    timeouts.setdefault('stream_stall_abort_ms', 30000)

    data.setdefault('timeouts_role', {})
    data.setdefault('retry', {'max_attempts': 2, 'base_backoff_ms': 250})

    abuse = data.setdefault('abuse', {})
    abuse.setdefault('max_codeblock_lines', 120)
    abuse.setdefault('max_base64_bytes', 2048)
    abuse.setdefault('max_echo_ratio', 0.35)
    abuse.setdefault('max_quote_chars', 600)
    abuse.setdefault('ban_control_chars', True)
    abuse.setdefault('ban_injection_phrases', True)
    abuse.setdefault('require_idempotency_key', True)

    data.setdefault('abuse_role', {})
    data.setdefault('providers', {})
    # Diagnostics defaults (safe to expose to frontend)
    diagnostics = data.setdefault('diagnostics', {})
    diagnostics.setdefault('enable_diag_sse', False)
    diagnostics.setdefault('diag_token', '')
    diagnostics.setdefault('allow_ips', ['127.0.0.1'])
    # New: gate UI debug logging globally without URL/localStorage
    diagnostics.setdefault('rt_debug_ui', False)
    # Env override so platforms like Doppler can toggle without editing files
    env_rt_dbg = os.getenv('RT_DEBUG_UI')
    if env_rt_dbg is not None:
        try:
            diagnostics['rt_debug_ui'] = str(env_rt_dbg).strip().lower() in {'1','true','yes','on','y'}
        except Exception:
            pass
    # Security defaults
    security = data.setdefault('security', {})
    security.setdefault('strict_secrets', False)
    # Step-up (re-auth) TTL
    stepup = security.setdefault('stepup', {})
    try:
        stepup.setdefault('ttl_seconds', int(os.getenv('STEPUP_TTL_SECONDS') or '300'))
    except Exception:
        stepup.setdefault('ttl_seconds', 300)
    # Password policy
    password = security.setdefault('password', {})
    try:
        password.setdefault('min_length', int(os.getenv('PASSWORD_MIN_LENGTH') or '8'))
    except Exception:
        password.setdefault('min_length', 8)
    def _truthy_env(name: str, default: bool) -> bool:
        v = os.getenv(name)
        if v is None:
            return default
        return str(v).strip().lower() in {'1','true','yes','y','on'}
    password.setdefault('require_symbols', _truthy_env('PASSWORD_REQUIRE_SYMBOLS', False))
    # Remember-me settings (nested block) with sane defaults and env overrides
    rem = security.setdefault('remember', {})
    # Back-compat: also surface signer secret and days at top level under security
    env_rem_secret = os.getenv('SECURITY_REMEMBER_SIGNER_SECRET')
    if env_rem_secret is not None:
        rem['remember_signer_secret'] = env_rem_secret
    # prefer nested remember.days if provided; else env; else default 30
    try:
        rem_days_env = int(os.getenv('SECURITY_REMEMBER_DAYS') or '0')
    except Exception:
        rem_days_env = 0
    rem.setdefault('days', rem.get('days', rem_days_env if rem_days_env > 0 else 30))
    # Admin stricter defaults
    rem.setdefault('admin_days', rem.get('admin_days', 30))
    rem.setdefault('max_devices_per_user', rem.get('max_devices_per_user', 5))
    rem.setdefault('admin_max_devices', rem.get('admin_max_devices', 2))
    rem.setdefault('bind_user_agent', rem.get('bind_user_agent', True))
    rem.setdefault('bind_ip_prefix', rem.get('bind_ip_prefix', 24))
    rem.setdefault('rotate_on_password_change', rem.get('rotate_on_password_change', True))
    rem.setdefault('rotate_on_2fa_change', rem.get('rotate_on_2fa_change', True))
    # Back-compat fields at security level (legacy consumers read these)
    if 'remember_days' not in security:
        security['remember_days'] = int(rem.get('days', 30))
    if 'remember_signer_secret' not in security and rem.get('remember_signer_secret'):
        security['remember_signer_secret'] = rem.get('remember_signer_secret')
    # MFA TOTP at-rest encryption key (Fernet urlsafe base64)
    env_totp_key = os.getenv('TOTP_FERNET_KEY')
    if env_totp_key is not None:
        security['totp_fernet_key'] = env_totp_key

    # WebAuthn defaults (can be overridden via config or env)
    webauthn = security.setdefault('webauthn', {})
    webauthn.setdefault('rp_id', os.getenv('WEBAUTHN_RP_ID', 'localhost'))
    webauthn.setdefault('rp_name', os.getenv('WEBAUTHN_RP_NAME', app.get('name', 'Restailor')))
    # Accept a single origin via env; list via config file
    env_origin = os.getenv('WEBAUTHN_ORIGIN')
    if env_origin:
        webauthn['origins'] = [env_origin]
    else:
        webauthn.setdefault('origins', ['http://localhost:3000'])
    webauthn.setdefault('user_verification', os.getenv('WEBAUTHN_USER_VERIFICATION', 'preferred'))
    webauthn.setdefault('attestation', os.getenv('WEBAUTHN_ATTESTATION', 'none'))
    try:
        webauthn.setdefault('timeout_ms', int(os.getenv('WEBAUTHN_TIMEOUT_MS') or '60000'))
    except Exception:
        webauthn.setdefault('timeout_ms', 60000)
    # Challenge management knobs
    try:
        webauthn.setdefault('challenge_ttl_seconds', int(os.getenv('WEBAUTHN_CHALLENGE_TTL_SECONDS') or '180'))
    except Exception:
        webauthn.setdefault('challenge_ttl_seconds', 180)
    try:
        webauthn.setdefault('challenge_bytes', int(os.getenv('WEBAUTHN_CHALLENGE_BYTES') or '32'))
    except Exception:
        webauthn.setdefault('challenge_bytes', 32)
    # Allowed COSE algorithms (pubKeyCredParams)
    # Default: ES256 (-7) and RS256 (-257)
    env_algs = os.getenv('WEBAUTHN_ALGS')
    if env_algs is not None:
        try:
            parts = [p.strip() for p in env_algs.split(',') if p.strip()]
            vals: list[int] = []
            for p in parts:
                # Avoid try/except/continue by parsing defensively
                v: Optional[int]
                try:
                    v = int(p)
                except (TypeError, ValueError):
                    v = None
                if v is not None:
                    vals.append(v)
            if vals:
                webauthn['algs'] = vals
        except Exception as ex:
            # Ignore malformed env and stick to defaults below
            import logging as _log
            _log.getLogger(__name__).debug("app_config: WEBAUTHN_ALGS parse failed: %s", ex)
    if 'algs' not in webauthn or not isinstance(webauthn.get('algs'), (list, tuple)) or not webauthn.get('algs'):
        webauthn['algs'] = [-7, -257]

    # Email SMTP settings surfaced for convenience; prefer env when set.
    email = data.setdefault('email', {})
    def _truthy(v: str | None) -> bool:
        return str(v or '').strip().lower() in {'1','true','yes','y','on'}
    if os.getenv('MAIL_SERVER') is not None:
        email['server'] = os.getenv('MAIL_SERVER')
    if os.getenv('MAIL_PORT') is not None:
        try:
            email['port'] = int(str(os.getenv('MAIL_PORT')))
        except Exception as ex:
            import logging as _log
            _log.getLogger(__name__).debug("app_config: MAIL_PORT parse failed: %s", ex)
    if os.getenv('MAIL_FROM') is not None:
        email['from'] = os.getenv('MAIL_FROM')
    if os.getenv('MAIL_FROM_NAME') is not None:
        email['from_name'] = os.getenv('MAIL_FROM_NAME')
    if os.getenv('MAIL_STARTTLS') is not None:
        email['starttls'] = _truthy(os.getenv('MAIL_STARTTLS'))
    if os.getenv('MAIL_SSL_TLS') is not None:
        email['ssl_tls'] = _truthy(os.getenv('MAIL_SSL_TLS'))
    if os.getenv('MAIL_USERNAME') is not None:
        email['username'] = os.getenv('MAIL_USERNAME')
    if os.getenv('MAIL_PASSWORD') is not None:
        email['password'] = os.getenv('MAIL_PASSWORD')
    if os.getenv('MAIL_USE_CREDENTIALS') is not None:
        email['use_credentials'] = _truthy(os.getenv('MAIL_USE_CREDENTIALS'))
    # Diagnostics defaults
    diagnostics = data.setdefault('diagnostics', {})
    diagnostics.setdefault('enable_diag_sse', False)
    diagnostics.setdefault('diag_token', '')
    diagnostics.setdefault('allow_ips', ['127.0.0.1'])

    app = data.setdefault('app', {})
    if os.getenv('DEMO_USER_EMAIL') is not None:
        app['demo_user_email'] = os.getenv('DEMO_USER_EMAIL')

    # Perf/observability knobs
    perf = data.setdefault('perf', {})
    try:
        perf.setdefault('sql_slow_ms', float(os.getenv('PERF_SQL_SLOW_MS') or '50.0'))
    except Exception:
        perf.setdefault('sql_slow_ms', 50.0)
    # Optional httpx shared client tuning (used only if get_shared_async_client() is adopted by callers)
    def _int_env_default(name: str, default_val: int) -> int:
        try:
            v = os.getenv(name)
            return int(v) if v is not None and str(v).strip() != '' else default_val
        except Exception:
            return default_val
    def _float_env_default(name: str, default_val: float) -> float:
        try:
            v = os.getenv(name)
            return float(v) if v is not None and str(v).strip() != '' else default_val
        except Exception:
            return default_val
    perf.setdefault('httpx_max_connections', _int_env_default('PERF_HTTPX_MAX_CONNECTIONS', 100))
    perf.setdefault('httpx_max_keepalive', _int_env_default('PERF_HTTPX_MAX_KEEPALIVE', 20))
    # Milliseconds to align with perf.sql_slow_ms units; convert to seconds in helper
    perf.setdefault('httpx_timeout_ms', _float_env_default('PERF_HTTPX_TIMEOUT_MS', 10000.0))
    perf.setdefault('httpx_connect_timeout_ms', _float_env_default('PERF_HTTPX_CONNECT_TIMEOUT_MS', 5000.0))

    # Redis connection (for ARQ/queues and optional captcha state)
    redis = data.setdefault('redis', {})
    # Support unified REDIS_URL first (e.g., redis://:pass@host:6379/0)
    _ru = os.getenv('REDIS_URL') or os.getenv('RATE_LIMIT_STORAGE_URI')
    if _ru:
        try:
            from urllib.parse import urlparse
            u = urlparse(_ru)
            if u.hostname:
                redis['host'] = u.hostname
            if u.port:
                try:
                    redis['port'] = int(u.port)
                except Exception:
                    redis['port'] = 6379
            # path like "/0" for DB number
            try:
                redis['database'] = int((u.path or '/0').lstrip('/') or '0')
            except Exception:
                redis['database'] = 0
            if u.password:
                redis['password'] = u.password
        except Exception:
            pass
    if os.getenv('REDIS_HOST') is not None:
        redis['host'] = os.getenv('REDIS_HOST')
    if os.getenv('REDIS_PORT') is not None:
        try:
            redis['port'] = int(str(os.getenv('REDIS_PORT')))
        except Exception:
            redis['port'] = 6379
    if os.getenv('REDIS_DB') is not None:
        try:
            redis['database'] = int(str(os.getenv('REDIS_DB')))
        except Exception:
            redis['database'] = 0
    if os.getenv('REDIS_PASSWORD') is not None:
        redis['password'] = os.getenv('REDIS_PASSWORD')
    # Defaults if not provided by env or file
    redis.setdefault('host', '127.0.0.1')
    redis.setdefault('port', 6379)
    redis.setdefault('database', 0)
    # password is optional; omit if empty

    # Auth flows: verification and password reset throttles and expirations
    auth = data.setdefault('auth', {})
    # Token expirations
    tokens = auth.setdefault('tokens', {})
    try:
        tokens.setdefault('access_token_expire_minutes', int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES') or '60'))
    except Exception:
        tokens.setdefault('access_token_expire_minutes', 60)
    try:
        tokens.setdefault('reauth_token_expire_minutes', int(os.getenv('REAUTH_TOKEN_EXPIRE_MINUTES') or '5'))
    except Exception:
        tokens.setdefault('reauth_token_expire_minutes', 5)
    try:
        tokens.setdefault('pending2_token_expire_minutes', int(os.getenv('PENDING2_TOKEN_EXPIRE_MINUTES') or '15'))
    except Exception:
        tokens.setdefault('pending2_token_expire_minutes', 15)
    try:
        tokens.setdefault('refresh_token_expire_days', int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS') or '30'))
    except Exception:
        tokens.setdefault('refresh_token_expire_days', 30)
    verify = auth.setdefault('verify', {})
    verify.setdefault('cooldown_seconds', 300)
    verify.setdefault('limit_window_seconds', 600)
    verify.setdefault('max_per_window', 5)
    verify.setdefault('token_expire_minutes', 60)
    reset = auth.setdefault('reset', {})
    reset.setdefault('ip_rate', '5/hour')
    reset.setdefault('per_user_cooldown_seconds', 300)
    reset.setdefault('token_expire_minutes', 30)
    login = auth.setdefault('login', {})
    login.setdefault('ip_rate', '10/minute;100/hour')
    login.setdefault('fail_window_seconds', 900)
    login.setdefault('backoff_base_seconds', 2)
    login.setdefault('backoff_max_seconds', 900)
    login.setdefault('lockout_after', 0)  # 0 disables hard lockout threshold
    login.setdefault('lockout_seconds', 900)
    captcha = login.setdefault('captcha', {})
    captcha.setdefault('provider', '')            # 'recaptcha' | 'turnstile' | ''
    captcha.setdefault('required', False)
    captcha.setdefault('site_key', '')
    # Client-side helpers (safe): allow a short cache for captcha "ready" checks
    captcha.setdefault('ready_ttl_seconds', 90)

    # Optional list of allowed CORS origins (fallback to dev defaults in main if not provided)
    app.setdefault('allowed_origins', app.get('allowed_origins', []))

    # Stripe payment settings (prefer env vars for secrets)
    stripe = data.setdefault('stripe', {})
    # Enable/disable Stripe integration
    stripe_enabled_env = os.getenv('STRIPE_ENABLED')
    if stripe_enabled_env is not None:
        stripe['enabled'] = _truthy(stripe_enabled_env)
    else:
        stripe.setdefault('enabled', False)
    # Webhook secret (required for verifying webhook signatures)
    stripe_webhook_secret_env = os.getenv('STRIPE_WEBHOOK_SECRET')
    if stripe_webhook_secret_env is not None:
        stripe['webhook_secret'] = stripe_webhook_secret_env
    else:
        stripe.setdefault('webhook_secret', '')
    # Publishable and secret keys (for API initialization)
    stripe_publishable_key_env = os.getenv('STRIPE_PUBLISHABLE_KEY')
    if stripe_publishable_key_env is not None:
        stripe['publishable_key'] = stripe_publishable_key_env
    stripe_secret_key_env = os.getenv('STRIPE_SECRET_KEY')
    if stripe_secret_key_env is not None:
        stripe['secret_key'] = stripe_secret_key_env

    # UI defaults
    ui = data.setdefault('ui', {})
    # Cache credits display to avoid per-render /users/me calls
    ui.setdefault('credits_ttl_seconds', 120)
    # Max recursion/scan depth when walking nested SDK objects to extract final text on demo pages
    try:
        ui.setdefault('deep_text_scan_limit', int(os.getenv('UI_DEEP_TEXT_SCAN_LIMIT') or '10000'))
    except Exception:
        ui.setdefault('deep_text_scan_limit', 10000)
    # Standardized UI->API HTTP timeouts (seconds)
    def _int_env(name: str, default_val: int) -> int:
        try:
            v = os.getenv(name)
            return int(v) if v is not None and str(v).strip() != '' else default_val
        except Exception:
            return default_val
    ui.setdefault('api_timeout_short_s', _int_env('UI_API_TIMEOUT_SHORT_S', 6))
    ui.setdefault('api_timeout_medium_s', _int_env('UI_API_TIMEOUT_MEDIUM_S', 8))
    ui.setdefault('api_timeout_default_s', _int_env('UI_API_TIMEOUT_DEFAULT_S', 10))
    ui.setdefault('api_timeout_medlong_s', _int_env('UI_API_TIMEOUT_MEDLONG_S', 12))
    ui.setdefault('api_timeout_long_s', _int_env('UI_API_TIMEOUT_LONG_S', 20))
    ui.setdefault('api_timeout_xlong_s', _int_env('UI_API_TIMEOUT_XLONG_S', 30))
    ui.setdefault('api_timeout_bulk_s', _int_env('UI_API_TIMEOUT_BULK_S', 120))

    # --- Multi-factor authentication (MFA) and step-up rate/limits ---
    security = data.setdefault('security', {})
    mfa = security.setdefault('mfa', {})
    # Per-operation soft limits for memory/Redis fallback gates
    mfa_limits = mfa.setdefault('limits', {})
    # Confirm TOTP: default 5 in 10 minutes
    try:
        mfa_limits.setdefault('totp_confirm_limit', int(os.getenv('MFA_TOTP_CONFIRM_LIMIT') or '5'))
    except Exception:
        mfa_limits.setdefault('totp_confirm_limit', 5)
    try:
        mfa_limits.setdefault('totp_confirm_window_seconds', int(os.getenv('MFA_TOTP_CONFIRM_WINDOW_SECONDS') or '600'))
    except Exception:
        mfa_limits.setdefault('totp_confirm_window_seconds', 600)
    # Regen recovery codes: default 3/hour
    try:
        mfa_limits.setdefault('recovery_regen_limit', int(os.getenv('MFA_RECOVERY_REGEN_LIMIT') or '3'))
    except Exception:
        mfa_limits.setdefault('recovery_regen_limit', 3)
    try:
        mfa_limits.setdefault('recovery_regen_window_seconds', int(os.getenv('MFA_RECOVERY_REGEN_WINDOW_SECONDS') or '3600'))
    except Exception:
        mfa_limits.setdefault('recovery_regen_window_seconds', 3600)

    # Email OTP limiter rate strings (used by SlowAPI decorators)
    eotp = mfa.setdefault('email_otp', {})
    eotp.setdefault('request_rate', os.getenv('EMAIL_OTP_REQUEST_RATE', '1/minute;5/hour'))
    eotp.setdefault('request_ip_rate', os.getenv('EMAIL_OTP_REQUEST_IP_RATE', '30/hour'))
    eotp.setdefault('verify_rate', os.getenv('EMAIL_OTP_VERIFY_RATE', '10/minute;100/hour'))
    eotp.setdefault('verify_ip_rate', os.getenv('EMAIL_OTP_VERIFY_IP_RATE', '30/minute;300/hour'))

    # Step-up WebAuthn limiter rate string
    stepup_cfg = security.setdefault('stepup', security.get('stepup', {}))
    stepup_cfg.setdefault('rate', os.getenv('STEPUP_WEBAUTHN_RATE', '20/minute;200/hour'))
    return data


CONFIG: Dict[str, Any] = load_config()


# --- Typed settings: Abuse IP/ASN policy ---
ActionLadder = str  # one of: "allow_trial" | "allow_only_with_2fa" | "require_payment" | "hard_block"


@dataclass(frozen=True)
class AbuseIpAsnSettings:
    # headers
    asn_header: str = "X-ASN"
    org_header: str = "X-ASN-Org"
    # per-24h caps
    cap_residential_per_ip: int = 5
    cap_university_per_ip: int = 20
    cap_unknown_per_ip: int = 3
    cap_datacenter_per_ip: int = 1
    # action ladder
    over_cap_residential: ActionLadder = "allow_only_with_2fa"
    over_cap_university: ActionLadder = "allow_only_with_2fa"
    over_cap_unknown: ActionLadder = "require_payment"
    over_cap_datacenter: ActionLadder = "require_payment"
    # classification helpers
    university_org_keywords: List[str] = None  # type: ignore[assignment]
    datacenter_org_keywords: List[str] = None  # type: ignore[assignment]
    university_asns: List[str] = None  # type: ignore[assignment]
    datacenter_asns: List[str] = None  # type: ignore[assignment]
    # window
    window_seconds: int = 86400

    @staticmethod
    def from_config(cfg: Dict[str, Any]) -> "AbuseIpAsnSettings":
        abuse = (cfg.get('abuse', {}) or {})
        raw = (abuse.get('ip_asn', {}) or {})
        # lists: ensure type and defaults
        uni_kw = raw.get('university_org_keywords')
        if not isinstance(uni_kw, (list, tuple)):
            uni_kw = ["University", "College", "Institute of Technology", ".edu"]
        uni_kw = [str(x) for x in uni_kw]

        dc_kw = raw.get('datacenter_org_keywords')
        if not isinstance(dc_kw, (list, tuple)):
            dc_kw = [
                "Amazon", "AWS", "Google Cloud", "GCP", "Microsoft Azure",
                "DigitalOcean", "Hetzner", "OVH", "Scaleway", "Vultr", "Linode",
            ]
        dc_kw = [str(x) for x in dc_kw]

        uni_asns = raw.get('university_asns')
        if not isinstance(uni_asns, (list, tuple)):
            uni_asns = []
        uni_asns = [str(x) for x in uni_asns]

        dc_asns = raw.get('datacenter_asns')
        if not isinstance(dc_asns, (list, tuple)):
            dc_asns = []
        dc_asns = [str(x) for x in dc_asns]

        def _int(v: Any, d: int) -> int:
            try:
                return int(v)
            except Exception:
                return d

        def _str(v: Any, d: str) -> str:
            return str(v) if v is not None else d

        return AbuseIpAsnSettings(
            asn_header=_str(raw.get('asn_header'), 'X-ASN'),
            org_header=_str(raw.get('org_header'), 'X-ASN-Org'),
            cap_residential_per_ip=_int(raw.get('cap_residential_per_ip'), 5),
            cap_university_per_ip=_int(raw.get('cap_university_per_ip'), 20),
            cap_unknown_per_ip=_int(raw.get('cap_unknown_per_ip'), 3),
            cap_datacenter_per_ip=_int(raw.get('cap_datacenter_per_ip'), 1),
            over_cap_residential=_str(raw.get('over_cap_residential'), 'allow_only_with_2fa'),
            over_cap_university=_str(raw.get('over_cap_university'), 'allow_only_with_2fa'),
            over_cap_unknown=_str(raw.get('over_cap_unknown'), 'require_payment'),
            over_cap_datacenter=_str(raw.get('over_cap_datacenter'), 'require_payment'),
            university_org_keywords=uni_kw,
            datacenter_org_keywords=dc_kw,
            university_asns=uni_asns,
            datacenter_asns=dc_asns,
            window_seconds=_int(raw.get('window_seconds'), 86400),
        )


def get_abuse_ip_asn_settings() -> AbuseIpAsnSettings:
    """Public accessor for typed IP/ASN abuse settings.

    Safe defaults are returned when the section is missing.
    """
    return AbuseIpAsnSettings.from_config(CONFIG)
