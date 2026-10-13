import asyncio
import os
import sys
import sqlite3
import random
import logging
import time
import aiohttp
import hmac
import hashlib
import json
import html
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    SendMessage, EditMessageText, EditMessageCaption,
    SendPhoto, SendDocument, SendVideo, SendAnimation,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, Dice, BufferedInputFile
)

# ==============================================================================
# 1. BOT CONFIGURATION & CONSTANTS
# ==============================================================================
# Configure secrets in Render -> Environment. Never hard-code a bot token here.
BOT_TOKEN = os.getenv("BOT_TOKEN", "8873930996:AAGpGeSAtyJzWtDAdqbq6t9OChomqwPXliM").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "@AimAi_Kirampur_bot").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "5765985377").strip() or "0")
ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "@Kirampur").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "Galu.db").strip() or "Galu.db"
SUPPORT_TELEGRAM_URL = os.getenv("SUPPORT_TELEGRAM_URL", "https://t.me/Kirampur").strip()
SUPPORT_WHATSAPP_URL = os.getenv("SUPPORT_WHATSAPP_URL", "").strip()

# --- FAMGATEWAY (famgateway.in) AUTO PAYMENT ---
# Get your key (sk_live_...) from https://famgateway.in/dashboard.php
# You can also set/change it from the bot: Admin Panel -> FamPay Setup
FAMGATEWAY_API_KEY = os.getenv("FAMGATEWAY_API_KEY", "").strip()
FAMGATEWAY_BASE = "https://famgateway.in"
MIN_DEPOSIT = 1.0
MAX_DEPOSIT = 50000.0

USDT_TO_INR = 90.0
VIP_DISCOUNT_PERCENTAGE = 10.0
VIP_PRICE_INR = 1000.0

WELCOME_STICKER_ID = os.getenv("WELCOME_STICKER_ID", "").strip()  # Optional; blank disables welcome sticker

FIXED_CATEGORIES = [
    "CARROM POOL AUTOPLAY ENGINE"
]

# ==============================================================================
# YOUR PREMIUM EMOJIS – all required emoji IDs (updated with new premium ones)
# ==============================================================================
DEFAULT_EMOJIS = {
    'product_store': '6163205892834598715',
    'profile': '5258011929993026890',
    'add_balance': '5985630530111020079',
    'history': '6032594876506312598',
    'support': '5967280668885913944',
    'back': '5877536313623711363',
    'upi': '5807750375033278838',
    'reseller': '5886505193180239900',
    'tutorial': '6005986106703613755',
    'telegram': '5875465628285931233',
    'whatsapp': '5954224165874569584',
    'welcome': '5994502837327892086',
    'vip': '5206607081334906820',
    'category_android_non_root': '6161172706856282588',
    'category_android_root': '6161449831031118974',
    'category_pc': '5350554349074391003',
    'grid_id': '5474625972751837256',
    'name': '5215399540814781035',
    'account_level': '6129584162992034014',
    'regular_user': '5904630315946611415',
    'wallet': '6210859306602995217',
    'current_balance': '5316711376876485361',
    'global_stats': '6161437856662298090',
    'total_orders': '6160968017304888311',
    'total_spent': '5197503331215361533',
    'joined_grid': '5433614043006903194',
    'info_icon': '6037421444789440735',
    'check_icon': '6161241250239356403',
    'checkbox_icon': '6161437856662298090',
    'shield_icon': '6086672466132865380',
    'money_icon': '5890848474563352982',
    'redeem_icon': '5377624166436445368',
    'wallet_left': '6210859306602995217',
    'wallet_right': '5305699699204837855',
    'point_down': '6161302621027049305',
}

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_activity.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it in Render Environment Variables; do not paste it into source code.")
if ADMIN_ID <= 0:
    raise RuntimeError("ADMIN_ID is missing or invalid. Add your numeric Telegram user ID in Render Environment Variables.")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

def fmt_curr(amount: float) -> str:
    return f"₹{amount:,.2f}"

def safe_float(val, default=0.0):
    """Safely convert a value to float, return default if fails."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

# ==============================================================================
# 2. DATABASE FUNCTIONS
# ==============================================================================
def _ensure_database_directory() -> None:
    parent = os.path.dirname(os.path.abspath(DATABASE_PATH))
    os.makedirs(parent, exist_ok=True)

def db_query(query: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False, commit: bool = True) -> Any:
    _ensure_database_directory()
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    try:
        c.execute(query, params)
        if fetchone:
            res = c.fetchone()
        elif fetchall:
            res = c.fetchall()
        else:
            res = None
        if commit: conn.commit()
        return res
    except Exception as e:
        logger.error(f"DB Error: {e} | Query: {query} | Params: {params}")
        if commit: conn.rollback()
        return None
    finally:
        conn.close()

def get_setting(key: str, default: str = "") -> str:
    val = db_query("SELECT value FROM settings WHERE key=?", (key,), fetchone=True)
    return val[0] if val and val[0] else default

def set_setting(key: str, value: str) -> None:
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

def log_activity(user_id: int, action: str, details: str = "") -> None:
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_query(
            "INSERT INTO activity_logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, action, details, timestamp)
        )
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

def get_emoji(slot: str, default_id: str = None) -> str:
    stored = get_setting(f"emoji_{slot}", "")
    emoji_id = stored if stored and stored.isdigit() else (default_id or DEFAULT_EMOJIS.get(slot, ""))
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">✨</tg-emoji>'
    return "✨"

def get_emoji_fb(slot: str, fallback: str, default_id: str = "") -> str:
    """Premium emoji (admin-set ID, else built-in ID), otherwise the normal emoji."""
    stored = get_setting(f"emoji_{slot}", "")
    emoji_id = stored if stored and stored.isdigit() else default_id
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback

def get_emoji_icon(slot: str, default_id: str = None) -> str:
    stored = get_setting(f"emoji_{slot}", "")
    emoji_id = stored if stored and stored.isdigit() else (default_id or DEFAULT_EMOJIS.get(slot, ""))
    return emoji_id

# ==============================================================================
# 3. STRING RESOURCES – using placeholders for premium emojis
# ==============================================================================
# Divider under the blocks of the main menu. Make it longer/shorter if it wraps differently on your phone.
DIVIDER_LINE = "─" * 56

# Main-menu emoji slots: slot -> normal emoji shown until you set a premium emoji ID for it
# (Admin Panel -> Edit All Emojis, or see /emojiid to read IDs from any message).
START_MENU_EMOJIS = {
    # slot: (normal emoji fallback, premium emoji ID)
    'e_cart':  ('🛒', '5451937962629544243'),   # 🛒 — LUFFY STORY — 🛒
    'e_crown': ('👑', '5433758796289685818'),   # 👑 Welcome
    'e_game':  ('🎮', '6050924877802640640'),   # Premium Game Keys
    'e_user':  ('👤', '5927266769281487788'),   # Instant Delivery 24/7
    'e_100':   ('💯', '6001517283426439371'),   # 100% Secure Payment
    'e_chart': ('📊', '6165617418187050280'),   # Best Prices Guaranteed
    'e_flag':  ('🇮🇳', '6195196922379115661'),  # Safe And Trusted
    'e_mail':  ('📩', '6194884545112709374'),   # Professional Support
    'e_money': ('💰', '6001434068435079689'),   # Wallet Balance
    'e_tap':   ('👑', '6057415823222379852'),   # Tap Shop Now to Start!
}

UI_TEXTS = {
    "start_menu": (
        "<blockquote>{e_cart} <b>— LUFFY STORY —</b> {e_cart}</blockquote>"
        "{e_crown} Welcome, <b>{first_name}</b>!\n\n"
        "<blockquote>"
        "{e_game} Premium Game Keys\n"
        "{e_user} Instant Delivery 24/7\n"
        "{e_100} 100% Secure Payment\n"
        "{e_chart} Best Prices Guaranteed\n"
        "{e_flag} Safe And Trusted\n"
        "{e_mail} Professional Support"
        "</blockquote>\n"
        + DIVIDER_LINE + "\n\n"
        "<blockquote>{e_money} <b>Wallet Balance:</b> {balance}</blockquote>\n"
        + DIVIDER_LINE + "\n\n"
        "{e_tap} <b>Tap Shop Now to Start!</b>"
    ),
    "vip_menu": (
        "🌟 <b><u>VIP MEMBERSHIP CLUB</u></b> 🌟\n\n"
        "Unlock premium benefits and permanent discounts!\n\n"
        "💎 <b>VIP Benefits:</b>\n"
        "• Flat 15% off on ALL products (Stacks with Reseller!)\n"
        "• Priority Support\n"
        "• Exclusive VIP-only giveaways\n\n"
        "💳 <b>VIP Price:</b> ₹299.00 (Lifetime)\n"
        "👤 <b>Your Status:</b> {vip_status}"
    ),
    "add_balance_menu": (
        "{add_balance} <b>ADD BALANCE</b> {info_icon}\n\n"
        "{info_icon} Select your preferred payment method. {check_icon}\n\n"
        "┣ {upi} UPI — Fast Indian payments {checkbox_icon}\n"
        ""
        "{shield_icon} Payments are verified securely. {check_icon}"
    )
}

def get_ui_text(key: str, **kwargs) -> str:
    val = db_query("SELECT value FROM settings WHERE key=?", (f"ui_{key}",), fetchone=True)
    template = val[0] if val and val[0] else UI_TEXTS.get(key, "")

    emoji_map = {
        '{product_store}': get_emoji('product_store'),
        '{profile}': get_emoji('profile'),
        '{add_balance}': get_emoji('add_balance'),
        '{history}': get_emoji('history'),
        '{tutorial}': get_emoji('tutorial'),
        '{support}': get_emoji('support'),
        '{telegram}': get_emoji('telegram'),
        '{whatsapp}': get_emoji('whatsapp'),
        '{upi}': get_emoji('upi'),
        '{binance}': get_emoji('binance'),
        '{info_icon}': get_emoji('info_icon'),
        '{check_icon}': get_emoji('check_icon'),
        '{checkbox_icon}': get_emoji('checkbox_icon'),
        '{shield_icon}': get_emoji('shield_icon'),
        '{money_icon}': get_emoji('money_icon'),
        '{redeem_icon}': get_emoji('redeem_icon'),
        '{wallet_left}': get_emoji('wallet_left'),
        '{wallet_right}': get_emoji('wallet_right'),
        '{point_down}': get_emoji('point_down'),
    }
    for placeholder, emoji_tag in emoji_map.items():
        template = template.replace(placeholder, emoji_tag)
    for slot, (fb, default_id) in START_MENU_EMOJIS.items():
        template = template.replace("{" + slot + "}", get_emoji_fb(slot, fb, default_id))

    # Fill values safely: never fails, even if the template has a placeholder we don't know.
    for k, v in kwargs.items():
        template = template.replace("{" + k + "}", str(v))
    template = re.sub(r"\{e_[a-z0-9_]+\}", "", template)   # unknown emoji slots -> removed, never shown raw
    return template

# ==============================================================================
# 4. DATABASE INITIALISATION & MIGRATION
# ==============================================================================
def init_db() -> None:
    _ensure_database_directory()
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            phone TEXT, 
            first_name TEXT, 
            username TEXT,
            balance REAL DEFAULT 0.0, 
            account_type TEXT DEFAULT 'Regular', 
            orders_count INTEGER DEFAULT 0, 
            spent REAL DEFAULT 0.0, 
            last_spin TEXT, 
            joined_date TEXT,
            is_reseller INTEGER DEFAULT 0,
            reseller_since TEXT,
            total_saved REAL DEFAULT 0.0,
            is_banned INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            is_vip INTEGER DEFAULT 0,
            vip_since TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            category TEXT, 
            panel_name TEXT DEFAULT '',
            name TEXT, 
            price_inr REAL, 
            reseller_price REAL DEFAULT 0.0,
            stock INTEGER, 
            apk_link TEXT, 
            validity TEXT DEFAULT 'Lifetime', 
            device_limit TEXT DEFAULT '1 Device',
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS product_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            product_id INTEGER, 
            key_text TEXT, 
            is_used INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            product_name TEXT, 
            price_paid REAL, 
            delivered_key TEXT, 
            purchase_date TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            message TEXT, 
            status TEXT DEFAULT 'Open',
            created_at TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, 
            value TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS coupons (
            code TEXT PRIMARY KEY, 
            amount REAL, 
            uses_left INTEGER
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS redeemed (
            user_id INTEGER, 
            code TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            order_id TEXT PRIMARY KEY, 
            user_id INTEGER, 
            amount_inr REAL, 
            status TEXT, 
            timestamp INTEGER,
            qr_url TEXT,
            upi_id TEXT,
            expires_at INTEGER,
            checkout_url TEXT,
            chat_id INTEGER,
            message_id INTEGER,
            utr TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS crypto_txns (
            txid TEXT PRIMARY KEY, 
            user_id INTEGER, 
            amount_usdt REAL, 
            timestamp INTEGER
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS spin_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            amount REAL
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            timestamp TEXT
        )
    ''')

    migrations = [
        "ALTER TABLE users ADD COLUMN is_vip INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN vip_since TEXT",
        "ALTER TABLE products ADD COLUMN is_active INTEGER DEFAULT 1",
        "ALTER TABLE tickets ADD COLUMN created_at TEXT",
        "ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN warnings INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN panel_name TEXT DEFAULT ''",
        "ALTER TABLE transactions ADD COLUMN qr_url TEXT",
        "ALTER TABLE transactions ADD COLUMN upi_id TEXT",
        "ALTER TABLE transactions ADD COLUMN expires_at INTEGER",
        "ALTER TABLE transactions ADD COLUMN checkout_url TEXT",
        "ALTER TABLE transactions ADD COLUMN chat_id INTEGER",
        "ALTER TABLE transactions ADD COLUMN message_id INTEGER",
        "ALTER TABLE transactions ADD COLUMN utr TEXT",
    ]
    for mig in migrations:
        try: c.execute(mig)
        except sqlite3.OperationalError: pass

    # Existing inventory is always rebuilt from the local manual-key vault.
    try:
        c.execute("UPDATE products SET stock=(SELECT COUNT(*) FROM product_keys k WHERE k.product_id=products.id AND k.is_used=0)")
        c.execute("UPDATE products SET category='CARROM POOL AUTOPLAY ENGINE' WHERE LOWER(category) IN ('android non root panel','android root panel','pc panel')")
    except sqlite3.OperationalError:
        pass

    # Old-gateway (fampay.anujbots.xyz) orders can never be verified on FamGateway -> close them.
    c.execute("UPDATE transactions SET status='expired' WHERE status='pending' AND order_id LIKE 'FAMPAY%'")
    

    default_settings = [
        ('reseller_system_status', 'ON'),
        ('bot_status', 'ON'),
        ('how_to_video', 'None'),
        ('famgateway_api_key', FAMGATEWAY_API_KEY),
        ('binance_api', ''),
        ('binance_secret', ''),
        ('binance_address', ''),
        ('vip_status', 'OFF'),
        ('reseller_setup_fee', '200.0'),
        ('reseller_min_balance', '500.0'),
        ('migration_done', '0'),
        ('support_telegram', SUPPORT_TELEGRAM_URL),
        ('support_whatsapp', SUPPORT_WHATSAPP_URL),
        ('ui_start_menu', UI_TEXTS['start_menu']),
        ('ui_vip_menu', UI_TEXTS['vip_menu']),
        ('ui_add_balance_menu', UI_TEXTS['add_balance_menu']),
    ]
    for slot, emoji_id in DEFAULT_EMOJIS.items():
        default_settings.append((f"emoji_{slot}", emoji_id))
    for slot, (fb, default_id) in START_MENU_EMOJIS.items():
        default_settings.append((f"emoji_{slot}", default_id))
    
    for key, val in default_settings:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

    conn.commit()
    conn.close()


    # Removed feature settings are intentionally ignored by the UI.
    # Their old database values may remain, but no button or handler exposes them.

def migrate_categories() -> None:
    done = get_setting("migration_done", "0")
    
    # ALWAYS force update emojis and UI texts regardless of migration status
    logger.info("Forcing emoji and UI text updates...")
    
    # Remove legacy Ludo Spin / Download Files settings from existing databases
    db_query("DELETE FROM settings WHERE key IN ('emoji_ludo_spin', 'emoji_download', 'ui_download_files', 'ui_lucky_dice_result', 'all_files_link', 'spin_status', 'daily_spin_limit', 'emoji_referral')")

    # Update all emoji settings
    for slot, emoji_id in DEFAULT_EMOJIS.items():
        set_setting(f"emoji_{slot}", emoji_id)
    
    # Force update UI texts
    set_setting("ui_start_menu", UI_TEXTS['start_menu'])
    set_setting("ui_add_balance_menu", UI_TEXTS['add_balance_menu'])
    set_setting("ui_vip_menu", UI_TEXTS['vip_menu'])
    logger.info("UI texts and emojis updated with new placeholders and IDs.")
    
    # Fix any corrupted price columns (one-time cleanup)
    _ensure_database_directory()
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    products = c.execute("SELECT id, price_inr, reseller_price FROM products").fetchall()
    f
