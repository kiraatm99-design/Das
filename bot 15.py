"""
Football Prediction Bot — DASI BET
- No subscription required to use
- Welcome image + channel link on first use
- Short analysis + reason button
- Smart coupon with target odd
"""
import logging, os, json, hashlib, threading, requests
from datetime import datetime, timedelta, time as dtime
from flask import Flask
from threading import Thread
from groq import Groq
from tavily import TavilyClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                           CallbackQueryHandler, filters, ContextTypes)

# ═══════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "")
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY", "5d44806d63094fdab0090cc5faef770c")
TAVILY_API_KEY   = os.environ.get("TAVILY_API_KEY", "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")
CHANNEL          = "@dasi_bet"
CHANNEL_URL      = "https://t.me/dasi_bet"
ADMIN_ID         = 7046072164
ADMIN_USERNAME   = "@dasi_supportt"
FREE_LIMIT       = 3
REFERRAL_GOAL    = 5
VIP_DAYS         = 30
POINTS_PER_VIP   = 100
CACHE_TTL_HOURS  = 6
SEASON           = "2025"
PORT             = 8080
BOT_USERNAME     = os.environ.get("BOT_USERNAME", "football_analysist2_bot")
DB_FILE          = "data/users.json"
CACHE_FILE       = "data/cache.json"
WELCOME_ID_FILE  = "data/welcome_file_id.txt"

LEAGUES = {
    "PL":  {"name": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 الإنجليزي",  "id": 2021},
    "PD":  {"name": "🇪🇸 الإسباني",    "id": 2014},
    "BL1": {"name": "🇩🇪 الألماني",    "id": 2002},
    "SA":  {"name": "🇮🇹 الإيطالي",    "id": 2019},
    "FL1": {"name": "🇫🇷 الفرنسي",     "id": 2015},
    "CL":  {"name": "🌍 أبطال أوروبا","id": 2001},
}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger        = logging.getLogger(__name__)
groq_client   = Groq(api_key=GROQ_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
_db_lock      = threading.Lock()
_cache_lock   = threading.Lock()

# ═══════════════════════════════════════════════
#  PROMPTS
# ═══════════════════════════════════════════════
ANALYSIS_PROMPT = """أنت محلل كرة قدم خبير. حلل مباريات موسم 2025/2026 فقط.
رد بنفس لغة المستخدم (عربي أو إنجليزي).

اجعل التحليل مختصراً جداً بهذا الشكل الثابت:

━━━━━━━━━━━━━━━━━━
⚽ [ف1] vs [ف2]
━━━━━━━━━━━━━━━━━━
🏆 التوقع: [الفائز] | الأود: [X.XX]
📊 النتيجة المحتملة: [X-X]
🔄 فرصة مزدوجة ([الفائز] أو تعادل) | الأود: [X.XX]
⚽ أهداف: أوفر [X].5 | الأود: [X.XX]
👥 كلا الفريقين يسجلان: [نعم/لا] | الأود: [X.XX]
🔄 ركنيات [الفريق الأكثر]: أوفر [X].5 | الأود: [X.XX]
🟨 بطاقات: أوفر [X].5 | الأود: [X.XX]
💡 أفضل رهان: [الرهان] | الأود: [X.XX] | الثقة: [X]%
━━━━━━━━━━━━━━━━━━
⚠️ للترفيه فقط

لا تضيف أي شرح خارج هذا الشكل."""

REASON_PROMPT = """أنت محلل كرة قدم خبير. قدم تحليلاً مفصلاً لهذه المباراة في موسم 2025/2026.

اكتب بنفس لغة المستخدم (عربي أو إنجليزي). الشكل:

🔍 *سبب التوقع — [ف1] vs [ف2]*
━━━━━━━━━━━━━━━━━━

📋 *آخر 5 مباريات:*
• [ف1]: [النتائج] | الشكل: [ممتاز/جيد/متذبذب]
• [ف2]: [النتائج] | الشكل: [ممتاز/جيد/متذبذب]

🎮 *أسلوب اللعب:*
• [ف1]: [النظام التكتيكي وطريقة اللعب]
• [ف2]: [النظام التكتيكي وطريقة اللعب]

🏥 *الغيابات والإصابات:*
• [ف1]: [اللاعبون الغائبون]
• [ف2]: [اللاعبون الغائبون]

⚡ *أسباب التوقع:*
• [سبب 1 — مثال: يحتاج نقاط لتجنب الهبوط]
• [سبب 2]
• [سبب 3]

📍 *عوامل إضافية:*
• الملعب: [هجوم/دفاع وتأثيره]
• الضغط النفسي: [من المضغوط أكثر ولماذا]
━━━━━━━━━━━━━━━━━━
⚠️ للترفيه فقط"""

SAFE_BET_PROMPT = """أنت محلل كرة قدم. من المباريات التالية اختر الأكثر أماناً لموسم 2025/2026.

🔒 أضمن رهان اليوم
━━━━━━━━━━━━━━━━━━
⚽ [ف1] vs [ف2]
✅ [التوقع] | الأود: [X.XX] | الثقة: [X]%
💡 [سبب واحد قصير]
━━━━━━━━━━━━━━━━━━
⚠️ للترفيه فقط"""

COUPON_PROMPT = """أنت محلل كرة قدم محترف. بناء قسيمة رهان مركبة.

الأود الإجمالي المطلوب: {target_odd}

القواعد الإلزامية:
1. اختر مباريات مختلفة تماماً — لا تكرر أي مباراة
2. لكل مباراة رهان واحد فقط
3. حاصل ضرب الأودد = {target_odd} تقريباً
4. مثال للأود 5.0: اختر 4 رهانات: 1.40 × 1.50 × 1.55 × 1.55 = 5.04

القسيمة بهذا الشكل فقط:

🎫 القسيمة الذهبية
🎯 الأود المطلوب: {target_odd}
━━━━━━━━━━━━━━━━━━
1. [ف1 vs ف2] | ✅ [الرهان] | 💰 [X.XX]
2. [ف1 vs ف2] | ✅ [الرهان] | 💰 [X.XX]
3. [ف1 vs ف2] | ✅ [الرهان] | 💰 [X.XX]
4. [ف1 vs ف2] | ✅ [الرهان] | 💰 [X.XX]
━━━━━━━━━━━━━━━━━━
💰 الأود الفعلي: [اضرب الأودد]
📊 نسبة النجاح: [X]%
⚠️ للترفيه فقط"""

# ═══════════════════════════════════════════════
#  CACHE
# ═══════════════════════════════════════════════
def _ensure_dirs():
    os.makedirs("data", exist_ok=True)

def _load_cache() -> dict:
    _ensure_dirs()
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r") as f:
        return json.load(f)

def _save_cache(c: dict):
    _ensure_dirs()
    with _cache_lock:
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(c, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CACHE_FILE)

def cache_key(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode()).hexdigest()[:12]

def cache_get(key: str):
    c = _load_cache()
    if key not in c:
        return None
    t = datetime.strptime(c[key]["time"], "%Y-%m-%d %H:%M")
    if datetime.now() - t > timedelta(hours=CACHE_TTL_HOURS):
        return None
    return c[key]["data"]

def cache_set(key: str, data):
    c = _load_cache()
    c[key] = {"data": data, "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
    if len(c) > 500:
        for k, _ in sorted(c.items(), key=lambda x: x[1]["time"])[:100]:
            del c[k]
    _save_cache(c)

def cache_clear():
    _save_cache({})

# ═══════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════
def db_load() -> dict:
    _ensure_dirs()
    if not os.path.exists(DB_FILE):
        return {"users": {}, "total_requests": 0}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def db_save(db: dict):
    _ensure_dirs()
    with _db_lock:
        tmp = DB_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DB_FILE)

def db_user(db: dict, uid: int, update=None) -> dict:
    k = str(uid)
    if k not in db["users"]:
        db["users"][k] = {
            "name": getattr(getattr(update, "effective_user", None), "full_name", ""),
            "username": getattr(getattr(update, "effective_user", None), "username", ""),
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "requests_today": 0, "bonus_requests": 0,
            "last_request_date": "", "total_requests": 0,
            "vip": False, "vip_expiry": "", "blocked": False,
            "points": 0, "referrals": [], "referred_by": "",
            "history": [], "ratings": [], "first_visit": True,
        }
        db_save(db)
    return db["users"][k]

def is_vip(db: dict, uid: int) -> bool:
    if uid == ADMIN_ID:
        return True
    u = db_user(db, uid)
    if not u["vip"]:
        return False
    if u["vip_expiry"] and datetime.now().strftime("%Y-%m-%d") > u["vip_expiry"]:
        u["vip"] = False
        db_save(db)
        return False
    return True

def get_limit(db: dict, uid: int) -> int:
    return 9999 if is_vip(db, uid) else FREE_LIMIT + db_user(db, uid).get("bonus_requests", 0)

def has_quota(db: dict, uid: int) -> bool:
    if is_vip(db, uid):
        return True
    u = db_user(db, uid)
    today = datetime.now().strftime("%Y-%m-%d")
    if u["last_request_date"] != today:
        u["requests_today"] = 0
        u["last_request_date"] = today
        db_save(db)
    return u["requests_today"] < get_limit(db, uid)

def remaining(db: dict, uid: int):
    if is_vip(db, uid):
        return "♾️"
    u = db_user(db, uid)
    today = datetime.now().strftime("%Y-%m-%d")
    used = u["requests_today"] if u["last_request_date"] == today else 0
    return max(0, get_limit(db, uid) - used)

def consume(db: dict, uid: int, match: str):
    u = db_user(db, uid)
    today = datetime.now().strftime("%Y-%m-%d")
    if u["last_request_date"] != today:
        u["requests_today"] = 0
        u["last_request_date"] = today
    u["requests_today"] += 1
    u["total_requests"] += 1
    db["total_requests"] = db.get("total_requests", 0) + 1
    u["history"].append({"match": match, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
    u["history"] = u["history"][-20:]
    _add_points(db, uid, 5)

def _add_points(db: dict, uid: int, pts: int) -> bool:
    u = db_user(db, uid)
    u["points"] = u.get("points", 0) + pts
    if u["points"] >= POINTS_PER_VIP:
        u["points"] -= POINTS_PER_VIP
        u["vip"] = True
        u["vip_expiry"] = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        db_save(db)
        return True
    db_save(db)
    return False

def activate_vip(db: dict, uid: int) -> str:
    u = db_user(db, uid)
    u["vip"] = True
    expiry = (datetime.now() + timedelta(days=VIP_DAYS)).strftime("%Y-%m-%d")
    u["vip_expiry"] = expiry
    db_save(db)
    return expiry

def handle_referral(db: dict, new_uid: int, ref_id: str):
    if str(new_uid) == ref_id or ref_id not in db.get("users", {}):
        return
    ref = db_user(db, int(ref_id))
    if str(new_uid) in ref.get("referrals", []):
        return
    ref.setdefault("referrals", []).append(str(new_uid))
    db_user(db, new_uid)["referred_by"] = ref_id
    if len(ref["referrals"]) % REFERRAL_GOAL == 0:
        ref["bonus_requests"] = ref.get("bonus_requests", 0) + 1
    _add_points(db, int(ref_id), 10)
    db_save(db)

# ═══════════════════════════════════════════════
#  FOOTBALL API
# ═══════════════════════════════════════════════
_FAPI_BASE    = "https://api.football-data.org/v4"
_FAPI_HEADERS = {"X-Auth-Token": FOOTBALL_API_KEY}

def _fapi(endpoint: str, params: dict = None):
    try:
        r = requests.get(f"{_FAPI_BASE}/{endpoint}", headers=_FAPI_HEADERS,
                         params=params, timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logger.error(f"Football API: {e}")
        return None

def get_matches(league_code: str, date: str) -> list:
    key = f"matches_{league_code}_{date}"
    cached = cache_get(key)
    if cached:
        return json.loads(cached)
    lid  = LEAGUES[league_code]["id"]
    data = _fapi(f"competitions/{lid}/matches",
                 {"dateFrom": date, "dateTo": date, "season": SEASON})
    if not data:
        return []
    result = [{"home": m["homeTeam"]["name"], "away": m["awayTeam"]["name"],
               "time": m["utcDate"][11:16], "league": LEAGUES[league_code]["name"]}
              for m in data.get("matches", [])]
    cache_set(key, json.dumps(result))
    return result

def get_all_matches(date: str) -> list:
    key = f"all_{date}"
    cached = cache_get(key)
    if cached:
        return json.loads(cached)
    all_m = []
    for code in LEAGUES:
        all_m.extend(get_matches(code, date))
    cache_set(key, json.dumps(all_m))
    return all_m

# ═══════════════════════════════════════════════
#  AI SERVICE
# ═══════════════════════════════════════════════
def _groq(system: str, user: str, tokens: int = 500) -> str:
    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile", max_tokens=tokens,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}]
    )
    return r.choices[0].message.content

def _news(t1: str, t2: str) -> str:
    key = f"news_{cache_key(t1+t2)}"
    cached = cache_get(key)
    if cached:
        return cached
    try:
        res = tavily_client.search(
            query=f"{t1} vs {t2} 2025 injuries form news",
            max_results=3, search_depth="basic"
        )
        text = " | ".join(r.get("content", "")[:200] for r in res.get("results", []))
        cache_set(key, text)
        return text
    except Exception as e:
        logger.warning(f"Tavily: {e}")
        return ""

def ai_analyze(match: str) -> str:
    key = cache_key(f"analysis_{match}")
    cached = cache_get(key)
    if cached:
        return cached + "\n⚡ _من الكاش_"
    result = _groq(ANALYSIS_PROMPT, f"حلل: {match}", tokens=400)
    cache_set(key, result)
    return result

def ai_reason(match: str) -> str:
    key = cache_key(f"reason_{match}")
    cached = cache_get(key)
    if cached:
        return cached
    parts = match.lower().replace(" vs ", " ").replace(" ضد ", " ").split()
    t1, t2 = (parts[0], parts[-1]) if len(parts) > 1 else (match, "")
    news   = _news(t1, t2)
    content = f"المباراة: {match}" + (f"\nأخبار: {news}" if news else "")
    result = _groq(REASON_PROMPT, content, tokens=700)
    cache_set(key, result)
    return result

def ai_safe_bet(matches: list) -> str:
    key = f"safe_{datetime.now().strftime('%Y-%m-%d')}"
    cached = cache_get(key)
    if cached:
        return cached
    lines  = "\n".join(f"{m['home']} vs {m['away']} ({m.get('league','')})"
                       for m in matches[:15])
    result = _groq(SAFE_BET_PROMPT, f"مباريات اليوم:\n{lines}", tokens=200)
    cache_set(key, result)
    return result

def ai_coupon(target_odd: str, matches: list) -> str:
    key = f"coupon_{cache_key(target_odd)}_{datetime.now().strftime('%Y-%m-%d')}"
    cached = cache_get(key)
    if cached:
        return cached
    lines = "\n".join(
        f"{i+1}. {m['home']} vs {m['away']} ({m.get('league', '')})"
        for i, m in enumerate(matches[:20])
    )
    prompt = COUPON_PROMPT.format(target_odd=target_odd)
    user_msg = (
        f"الأود المطلوب: {target_odd}\n\n"
        f"المباريات المتاحة اليوم (اختر مباريات مختلفة):\n{lines}\n\n"
        f"تذكر: حاصل ضرب الأودد يجب أن يساوي {target_odd} تقريباً"
    )
    result = _groq(prompt, user_msg, tokens=600)
    cache_set(key, result)
    return result

# ═══════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════
def kb_main(vip: bool):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 مباريات اليوم",  callback_data="leagues_today"),
         InlineKeyboardButton("📆 مباريات الغد",   callback_data="leagues_tomorrow")],
        [InlineKeyboardButton("🔒 أضمن رهان",      callback_data="safe_bet"),
         InlineKeyboardButton("⚽ توقع مباراة",    callback_data="predict")],
        [InlineKeyboardButton("🎫 قسيمة ذهبية",   callback_data="coupon"),
         InlineKeyboardButton("👥 أحل صديقاً",     callback_data="referral")],
        [InlineKeyboardButton("📊 إحصائياتي",      callback_data="my_stats"),
         InlineKeyboardButton("💎 VIP نشط ✅" if vip else "💎 VIP $5/شهر",
                              callback_data="my_stats" if vip else "vip_info")]
    ])

def kb_leagues(day: str):
    rows = []
    items = list(LEAGUES.items())
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(items[i][1]["name"],
                                    callback_data=f"league_{items[i][0]}_{day}")]
        if i + 1 < len(items):
            row.append(InlineKeyboardButton(items[i+1][1]["name"],
                                            callback_data=f"league_{items[i+1][0]}_{day}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)

def kb_matches(match_list: list, league_code: str, day: str):
    rows = []
    for i, m in enumerate(match_list[:10]):
        rows.append([InlineKeyboardButton(
            f"⚽ {m['home']} vs {m['away']}  🕐{m['time']}",
            callback_data=f"match_{league_code}_{day}_{i}"
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"leagues_{day}")])
    return InlineKeyboardMarkup(rows)

def kb_after_analysis(match: str):
    """أزرار تظهر بعد التوقع"""
    match_encoded = match[:30]  # نختصر اسم المباراة
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 سبب التوقع", callback_data=f"reason_{match_encoded}")],
        [InlineKeyboardButton("✍️ تقييم التوقع", callback_data="write_review")]
    ])

def kb_vip():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 اشترك $5/شهر", callback_data="pay_vip")],
        [InlineKeyboardButton("🔙 رجوع",          callback_data="back_main")]
    ])

def kb_back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])

# ═══════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════
def ref_link(uid: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"

async def safe_send(msg, text: str, **kw):
    try:
        await msg.reply_text(text, parse_mode="Markdown", **kw)
    except Exception:
        await msg.reply_text(text, **kw)

async def safe_edit(query, text: str, **kw):
    try:
        await query.edit_message_text(text, parse_mode="Markdown", **kw)
    except Exception:
        try:
            await query.edit_message_text(text, **kw)
        except Exception:
            pass

def day_date(day: str) -> str:
    return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d") \
           if day == "tomorrow" else datetime.now().strftime("%Y-%m-%d")

def day_label(day: str) -> str:
    return "الغد 📆" if day == "tomorrow" else "اليوم 📅"

async def _send_welcome_photo(msg):
    """إرسال صورة الترحيب مع رابط القناة"""
    caption = (
        f"👑 *أهلاً بك في DASI BET!*\n\n"
        f"🏆 بوت التوقعات الرياضية الاحترافي\n"
        f"تحليلات دقيقة • توقعات احترافية • أرباح أكبر 🚀\n\n"
        f"📢 *اشترك في قناتنا للحصول على أفضل التوقعات يومياً:*\n"
        f"{CHANNEL_URL}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 اشترك في القناة", url=CHANNEL_URL)]
    ])
    try:
        if os.path.exists(WELCOME_ID_FILE):
            with open(WELCOME_ID_FILE, "r") as f:
                fid = f.read().strip()
            if fid:
                await msg.reply_photo(photo=fid, caption=caption,
                                      parse_mode="Markdown", reply_markup=kb)
                return
        if os.path.exists("welcome.png"):
            with open("welcome.png", "rb") as img:
                sent = await msg.reply_photo(photo=img, caption=caption,
                                             parse_mode="Markdown", reply_markup=kb)
            fid = sent.photo[-1].file_id
            _ensure_dirs()
            with open(WELCOME_ID_FILE, "w") as f:
                f.write(fid)
        else:
            await safe_send(msg, caption, reply_markup=kb)
    except Exception as e:
        logger.warning(f"Welcome photo error: {e}")
        await safe_send(msg, caption, reply_markup=kb)

async def _send_home_menu(msg, uid: int, db: dict):
    u      = db_user(db, uid)
    badge  = "💎 VIP" if is_vip(db, uid) else "🆓 مجاني"
    rem    = remaining(db, uid)
    points = u.get("points", 0)
    name   = ""
    try:
        name = msg.chat.first_name
    except Exception:
        pass
    await safe_send(msg,
        f"👑 *DASI BET — {name}*\n\n"
        f"🏷️ {badge} | 🎯 متبقي: *{rem}* | ⭐ {points}/100\n\n"
        f"اختر من القائمة 👇",
        reply_markup=kb_main(is_vip(db, uid))
    )

# ═══════════════════════════════════════════════
#  HANDLERS — USER
# ═══════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db  = db_load()
    uid = update.effective_user.id
    u   = db_user(db, uid, update)

    # معالجة رابط الإحالة
    if context.args and context.args[0].startswith("ref_"):
        handle_referral(db, uid, context.args[0][4:])

    # أرسل صورة الترحيب في أول زيارة فقط
    if u.get("first_visit", True):
        u["first_visit"] = False
        db_save(db)
        await _send_welcome_photo(update.message)

    # أرسل القائمة الرئيسية — البوت يعمل للجميع بدون شرط اشتراك
    await _send_home_menu(update.message, uid, db)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db   = db_load()
    uid  = update.effective_user.id
    text = update.message.text.strip()

    u = db_user(db, uid, update)
    if u.get("blocked"):
        return

    mode = context.user_data.pop("mode", "predict")

    # وضع التقييم
    if mode == "review":
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"⭐ *تقييم جديد*\n\n"
                f"👤 {u.get('name','?')} | ID: `{uid}`\n\n"
                f"💬 {text}",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        await safe_send(update.message, "✅ شكراً! تم إرسال تقييمك للإدارة 🙏")
        return

    # وضع القسيمة
    if mode == "coupon":
        try:
            float(text.replace(",", "."))
        except ValueError:
            await safe_send(update.message,
                            "❌ أرسل رقماً فقط مثل: `5.00` أو `10.00`")
            context.user_data["mode"] = "coupon"
            return
        wait = await update.message.reply_text("🎫 جاري بناء القسيمة...")
        try:
            matches = get_all_matches(datetime.now().strftime("%Y-%m-%d"))
            if not matches:
                await wait.edit_text("😔 لا توجد مباريات كافية اليوم.")
                return
            result = ai_coupon(text, matches)
            await wait.delete()
            await safe_send(update.message, result)
        except Exception as e:
            logger.error(e)
            await wait.edit_text("❌ حدث خطأ، حاول مرة أخرى.")
        return

    # وضع التوقع — تحقق من الحد اليومي
    if not has_quota(db, uid):
        link = ref_link(uid)
        await safe_send(update.message,
            f"⛔ *انتهت توقعاتك اليوم!*\n\n"
            f"🆓 شارك رابطك — كل {REFERRAL_GOAL} أصدقاء = توقع مجاني\n`{link}`\n\n"
            f"💎 أو اشترك VIP بـ $5/شهر",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 اشترك VIP",    callback_data="vip_info")],
                [InlineKeyboardButton("👥 رابط الإحالة", callback_data="referral")]
            ])
        )
        return

    wait = await update.message.reply_text("🔍 جاري التحليل...")
    try:
        result = ai_analyze(text)
        consume(db, uid, text)
        db_save(db)
        # احفظ اسم المباراة لزر "سبب التوقع"
        context.user_data["last_match"] = text[:30]
        await wait.delete()
        await safe_send(update.message, result)
        rem = remaining(db, uid)
        await update.message.reply_text(
            f"🎯 متبقي: *{rem}*",
            parse_mode="Markdown",
            reply_markup=kb_after_analysis(text)
        )
    except Exception as e:
        logger.error(e)
        await wait.edit_text("❌ حدث خطأ، حاول مرة أخرى.")

# ═══════════════════════════════════════════════
#  HANDLERS — CALLBACKS
# ═══════════════════════════════════════════════
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    db  = db_load()
    uid = q.from_user.id
    d   = q.data

    # سبب التوقع
    if d.startswith("reason_"):
        match = d[7:]  # استخرج اسم المباراة
        # حاول الحصول على الاسم الكامل من user_data
        full_match = context.user_data.get("last_match", match)
        await q.edit_message_text("🔍 جاري تحليل أسباب التوقع...")
        try:
            result = ai_reason(full_match)
            await safe_edit(q, result, reply_markup=kb_back())
        except Exception as e:
            logger.error(e)
            await q.edit_message_text("❌ حدث خطأ، حاول مرة أخرى.")
        return

    if d in ("leagues_today", "leagues_tomorrow"):
        day = "today" if d == "leagues_today" else "tomorrow"
        await safe_edit(q, f"🏆 *اختر الدوري — {day_label(day)}:*",
                        reply_markup=kb_leagues(day))

    elif d.startswith("league_"):
        parts = d.split("_")
        code  = parts[1]
        day   = parts[2] if len(parts) > 2 else "today"
        if code not in LEAGUES:
            await q.edit_message_text("❌ دوري غير معروف.")
            return
        name = LEAGUES[code]["name"]
        await q.edit_message_text(f"⏳ جاري جلب مباريات {name}...")
        date    = day_date(day)
        matches = get_matches(code, date)
        context.user_data[f"m_{code}_{day}"] = matches
        if not matches:
            await safe_edit(q, f"😔 لا توجد مباريات في {name} {day_label(day)}.",
                            reply_markup=kb_back())
        else:
            await safe_edit(q,
                f"📅 *{name} — {day_label(day)}*\n\nاضغط مباراة للتحليل 👇",
                reply_markup=kb_matches(matches, code, day))

    elif d.startswith("match_"):
        parts   = d.split("_")
        code    = parts[1]
        day     = parts[2]
        idx     = int(parts[3])
        matches = context.user_data.get(f"m_{code}_{day}", [])
        if not matches or idx >= len(matches):
            await q.edit_message_text("❌ حدث خطأ، ارجع وحاول.")
            return
        if not has_quota(db, uid):
            await safe_edit(q, "⛔ *انتهت توقعاتك اليوم!*\n\n💎 اشترك VIP.",
                            reply_markup=kb_vip())
            return
        m  = matches[idx]
        mt = f"{m['home']} vs {m['away']}"
        await q.edit_message_text(f"🔍 جاري تحليل {mt}...")
        try:
            result = ai_analyze(mt)
            consume(db, uid, mt)
            db_save(db)
            context.user_data["last_match"] = mt[:30]
            await safe_edit(q, result)
            rem = remaining(db, uid)
            await context.bot.send_message(q.message.chat_id,
                f"🎯 متبقي: *{rem}*",
                parse_mode="Markdown",
                reply_markup=kb_after_analysis(mt)
            )
        except Exception as e:
            logger.error(e)
            await q.edit_message_text("❌ حدث خطأ، حاول مرة أخرى.")

    elif d == "safe_bet":
        await q.edit_message_text("🔍 جاري البحث عن أضمن رهان اليوم...")
        matches = get_all_matches(datetime.now().strftime("%Y-%m-%d"))
        if not matches:
            await safe_edit(q, "😔 لا توجد مباريات كافية اليوم.", reply_markup=kb_back())
            return
        try:
            result = ai_safe_bet(matches)
            await safe_edit(q, result, reply_markup=kb_back())
        except Exception as e:
            logger.error(e)
            await q.edit_message_text("❌ حدث خطأ، حاول مرة أخرى.")

    elif d == "predict":
        context.user_data["mode"] = "predict"
        await safe_edit(q, "⚽ *أرسل اسم المباراة:*\n\nمثال: ريال مدريد vs برشلونة")

    elif d == "coupon":
        if not is_vip(db, uid):
            await safe_edit(q,
                "🔒 *القسيمة الذهبية للـ VIP فقط!*\n\n"
                "💎 اشترك بـ $5/شهر للحصول على قسيمة بالأود الذي تريده!",
                reply_markup=kb_vip())
            return
        context.user_data["mode"] = "coupon"
        await safe_edit(q,
            "🎫 *القسيمة الذهبية*\n\n"
            "أرسل الأود الإجمالي الذي تريده:\n\n"
            "مثال: `5.00` أو `10.00` أو `20.00`\n\n"
            "سأختار مباريات مختلفة للوصول لهذا الأود 🎯")

    elif d == "write_review":
        context.user_data["mode"] = "review"
        await safe_edit(q,
            "✍️ *أرسل تقييمك الآن:*\n\n"
            "اكتب رأيك أو أي خطأ لاحظته — سيصل مباشرة للإدارة 📩")

    elif d == "referral":
        u    = db_user(db, uid, q)
        refs = len(u.get("referrals", []))
        next_b = REFERRAL_GOAL - (refs % REFERRAL_GOAL)
        link = ref_link(uid)
        await safe_edit(q,
            f"👥 *نظام الإحالة*\n\n"
            f"🔗 رابطك:\n`{link}`\n\n"
            f"📊 إحالاتك: *{refs}* | تحتاج *{next_b}* للتوقع التالي\n"
            f"⭐ كل إحالة = 10 نقاط | كل {REFERRAL_GOAL} إحالات = توقع مجاني",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 شارك الرابط",
                                      url=f"https://t.me/share/url?url={link}&text=%F0%9F%8F%86+%D8%A3%D9%81%D8%B6%D9%84+%D8%A8%D9%88%D8%AA+%D8%AA%D9%88%D9%82%D8%B9%D8%A7%D8%AA%21")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ]))

    elif d == "my_stats":
        u     = db_user(db, uid, q)
        badge = "💎 VIP" if is_vip(db, uid) else "🆓 مجاني"
        await safe_edit(q,
            f"📊 *إحصائياتك:*\n\n"
            f"🏷️ {badge}\n"
            f"🎯 متبقي اليوم: {remaining(db, uid)}\n"
            f"📈 إجمالي طلباتك: {u['total_requests']}\n"
            f"👥 إحالاتك: {len(u.get('referrals',[]))}\n"
            f"⭐ نقاطك: {u.get('points',0)}/100\n"
            f"🎁 توقعات مكسوبة: {u.get('bonus_requests',0)}\n"
            f"📅 انضمت: {u['joined']}",
            reply_markup=kb_back())

    elif d == "vip_info":
        await safe_edit(q,
            f"💎 *VIP — $5/شهر*\n\n"
            "✅ توقعات غير محدودة\n"
            "✅ القسيمة الذهبية بأود مخصص\n"
            "✅ أضمن رهان يومي\n"
            "✅ مباريات اليوم والغد\n"
            "✅ زر سبب التوقع المفصل\n\n"
            f"للاشتراك تواصل مع: {ADMIN_USERNAME}",
            reply_markup=kb_vip())

    elif d == "pay_vip":
        await safe_edit(q,
            f"💳 *للاشتراك VIP:*\n\n"
            f"👤 {ADMIN_USERNAME}\n"
            "💰 $5/شهر | ⚡ تفعيل فوري\n\n"
            "طرق الدفع:\n• USDT (TRC20)\n• PayPal\n• تحويل بنكي")

    elif d == "back_main":
        u      = db_user(db, uid)
        badge  = "💎 VIP" if is_vip(db, uid) else "🆓 مجاني"
        rem    = remaining(db, uid)
        points = u.get("points", 0)
        name   = q.from_user.first_name
        await safe_edit(q,
            f"👑 *DASI BET — {name}*\n\n"
            f"🏷️ {badge} | 🎯 متبقي: *{rem}* | ⭐ {points}/100\n\n"
            f"اختر من القائمة 👇",
            reply_markup=kb_main(is_vip(db, uid)))

# ═══════════════════════════════════════════════
#  HANDLERS — ADMIN
# ═══════════════════════════════════════════════
def admin_only(fn):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            return
        await fn(update, context)
    return wrapper

@admin_only
async def cmd_admin(update, context):
    db    = db_load()
    today = datetime.now().strftime("%Y-%m-%d")
    total  = len(db["users"])
    vip_c  = sum(1 for u in db["users"].values() if u.get("vip"))
    active = sum(1 for u in db["users"].values() if u.get("last_request_date") == today)
    await update.message.reply_text(
        f"👑 *لوحة التحكم*\n\n"
        f"👥 {total} | 💎 {vip_c} VIP | 🟢 {active} اليوم\n\n"
        f"`/vip [ID]` — تفعيل VIP\n"
        f"`/unvip [ID]` — إلغاء VIP\n"
        f"`/ban [ID]` — حظر\n"
        f"`/unban [ID]` — فك حظر\n"
        f"`/broadcast [رسالة]` — رسالة جماعية\n"
        f"`/users` — قائمة المستخدمين\n"
        f"`/stats` — إحصائيات\n"
        f"`/clearcache` — مسح الكاش\n"
        f"`/resetwelcome` — إعادة الصورة الترحيبية",
        parse_mode="Markdown")

@admin_only
async def cmd_vip(update, context):
    if not context.args:
        await update.message.reply_text("استخدام: /vip [ID]")
        return
    db  = db_load()
    uid = context.args[0]
    if uid not in db["users"]:
        await update.message.reply_text("❌ المستخدم غير موجود")
        return
    expiry = activate_vip(db, int(uid))
    await update.message.reply_text(
        f"✅ VIP مفعّل لـ `{uid}` حتى {expiry}", parse_mode="Markdown")
    try:
        await context.bot.send_message(
            int(uid), "🎉 *تم تفعيل VIP!*\n\nاضغط /start 🚀", parse_mode="Markdown")
    except Exception:
        pass

@admin_only
async def cmd_unvip(update, context):
    if not context.args:
        return
    db = db_load()
    uid = context.args[0]
    if uid in db["users"]:
        db["users"][uid]["vip"] = False
        db_save(db)
        await update.message.reply_text(f"✅ إلغاء VIP لـ `{uid}`", parse_mode="Markdown")

@admin_only
async def cmd_ban(update, context):
    if not context.args:
        return
    db = db_load()
    uid = context.args[0]
    if uid in db["users"]:
        db["users"][uid]["blocked"] = True
        db_save(db)
        await update.message.reply_text(f"⛔ حظر `{uid}`", parse_mode="Markdown")

@admin_only
async def cmd_unban(update, context):
    if not context.args:
        return
    db = db_load()
    uid = context.args[0]
    if uid in db["users"]:
        db["users"][uid]["blocked"] = False
        db_save(db)
        await update.message.reply_text(f"✅ فك حظر `{uid}`", parse_mode="Markdown")

@admin_only
async def cmd_broadcast(update, context):
    if not context.args:
        await update.message.reply_text("استخدام: /broadcast [الرسالة]")
        return
    db   = db_load()
    msg  = " ".join(context.args)
    sent = failed = 0
    for uid in db["users"]:
        try:
            await context.bot.send_message(
                int(uid), f"📢 *من الإدارة:*\n\n{msg}", parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ أُرسلت: {sent} | ❌ فشل: {failed}")

@admin_only
async def cmd_users(update, context):
    db    = db_load()
    lines = []
    for uid, u in list(db["users"].items())[-20:]:
        b = "💎" if u.get("vip") else "🆓"
        x = "⛔" if u.get("blocked") else ""
        lines.append(f"{b}{x} `{uid}` {u.get('name','?')} | {u.get('total_requests',0)}")
    await update.message.reply_text(
        "👥 *آخر 20:*\n\n" + "\n".join(lines), parse_mode="Markdown")

@admin_only
async def cmd_stats(update, context):
    db    = db_load()
    today = datetime.now().strftime("%Y-%m-%d")
    active = sum(1 for u in db["users"].values() if u.get("last_request_date") == today)
    vip_c  = sum(1 for u in db["users"].values() if u.get("vip"))
    refs   = sum(len(u.get("referrals", [])) for u in db["users"].values())
    await update.message.reply_text(
        f"📊 *إحصائيات:*\n\n"
        f"👥 {len(db['users'])} مستخدم\n"
        f"💎 {vip_c} VIP\n"
        f"🟢 {active} نشط اليوم\n"
        f"📈 {db.get('total_requests',0)} طلب إجمالي\n"
        f"👥 {refs} إحالة إجمالي",
        parse_mode="Markdown")

@admin_only
async def cmd_clearcache(update, context):
    cache_clear()
    await update.message.reply_text("✅ تم مسح الكاش!")

@admin_only
async def cmd_resetwelcome(update, context):
    if os.path.exists(WELCOME_ID_FILE):
        os.remove(WELCOME_ID_FILE)
    await update.message.reply_text("✅ سيتم إعادة رفع الصورة في المرة القادمة!")

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    db    = db_load()
    today = datetime.now().strftime("%Y-%m-%d")
    active = sum(1 for u in db["users"].values()
                 if u.get("last_request_date") == today)
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"📊 *تقرير يومي — {today}*\n\n"
            f"👥 {len(db['users'])} مستخدم\n"
            f"🟢 {active} نشط اليوم\n"
            f"📈 {db.get('total_requests',0)} طلب إجمالي",
            parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Daily report: {e}")

# ═══════════════════════════════════════════════
#  FLASK + MAIN
# ═══════════════════════════════════════════════
_flask = Flask(__name__)

@_flask.route("/")
def health():
    return "✅ OK", 200

def main():
    os.makedirs("data", exist_ok=True)
    Thread(target=lambda: _flask.run(
        host="0.0.0.0", port=PORT, use_reloader=False), daemon=True).start()
    logger.info(f"✅ Flask on port {PORT}")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("admin",        cmd_admin))
    app.add_handler(CommandHandler("vip",          cmd_vip))
    app.add_handler(CommandHandler("unvip",        cmd_unvip))
    app.add_handler(CommandHandler("ban",          cmd_ban))
    app.add_handler(CommandHandler("unban",        cmd_unban))
    app.add_handler(CommandHandler("broadcast",    cmd_broadcast))
    app.add_handler(CommandHandler("users",        cmd_users))
    app.add_handler(CommandHandler("stats",        cmd_stats))
    app.add_handler(CommandHandler("clearcache",   cmd_clearcache))
    app.add_handler(CommandHandler("resetwelcome", cmd_resetwelcome))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.job_queue.run_daily(daily_report, time=dtime(8, 0))

    logger.info("✅ Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
