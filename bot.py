import sqlite3
import secrets
from datetime import datetime, timedelta
import pytz
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = "8223437382:AAHRKPjLVD0ik_ijtoMrN8YwoNMZErPVccs"
# لیست ادمین‌ها (هر دو شناسه دسترسی کامل دارند)
ADMIN_IDS = [8423995337, 7615795494]
CHANNEL_USERNAME = "@eclissekai"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# تنظیم تایم‌زون تهران
TEHRAN_TZ = pytz.timezone("Asia/Tehran")

# اتصال به دیتابیس
conn = sqlite3.connect("tarot_database.db", check_same_thread=False)
cursor = conn.cursor()

# جدول کاربران
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    last_tarot_date TEXT
)
""")

# جدول کارت‌ها
cursor.execute("""
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT,
    normal_text TEXT,
    reversed_text TEXT
)
""")
conn.commit()

class AdminStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_normal_text = State()
    waiting_for_reversed_text = State()

async def check_channel_member(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# تابع فرستادن فال روزانه بدون دکمه با ریپلای روی عکس
async def send_tarot_to_user(user_id: int):
    if not await check_channel_member(user_id):
        return False

    cursor.execute("SELECT file_id, normal_text, reversed_text FROM cards")
    all_cards = cursor.fetchall()
    if not all_cards:
        return False

    chosen_card = secrets.choice(all_cards)
    file_id, normal_text, reversed_text = chosen_card

    if (secrets.randbelow(100) + 1) <= 20:
        title = "🔄 کارت معکوس (وارونه)"
        text = reversed_text
    else:
        title = "✨ کارت صاف (عادی)"
        text = normal_text

    try:
        photo_msg = await bot.send_photo(chat_id=user_id, photo=file_id)
        await bot.send_message(
            chat_id=user_id,
            text=f"🔮 <b>فال امروز شما</b>\n\n<b>{title}</b>\n\n{text}",
            parse_mode="HTML",
            reply_to_message_id=photo_msg.message_id
        )
        return True
    except Exception:
        return False

# ارسال خودکار راس ساعت ۰۰:۰۰ به وقت تهران
async def daily_auto_send():
    today_tehran = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")
    cursor.execute("SELECT user_id FROM users")
    all_users = cursor.fetchall()
    
    for row in all_users:
        user_id = row[0]
        success = await send_tarot_to_user(user_id)
        if success:
            cursor.execute("INSERT OR REPLACE INTO users (user_id, last_tarot_date) VALUES (?, ?)", (user_id, today_tehran))
            conn.commit()

def check_join_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")
    builder.button(text="✅ عضو شدم! دریافت فال امروز", callback_data="check_membership")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    now_tehran = datetime.now(TEHRAN_TZ)
    today_tehran = now_tehran.strftime("%Y-%m-%d")
    
    cursor.execute("INSERT OR IGNORE INTO users (user_id, last_tarot_date) VALUES (?, '')", (user_id,))
    conn.commit()

    if not await check_channel_member(user_id):
        await message.answer(
            f"✨ به ربات تاروت کبیر خوش آمدید.\n\n"
            f"برای فعال‌سازی ربات و دیدن تغییر روزانه فال‌ها، ابتدا باید عضو کانال {CHANNEL_USERNAME} شوید و سپس دکمه زیر را بزنید:",
            reply_markup=check_join_keyboard()
        )
        return

    cursor.execute("SELECT last_tarot_date FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row and row[0] == today_tehran:
        try:
            tomorrow = (now_tehran + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            remaining = tomorrow - now_tehran
            hours, remainder = divmod(remaining.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            await message.answer(
                f"✅ ربات برای شما فعال است.\n"
                f"فال روزانه بعدی شما دقیقاً {hours} ساعت و {minutes} دقیقه دیگر (رأس ساعت ۰۰:۰۰ بامداد به وقت تهران) به صورت خودکار ارسال می‌شود. 🌙"
            )
        except Exception:
            await message.answer("✅ ربات برای شما فعال است. فال روزانه بعدی شما رأس ساعت ۰۰:۰۰ بامداد به وقت تهران به صورت خودکار ارسال می‌شود. 🌙")
    else:
        await message.answer("🔮 در حال آماده‌سازی فال امروز شما...")
        success = await send_tarot_to_user(user_id)
        if success:
            cursor.execute("INSERT OR REPLACE INTO users (user_id, last_tarot_date) VALUES (?, ?)", (user_id, today_tehran))
            conn.commit()

@dp.callback_query(F.data == "check_membership")
async def process_check_membership(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    today_tehran = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")
    
    if not await check_channel_member(user_id):
        await callback.answer("❌ شما هنوز عضو کانال نشده‌اید یا لفت داده‌اید!", show_alert=True)
        return

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer("🔮 عضویت تایید شد! در حال آماده‌سازی فال امروز شما...")
    
    success = await send_tarot_to_user(user_id)
    if success:
        cursor.execute("INSERT OR REPLACE INTO users (user_id, last_tarot_date) VALUES (?, ?)", (user_id, today_tehran))
        conn.commit()
    else:
        await callback.message.answer("⚠️ مشکلی در ارسال فال پیش آمد. لطفاً مطمئن شوید ربات در کانال ادمین است و کارت‌ها ثبت شده‌اند.")
    await callback.answer()

# --- پنل ادمین ---
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    cursor.execute("SELECT id FROM cards")
    cards = cursor.fetchall()
    builder = InlineKeyboardBuilder()
    builder.button(text="📥 افزودن کارت جدید", callback_data="admin_add_card")
    for c in cards:
        builder.button(text=f"❌ حذف کارت {c[0]}", callback_data=f"admin_del_{c[0]}")
    builder.adjust(1)
    await message.answer("✨ پنل مدیریت:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "admin_add_card")
async def add_card_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await callback.message.answer("📸 عکس کارت را بفرستید:")
    await state.set_state(AdminStates.waiting_for_photo)
    await callback.answer()

@dp.message(AdminStates.waiting_for_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    await state.update_data(file_id=message.photo[-1].file_id)
    await message.reply("✍️ متن مثبت (عادی):")
    await state.set_state(AdminStates.waiting_for_normal_text)

@dp.message(AdminStates.waiting_for_normal_text)
async def process_normal_text(message: types.Message, state: FSMContext):
    await state.update_data(normal_text=message.text)
    await message.reply("✍️ متن منفی (معکوس ۲۰٪):")
    await state.set_state(AdminStates.waiting_for_reversed_text)

@dp.message(AdminStates.waiting_for_reversed_text)
async def process_reversed_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute("INSERT INTO cards (file_id, normal_text, reversed_text) VALUES (?, ?, ?)", (data['file_id'], data['normal_text'], message.text))
    conn.commit()
    await message.reply("🎉 کارت ثبت شد!")
    await state.clear()

@dp.callback_query(F.data.startswith("admin_del_"))
async def delete_card(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    card_id = int(callback.data.split("_")[2])
    cursor.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    conn.commit()
    await callback.message.answer(f"🗑 کارت {card_id} حذف شد.")
    await callback.answer()

async def main():
    scheduler = AsyncIOScheduler(timezone=TEHRAN_TZ)
    scheduler.add_job(daily_auto_send, "cron", hour=0, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
