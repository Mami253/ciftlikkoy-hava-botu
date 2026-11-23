from datetime import datetime, time
import json
import os
from pathlib import Path
import urllib.request
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.environ["BOT_TOKEN"]

# Yalova Çiftlikköy koordinatları
LAT = 40.656
LON = 29.315
TZ = ZoneInfo("Europe/Istanbul")

MAX_DAYS = 3
STATE_FILE = Path(__file__).with_name("state.json")


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return {
                "chat_id": data.get("chat_id"),
                "sent_days": int(data.get("sent_days", 0)),
            }
        except Exception:
            pass
    return {"chat_id": None, "sent_days": 0}


def save_state(chat_id: int | None, sent_days: int) -> None:
    payload = {"chat_id": chat_id, "sent_days": sent_days}
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


STATE = load_state()


def set_chat_id(chat_id: int) -> None:
    if STATE["chat_id"] != chat_id:
        STATE["chat_id"] = chat_id
        save_state(STATE["chat_id"], STATE["sent_days"])


def get_ciftlikkoy_weather() -> str:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&current=temperature_2m,apparent_temperature,wind_speed_10m,weather_code"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&timezone=Europe%2FIstanbul&forecast_days=1"
    )
    with urllib.request.urlopen(url, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))

    current = data.get("current", {})
    daily = data.get("daily", {})

    temp = current.get("temperature_2m", "-")
    feels = current.get("apparent_temperature", "-")
    wind = current.get("wind_speed_10m", "-")
    max_t = daily.get("temperature_2m_max", ["-"])[0]
    min_t = daily.get("temperature_2m_min", ["-"])[0]
    rain_prob = daily.get("precipitation_probability_max", ["-"])[0]

    bugun = datetime.now(TZ).strftime("%d.%m.%Y")
    return (
        f"🌤️ Yalova Çiftlikköy Hava Durumu ({bugun})\n\n"
        f"• Anlık Sıcaklık: {temp}°C (Hissedilen: {feels}°C)\n"
        f"• Gün İçi En Yüksek / En Düşük: {max_t}°C / {min_t}°C\n"
        f"• Yağış İhtimali: %{rain_prob}\n"
        f"• Rüzgar Hızı: {wind} km/s"
    )


async def daily_weather_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = STATE["chat_id"]
    sent_days = STATE["sent_days"]

    if chat_id is None:
        return

    if sent_days >= MAX_DAYS:
        if context.job:
            context.job.schedule_removal()
        return

    try:
        mesaj = get_ciftlikkoy_weather()
        await context.bot.send_message(chat_id=chat_id, text=mesaj)
        STATE["sent_days"] = sent_days + 1
        save_state(STATE["chat_id"], STATE["sent_days"])
    except Exception as exc:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Hava durumu alınırken bir hata oluştu: {exc}",
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        set_chat_id(update.message.chat_id)
        await update.message.reply_text(
            "Selam! Sohbet kaydın alındı.\n"
            "3 gün boyunca her gün saat 12:30'da Yalova Çiftlikköy hava durumunu göndereceğim.\n"
            "İstersen hemen test etmek için /hava veya hava yazabilirsin."
        )


async def hava(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        set_chat_id(update.message.chat_id)
        await update.message.reply_text("Çiftlikköy hava durumu kontrol ediliyor...")
        try:
            mesaj = get_ciftlikkoy_weather()
            await update.message.reply_text(mesaj)
        except Exception as exc:
            await update.message.reply_text(f"Hava durumu alınamadı: {exc}")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message and update.message.text:
        set_chat_id(update.message.chat_id)
        temiz_metin = update.message.text.strip().lower()

        if temiz_metin in {"hava", "hava durumu"}:
            await update.message.reply_text("Çiftlikköy hava durumu kontrol ediliyor...")
            try:
                mesaj = get_ciftlikkoy_weather()
                await update.message.reply_text(mesaj)
            except Exception as exc:
                await update.message.reply_text(f"Hava durumu alınamadı: {exc}")
            return

        await update.message.reply_text(f"Şunu yazdın: {update.message.text}")


def main() -> None:
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hava", hava))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    if app.job_queue is not None:
        app.job_queue.run_daily(
            daily_weather_job,
            time=time(hour=12, minute=30, second=0, tzinfo=TZ),
            name="ciftlikkoy_daily_weather",
        )

    print("Bot çalışıyor...")
    app.run_polling(timeout=30)


if __name__ == "__main__":
    main()