import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from config import ADMIN_IDS, BOT_TOKEN
from database import Database

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()

# Conversation states
WAITING_PAYMENT_PROOF = 1
WAITING_CONFIG = 2

# ─────────────────── Plans ───────────────────
PLANS = {
    "plan_1m": {"name": "۱ ماهه", "price": 80_000, "days": 30},
    "plan_3m": {"name": "۳ ماهه", "price": 220_000, "days": 90},
    "plan_6m": {"name": "۶ ماهه", "price": 400_000, "days": 180},
}

CARD_NUMBER = "6037-XXXX-XXXX-XXXX"  # شماره کارت خودت رو بذار
CARD_OWNER  = "نام صاحب کارت"


# ─────────────────── /start ───────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username or "", user.full_name)

    keyboard = [
        [InlineKeyboardButton("🛒 خرید VPN", callback_data="buy")],
        [InlineKeyboardButton("👤 اکانت من", callback_data="my_account")],
        [InlineKeyboardButton("📋 پلن‌ها و قیمت‌ها", callback_data="plans")],
        [InlineKeyboardButton("🎧 پشتیبانی", callback_data="support")],
    ]
    await update.message.reply_text(
        f"👋 سلام {user.first_name} عزیز!\n\n"
        "🔐 به ربات فروش VPN خوش اومدی.\n"
        "از منوی زیر انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─────────────────── Plans list ───────────────────
async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = "📋 *پلن‌های موجود:*\n\n"
    keyboard = []
    for plan_id, plan in PLANS.items():
        text += f"• {plan['name']}: {plan['price']:,} تومان\n"
        keyboard.append([InlineKeyboardButton(
            f"🛒 خرید {plan['name']} - {plan['price']:,} تومان",
            callback_data=f"buy_{plan_id}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])

    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(keyboard))


# ─────────────────── Buy flow ───────────────────
async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = []
    for plan_id, plan in PLANS.items():
        keyboard.append([InlineKeyboardButton(
            f"{plan['name']} — {plan['price']:,} تومان",
            callback_data=f"buy_{plan_id}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])

    await query.edit_message_text(
        "🛒 *خرید VPN*\n\nیه پلن انتخاب کن:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def buy_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan_id = query.data.replace("buy_", "")
    plan = PLANS.get(plan_id)
    if not plan:
        await query.answer("پلن یافت نشد!", show_alert=True)
        return ConversationHandler.END

    context.user_data["selected_plan"] = plan_id

    text = (
        f"💳 *روش پرداخت*\n\n"
        f"پلن انتخابی: *{plan['name']}*\n"
        f"مبلغ: *{plan['price']:,} تومان*\n\n"
        f"مبلغ را به شماره کارت زیر واریز کن:\n"
        f"`{CARD_NUMBER}`\n"
        f"به نام: {CARD_OWNER}\n\n"
        f"بعد از پرداخت، تصویر رسید رو اینجا ارسال کن 👇"
    )
    await query.edit_message_text(text, parse_mode="Markdown")
    return WAITING_PAYMENT_PROOF


async def receive_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    plan_id = context.user_data.get("selected_plan")
    plan = PLANS.get(plan_id, {})

    # Save order
    order_id = db.create_order(user.id, plan_id, plan.get("price", 0))

    # Forward to admins
    caption = (
        f"🔔 *سفارش جدید #{order_id}*\n\n"
        f"👤 کاربر: {user.full_name} (@{user.username or 'بدون یوزرنیم'})\n"
        f"🆔 User ID: `{user.id}`\n"
        f"📦 پلن: {plan.get('name', plan_id)}\n"
        f"💰 مبلغ: {plan.get('price', 0):,} تومان\n\n"
        f"برای تایید: /approve_{order_id}\n"
        f"برای رد: /reject_{order_id}"
    )

    for admin_id in ADMIN_IDS:
        try:
            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=update.message.photo[-1].file_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_document(
                    chat_id=admin_id,
                    document=update.message.document.file_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error sending to admin {admin_id}: {e}")

    await update.message.reply_text(
        f"✅ رسید پرداخت دریافت شد!\n\n"
        f"شماره سفارش: #{order_id}\n"
        f"در حال بررسی توسط ادمین... ⏳\n\n"
        f"بعد از تایید، کانفیگ VPN برات ارسال می‌شه."
    )
    return ConversationHandler.END


# ─────────────────── Admin: Approve/Reject ───────────────────
async def approve_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    order_id = int(context.args[0]) if context.args else None
    if not order_id:
        # Parse from command like /approve_123
        cmd = update.message.text
        order_id = int(cmd.split("_")[1])

    order = db.get_order(order_id)
    if not order:
        await update.message.reply_text("سفارش یافت نشد!")
        return

    db.update_order_status(order_id, "approved")

    await update.message.reply_text(
        f"✅ سفارش #{order_id} تایید شد.\n"
        f"حالا کانفیگ VPN رو ارسال کن.\n\n"
        f"User ID کاربر: `{order['user_id']}`\n"
        f"برای ارسال کانفیگ: /sendconfig_{order_id}",
        parse_mode="Markdown"
    )

    await context.bot.send_message(
        chat_id=order["user_id"],
        text=f"✅ *پرداخت شما تایید شد!*\n\n"
             f"شماره سفارش: #{order_id}\n"
             f"کانفیگ VPN به زودی ارسال می‌شه. ⏳",
        parse_mode="Markdown"
    )


async def reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    cmd = update.message.text
    order_id = int(cmd.split("_")[1])
    order = db.get_order(order_id)

    if not order:
        await update.message.reply_text("سفارش یافت نشد!")
        return

    db.update_order_status(order_id, "rejected")

    await context.bot.send_message(
        chat_id=order["user_id"],
        text=f"❌ *متاسفانه سفارش #{order_id} تایید نشد.*\n\n"
             f"اگه مشکلی داری با پشتیبانی در ارتباط باش.",
        parse_mode="Markdown"
    )
    await update.message.reply_text(f"سفارش #{order_id} رد شد.")


async def send_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin sends VPN config to user: /sendconfig_<order_id>"""
    if update.effective_user.id not in ADMIN_IDS:
        return

    cmd = update.message.text
    order_id = int(cmd.split("_")[1])
    order = db.get_order(order_id)

    if not order:
        await update.message.reply_text("سفارش یافت نشد!")
        return

    context.user_data["sending_config_for"] = order_id
    await update.message.reply_text(
        f"📤 کانفیگ VPN رو برای کاربر {order['user_id']} ارسال کن.\n"
        f"(متن یا فایل کانفیگ رو اینجا بفرست)"
    )
    return WAITING_CONFIG


async def forward_config_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END

    order_id = context.user_data.get("sending_config_for")
    order = db.get_order(order_id)
    plan = PLANS.get(order["plan_id"], {})

    header = (
        f"🎉 *کانفیگ VPN شما آماده‌ست!*\n\n"
        f"📦 پلن: {plan.get('name', '')}\n"
        f"📅 مدت اعتبار: {plan.get('days', 30)} روز\n\n"
        f"کانفیگ رو ایمپورت کن و لذت ببر! 🚀\n\n"
        f"⚠️ این کانفیگ فقط برای استفاده شخصی شماست."
    )

    await context.bot.send_message(chat_id=order["user_id"], text=header,
                                   parse_mode="Markdown")

    if update.message.text:
        await context.bot.send_message(chat_id=order["user_id"],
                                       text=f"`{update.message.text}`",
                                       parse_mode="Markdown")
    elif update.message.document:
        await context.bot.send_document(chat_id=order["user_id"],
                                        document=update.message.document.file_id)

    db.update_order_status(order_id, "delivered")
    db.set_user_subscription(order["user_id"], plan.get("days", 30))

    await update.message.reply_text(f"✅ کانفیگ به کاربر ارسال شد.")
    return ConversationHandler.END


# ─────────────────── My Account ───────────────────
async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    orders = db.get_user_orders(user_id)

    if user_data and user_data.get("sub_days_left", 0) > 0:
        sub_text = f"✅ اشتراک فعال: {user_data['sub_days_left']} روز مانده"
    else:
        sub_text = "❌ اشتراک فعال ندارید"

    orders_text = ""
    if orders:
        orders_text = "\n\n📋 *سفارش‌های اخیر:*\n"
        for o in orders[:5]:
            status_emoji = {"pending": "⏳", "approved": "✅",
                            "rejected": "❌", "delivered": "📦"}.get(o["status"], "❓")
            orders_text += f"{status_emoji} #{o['id']} — {PLANS.get(o['plan_id'], {}).get('name', o['plan_id'])}\n"

    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]
    await query.edit_message_text(
        f"👤 *اکانت شما*\n\n{sub_text}{orders_text}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─────────────────── Support ───────────────────
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]
    await query.edit_message_text(
        "🎧 *پشتیبانی*\n\n"
        "برای ارتباط با پشتیبانی:\n"
        "👤 @YourAdminUsername\n\n"  # یوزرنیم ادمین رو عوض کن
        "⏰ ساعات پاسخگویی: ۱۰ صبح تا ۱۲ شب",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─────────────────── Admin panel ───────────────────
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    stats = db.get_stats()
    keyboard = [
        [InlineKeyboardButton("📋 سفارش‌های در انتظار", callback_data="admin_pending")],
        [InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_users")],
    ]
    await update.message.reply_text(
        f"🔧 *پنل ادمین*\n\n"
        f"👥 کل کاربران: {stats['total_users']}\n"
        f"📦 کل سفارشات: {stats['total_orders']}\n"
        f"⏳ در انتظار تایید: {stats['pending_orders']}\n"
        f"✅ تحویل‌داده‌شده: {stats['delivered_orders']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🛒 خرید VPN", callback_data="buy")],
        [InlineKeyboardButton("👤 اکانت من", callback_data="my_account")],
        [InlineKeyboardButton("📋 پلن‌ها و قیمت‌ها", callback_data="plans")],
        [InlineKeyboardButton("🎧 پشتیبانی", callback_data="support")],
    ]
    await query.edit_message_text(
        "🏠 *منوی اصلی*\nیه گزینه انتخاب کن:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─────────────────── Main ───────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Buy conversation
    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_plan, pattern="^buy_plan_")],
        states={
            WAITING_PAYMENT_PROOF: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, receive_payment_proof)
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_user=True,
    )

    # Send config conversation (admin)
    config_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^/sendconfig_\d+$"), send_config)],
        states={
            WAITING_CONFIG: [
                MessageHandler(filters.TEXT | filters.Document.ALL, forward_config_to_user)
            ],
        },
        fallbacks=[],
        per_user=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(MessageHandler(filters.Regex(r"^/approve_\d+$"), approve_order))
    app.add_handler(MessageHandler(filters.Regex(r"^/reject_\d+$"), reject_order))

    app.add_handler(buy_conv)
    app.add_handler(config_conv)

    app.add_handler(CallbackQueryHandler(show_plans, pattern="^plans$"))
    app.add_handler(CallbackQueryHandler(buy_menu, pattern="^buy$"))
    app.add_handler(CallbackQueryHandler(buy_plan, pattern="^buy_plan_"))
    app.add_handler(CallbackQueryHandler(my_account, pattern="^my_account$"))
    app.add_handler(CallbackQueryHandler(support, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(back_main, pattern="^back_main$"))

    logger.info("Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
