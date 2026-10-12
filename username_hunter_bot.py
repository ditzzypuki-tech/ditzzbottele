#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================
  TELEGRAM USERNAME HUNTER BOT  (RENDER-READY)
=============================================================
  Versi ini sudah dimodifikasi untuk deploy di Render.com:
    - Menggunakan web server (Flask) agar Render menganggap "sehat"
    - Bot Telegram jalan di background thread
    - Token dibaca dari Environment Variable BOT_TOKEN
=============================================================
"""

import os
import sys
import time
import random
import string
import logging
import threading
import asyncio
from datetime import datetime
from functools import wraps

# ============================================================
# IMPORT DEPENDENCIES
# ============================================================
try:
    import requests
    from flask import Flask
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
    from telegram.error import TelegramError
except ImportError as e:
    print(f"❌ Gagal import module: {e}")
    print("Pastikan requirements.txt sudah diisi:")
    print("  python-telegram-bot")
    print("  flask")
    print("  requests")
    sys.exit(1)


# ============================================================
# KONFIGURASI TOKEN (DARI ENVIRONMENT VARIABLE)
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    print("⚠️  WARNING: BOT_TOKEN belum di-set di Environment Variable!")
    print("   Set di Render: Environment → BOT_TOKEN = token_kamu")


# ============================================================
# KONFIGURASI LAINNYA
# ============================================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 10
DELAY_BETWEEN_CHECK = 0.6
MAX_KANDIDAT = 10
CACHE_TTL = 3600


# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("UsernameHunter")


# ============================================================
# FLASK WEB SERVER (untuk Render)
# ============================================================
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "✅ Username Hunter Bot is running!", 200


@flask_app.route("/health")
def health():
    return "OK", 200


# ============================================================
# CACHE
# ============================================================
_cache: dict = {}


def cache_get(username: str):
    if username in _cache:
        result, timestamp = _cache[username]
        if time.time() - timestamp < CACHE_TTL:
            return result
        del _cache[username]
    return None


def cache_set(username: str, result: bool):
    _cache[username] = (result, time.time())


# ============================================================
# VALIDASI USERNAME
# ============================================================
def is_valid_format(username: str) -> bool:
    if not username:
        return False
    if len(username) < 5 or len(username) > 32:
        return False
    if not all(c.isalnum() or c == "_" for c in username):
        return False
    if "__" in username:
        return False
    return True


# ============================================================
# CORE: CEK KETERSEDIAAN USERNAME
# ============================================================
def cek_ketersediaan_username(username: str) -> bool:
    username = username.lstrip("@").lower().strip()

    if not is_valid_format(username):
        return False

    cached = cache_get(username)
    if cached is not None:
        return cached

    url = f"https://t.me/{username}"

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code == 404:
            cache_set(username, True)
            return True

        if response.status_code == 200:
            html = response.text
            indikator_dipakai = [
                "tgme_page_title",
                "tgme_page_photo",
                "tgme_page_action",
                "tgme_page_context_link",
                "If you have Telegram",
                "tgme_page_extra",
            ]
            for ind in indikator_dipakai:
                if ind in html:
                    cache_set(username, False)
                    return False
            cache_set(username, True)
            return True

        logger.warning(f"Status {response.status_code} untuk @{username}")
        return False

    except requests.Timeout:
        logger.error(f"Timeout cek @{username}")
        return False
    except requests.RequestException as e:
        logger.error(f"Request error cek @{username}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error cek @{username}: {e}")
        return False


# ============================================================
# GENERATOR KANDIDAT USERNAME
# ============================================================
PREFIXES = [
    "my", "the", "get", "go", "hey", "ok", "top", "pro",
    "super", "ultra", "real", "only", "just", "its", "mr",
    "team", "official", "daily",
]

SUFFIXES = [
    "hub", "lab", "box", "kit", "zen", "wise", "pal",
    "mate", "hq", "io", "app", "bot", "id", "x", "pro",
    "plus", "guru", "master", "world", "zone", "space",
]


def generate_kandidat(tema: str = "", jumlah: int = 5) -> list:
    kandidat = []

    if tema:
        tema_clean = (
            tema.lower()
            .replace(" ", "")
            .replace("_", "")
            .replace("-", "")
        )
        kandidat.extend([
            f"{tema_clean}bot",
            f"{tema_clean}_bot",
            f"my{tema_clean}bot",
            f"{tema_clean}hub",
            f"{tema_clean}lab",
            f"{tema_clean}app",
            f"{tema_clean}id",
            f"the{tema_clean}",
            f"{tema_clean}hq",
        ])
        while len(kandidat) < jumlah * 2:
            p = random.choice(PREFIXES)
            s = random.choice(SUFFIXES)
            kandidat.append(f"{p}{tema_clean}{s}")
    else:
        for _ in range(jumlah * 2):
            length = random.randint(6, 12)
            chars = string.ascii_lowercase + string.digits
            kandidat.append("".join(random.choices(chars, k=length)))

    seen = set()
    hasil = []
    for k in kandidat:
        if k in seen:
            continue
        seen.add(k)
        if is_valid_format(k):
            hasil.append(k)
        if len(hasil) >= jumlah:
            break

    return hasil


# ============================================================
# DECORATOR: ERROR HANDLER
# ============================================================
def safe_handler(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except TelegramError as e:
            logger.error(f"TelegramError di {func.__name__}: {e}")
        except Exception as e:
            logger.exception(f"Error di {func.__name__}: {e}")
            try:
                if update and update.effective_message:
                    await update.effective_message.reply_text(
                        "⚠️ Terjadi error. Coba lagi nanti."
                    )
            except Exception:
                pass
    return wrapper


# ============================================================
# HANDLERS TELEGRAM
# ============================================================
@safe_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pesan = (
        "🔍 *Username Hunter Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Saya bisa membantu kamu mencari username Telegram "
        "yang bagus dan masih tersedia!\n\n"
        "*📋 Perintah:*\n"
        "• `/cek <username>` — Cek satu username\n"
        "   contoh: `/cek mycoolname`\n\n"
        "• `/cari <tema>` — Cari kandidat username bagus\n"
        "   contoh: `/cari crypto`\n\n"
        "• `/random` — Generate username random yang tersedia\n\n"
        "• `/help` — Tampilkan bantuan ini\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ *Catatan:*\n"
        "• Hasil adalah *estimasi* dari halaman publik Telegram.\n"
        "• Username user/channel/bot berbagi namespace yang sama.\n"
        "• Username premium/reserved perlu dibeli di Fragment.com.\n"
        "• Selalu verifikasi di aplikasi Telegram sebelum dipakai."
    )
    await update.message.reply_text(
        pesan, parse_mode="Markdown", disable_web_page_preview=True
    )


@safe_handler
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_command(update, context)


@safe_handler
async def cek_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ *Format salah!*\n\n"
            "Gunakan: `/cek username`\n"
            "Contoh: `/cek mycoolname`",
            parse_mode="Markdown",
        )
        return

    username = context.args[0].lstrip("@")

    if not is_valid_format(username):
        await update.message.reply_text(
            f"❌ *Format username tidak valid!*\n\n"
            f"Aturan Telegram:\n"
            f"• Panjang 5–32 karakter\n"
            f"• Hanya huruf, angka, dan underscore (_)\n"
            f"• Tidak boleh double underscore (__)\n\n"
            f"Username kamu: `{username}`",
            parse_mode="Markdown",
        )
        return

    pesan = await update.message.reply_text(
        f"🔍 Mengecek `@{username}`...", parse_mode="Markdown"
    )

    tersedia = cek_ketersediaan_username(username)

    if tersedia:
        await pesan.edit_text(
            f"✅ *Username Tersedia!*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Username: `@{username}`\n\n"
            f"Sepertinya masih kosong. Segera klaim!\n\n"
            f"🔗 Verifikasi:\n"
            f"https://t.me/{username}",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    else:
        await pesan.edit_text(
            f"❌ *Username Tidak Tersedia*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Username: `@{username}`\n\n"
            f"Sudah dipakai, invalid, atau reserved.\n\n"
            f"🔗 Lihat:\n"
            f"https://t.me/{username}",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )


@safe_handler
async def cari_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ *Format salah!*\n\n"
            "Gunakan: `/cari tema`\n"
            "Contoh: `/cari gaming`",
            parse_mode="Markdown",
        )
        return

    tema = " ".join(context.args).strip()
    if len(tema) > 30:
        tema = tema[:30]

    pesan = await update.message.reply_text(
        f"🔎 Mencari username bagus untuk tema *{tema}*...\n"
        f"Mohon tunggu sebentar ⏳",
        parse_mode="Markdown",
    )

    kandidat = generate_kandidat(tema, jumlah=MAX_KANDIDAT)
    tersedia_list = []
    terpakai_list = []

    for k in kandidat:
        try:
            if cek_ketersediaan_username(k):
                tersedia_list.append(k)
            else:
                terpakai_list.append(k)
        except Exception as e:
            logger.error(f"Error cek kandidat {k}: {e}")
        time.sleep(DELAY_BETWEEN_CHECK)

    hasil = f"📋 *Hasil Pencarian untuk '{tema}'*\n"
    hasil += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if tersedia_list:
        hasil += f"✅ *Tersedia ({len(tersedia_list)}):*\n"
        for u in tersedia_list:
            hasil += f"• `@{u}`\n"
        hasil += "\n"
    else:
        hasil += "😔 Tidak ada username tersedia dari kandidat ini.\n\n"

    if terpakai_list:
        hasil += f"❌ *Sudah Dipakai ({len(terpakai_list)}):*\n"
        for u in terpakai_list[:5]:
            hasil += f"• `@{u}`\n"
        if len(terpakai_list) > 5:
            hasil += f"• _...dan {len(terpakai_list) - 5} lainnya_\n"
        hasil += "\n"

    hasil += "💡 *Tips:* Gunakan `/cek <username>` untuk verifikasi individual."

    await pesan.edit_text(
        hasil, parse_mode="Markdown", disable_web_page_preview=True
    )


@safe_handler
async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pesan = await update.message.reply_text(
        "🎲 Generate username random...\n⏳ Mohon tunggu"
    )

    kandidat = generate_kandidat("", jumlah=8)
    tersedia = []

    for k in kandidat:
        try:
            if cek_ketersediaan_username(k):
                tersedia.append(k)
        except Exception as e:
            logger.error(f"Error cek random {k}: {e}")
        time.sleep(DELAY_BETWEEN_CHECK)

    if tersedia:
        hasil = (
            "✅ *Username Random Tersedia:*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        for u in tersedia:
            hasil += f"• `@{u}`\n"
        hasil += "\n💡 Segera klaim sebelum diambil orang lain!"
    else:
        hasil = (
            "😔 *Tidak ada username random yang tersedia saat ini.*\n\n"
            "Coba lagi nanti ya!"
        )

    await pesan.edit_text(
        hasil, parse_mode="Markdown", disable_web_page_preview=True
    )


@safe_handler
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ Perintah tidak dikenal.\n\n"
        "Gunakan /help untuk melihat daftar perintah.",
        parse_mode="Markdown",
    )


@safe_handler
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text.startswith("@") or is_valid_format(text.lstrip("@")):
        context.args = [text.lstrip("@")]
        await cek_command(update, context)
    else:
        await update.message.reply_text(
            "🤖 Saya bot pencari username.\n\n"
            "Gunakan /help untuk melihat perintah yang tersedia.",
            parse_mode="Markdown",
        )


# ============================================================
# ERROR HANDLER GLOBAL
# ============================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(
        f"Update {update} menyebabkan error: {context.error}",
        exc_info=context.error,
    )


# ============================================================
# FUNGSI JALANKAN BOT (di thread terpisah)
# ============================================================
def run_bot():
    """Jalankan bot Telegram di thread terpisah."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN tidak ada! Bot tidak bisa jalan.")
        return

    logger.info("🚀 Menghubungkan ke Telegram...")

    try:
        # Buat event loop baru untuk thread ini
        asyncio.set_event_loop(asyncio.new_event_loop())

        application = Application.builder().token(BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("cek", cek_command))
        application.add_handler(CommandHandler("cari", cari_command))
        application.add_handler(CommandHandler("random", random_command))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
        )
        application.add_handler(
            MessageHandler(filters.COMMAND, unknown_command)
        )
        application.add_error_handler(error_handler)

        logger.info("✅ Bot Telegram berjalan!")

        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )

    except Exception as e:
        logger.exception(f"❌ Bot error: {e}")


# ============================================================
# MAIN
# ============================================================
def main():
    logger.info("=" * 60)
    logger.info("  🤖 USERNAME HUNTER BOT (Render Edition)")
    logger.info("=" * 60)
    logger.info(f"  Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Jalankan bot di background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Jalankan Flask untuk Render
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐 Flask web server jalan di port {port}")
    logger.info("=" * 60)

    flask_app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
