import asyncio
import logging
import json
import os
import time

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не найден.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "arba_istambul_bot").replace("@", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6013591658"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@ARBA_ISTAMBUL_RESTAURANT")
WEBAPP_URL = os.getenv(
    "WEBAPP_URL",
    "https://tahirovdd-lang.github.io/arba-istambul-restaurant/?v=1"
)

session = AiohttpSession(timeout=90)

bot = Bot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher()

_last_start: dict[int, float] = {}
BTN_OPEN_MULTI = "Ochish • Открыть • Open"


def kb_webapp_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_OPEN_MULTI, web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Откройте приложение"
    )


def kb_channel_deeplink() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=BTN_OPEN_MULTI,
                url=f"https://t.me/{BOT_USERNAME}?startapp=menu"
            )
        ]]
    )


def welcome_text() -> str:
    return (
        "🇷🇺 Добро пожаловать в <b>ARBA ISTAMBUL RESTAURANT</b>! 👋\n"
        "Нажмите кнопку ниже, чтобы открыть приложение.\n\n"
        "🇺🇿 <b>ARBA ISTAMBUL RESTAURANT</b> ga xush kelibsiz! 👋\n"
        "Ilovani ochish uchun pastdagi tugmani bosing.\n\n"
        "🇬🇧 Welcome to <b>ARBA ISTAMBUL RESTAURANT</b>! 👋\n"
        "Tap the button below to open the app."
    )


def allow_start(user_id: int, ttl: float = 2.0) -> bool:
    now = time.time()
    prev = _last_start.get(user_id, 0.0)
    if now - prev < ttl:
        return False
    _last_start[user_id] = now
    return True


@dp.message(CommandStart())
async def start(message: types.Message):
    logging.info(f"/start received from {message.from_user.id}")

    if not allow_start(message.from_user.id):
        return

    await message.answer(
        welcome_text(),
        reply_markup=kb_webapp_reply()
    )


@dp.message(Command("startapp"))
async def startapp(message: types.Message):
    logging.info(f"/startapp received from {message.from_user.id}")

    if not allow_start(message.from_user.id):
        return

    await message.answer(
        welcome_text(),
        reply_markup=kb_webapp_reply()
    )


@dp.message(Command("post_menu"))
async def post_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔️ Нет доступа.")
        return

    text = (
        "🇷🇺 <b>ARBA ISTAMBUL RESTAURANT</b>\n"
        "Нажмите кнопку ниже, чтобы открыть меню.\n\n"
        "🇺🇿 <b>ARBA ISTAMBUL RESTAURANT</b>\n"
        "Pastdagi tugma orqali menyuni oching.\n\n"
        "🇬🇧 <b>ARBA ISTAMBUL RESTAURANT</b>\n"
        "Tap the button below to open the menu."
    )

    try:
        sent = await bot.send_message(
            CHANNEL_ID,
            text,
            reply_markup=kb_channel_deeplink()
        )

        try:
            await bot.pin_chat_message(
                CHANNEL_ID,
                sent.message_id,
                disable_notification=True
            )
            await message.answer("✅ Пост отправлен в канал и закреплён.")
        except Exception:
            await message.answer(
                "✅ Пост отправлен в канал.\n"
                "⚠️ Не удалось закрепить — дай боту право «Закреплять сообщения»."
            )

    except Exception as e:
        logging.exception("CHANNEL POST ERROR")
        await message.answer(f"❌ Ошибка отправки в канал: <code>{e}</code>")


def fmt_sum(n: int) -> str:
    try:
        n = int(n)
    except Exception:
        n = 0
    return f"{n:,}".replace(",", " ")


def tg_label(u: types.User) -> str:
    return f"@{u.username}" if u.username else u.full_name


def clean_str(v) -> str:
    return ("" if v is None else str(v)).strip()


def safe_int(v, default=0) -> int:
    try:
        if v is None or isinstance(v, bool):
            return default
        if isinstance(v, (int, float)):
            return int(v)

        s = str(v).strip().replace(" ", "")
        if not s:
            return default

        return int(float(s))
    except Exception:
        return default


def build_order_lines(data: dict) -> list[str]:
    raw_items = data.get("items")
    lines: list[str] = []

    if isinstance(raw_items, list):
        for it in raw_items:
            if not isinstance(it, dict):
                continue

            name = (
                clean_str(it.get("name_lang"))
                or clean_str(it.get("name_ru"))
                or clean_str(it.get("name"))
                or clean_str(it.get("id"))
                or "—"
            )

            qty = safe_int(it.get("qty"), 0)
            price = safe_int(it.get("price"), 0)

            if qty <= 0:
                continue

            if price > 0:
                lines.append(f"• {name} × {qty} = {fmt_sum(price * qty)} сум")
            else:
                lines.append(f"• {name} × {qty}")

    return lines if lines else ["⚠️ Корзина пустая"]


@dp.message(F.web_app_data)
async def webapp_data(message: types.Message):
    raw = message.web_app_data.data

    await message.answer("✅ <b>Получил заказ.</b> Обрабатываю…")

    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        logging.exception("WEBAPP JSON ERROR")
        data = {}

    lines = build_order_lines(data)

    total_str = (
        clean_str(data.get("total_with_delivery"))
        or clean_str(data.get("total_items"))
        or clean_str(data.get("total"))
        or "0"
    )

    payment = clean_str(data.get("payment")) or "—"
    order_type = clean_str(data.get("type")) or "—"
    address = clean_str(data.get("address")) or "—"
    phone = clean_str(data.get("phone")) or "—"
    comment = clean_str(data.get("comment"))
    order_id = clean_str(data.get("order_id")) or "—"

    admin_text = (
        "🚨 <b>НОВЫЙ ЗАКАЗ ARBA ISTAMBUL RESTAURANT</b>\n"
        f"🆔 <b>{order_id}</b>\n\n"
        + "\n".join(lines)
        + f"\n\n💰 <b>Сумма:</b> {total_str} сум"
        + f"\n🚚 <b>Тип:</b> {order_type}"
        + f"\n💳 <b>Оплата:</b> {payment}"
        + f"\n📍 <b>Адрес:</b> {address}"
        + f"\n📞 <b>Телефон:</b> {phone}"
        + f"\n👤 <b>Telegram:</b> {tg_label(message.from_user)}"
    )

    if comment:
        admin_text += f"\n💬 <b>Комментарий:</b> {comment}"

    try:
        await bot.send_message(ADMIN_ID, admin_text)
    except Exception:
        logging.exception("ADMIN MESSAGE ERROR")

    await message.answer(
        "✅ <b>Ваш заказ принят!</b>\n"
        "🙏 Спасибо, мы скоро свяжемся с вами.",
        reply_markup=kb_webapp_reply()
    )


@dp.message()
async def any_message(message: types.Message):
    logging.info(f"ANY MESSAGE: {message.text}")

    await message.answer(
        "✅ Бот работает.\n"
        "Нажмите кнопку ниже, чтобы открыть приложение.",
        reply_markup=kb_webapp_reply()
    )


async def safe_delete_webhook():
    for i in range(10):
        try:
            await bot.delete_webhook(
                drop_pending_updates=True,
                request_timeout=90
            )
            logging.info("Webhook deleted successfully")
            return True
        except Exception as e:
            logging.warning(f"delete_webhook retry {i + 1}/10 failed: {e}")
            await asyncio.sleep(5)

    return False


async def start_polling_forever():
    while True:
        try:
            logging.info("Starting polling...")
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                polling_timeout=60
            )
        except Exception as e:
            logging.exception(f"Polling crashed: {e}")
            await asyncio.sleep(10)


async def main():
    try:
        try:
            me = await bot.get_me(request_timeout=90)
            logging.info(f"BOT CONNECTED: @{me.username} | id={me.id}")
        except Exception as e:
            logging.warning(f"get_me failed, but bot will continue: {e}")

        await safe_delete_webhook()

        logging.info("Bot started successfully")
        await start_polling_forever()

    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
