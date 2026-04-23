from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from database import Base, User, Service, UserServices, Payment, Ticket, Settings, Reseller
from config import get_settings
from xui_api import XuiAPI
import qrcode
from io import BytesIO
import datetime, random, string

settings = get_settings()
engine = create_engine(settings.DATABASE_URL)
router = Router()

def get_db():
    return Session(engine)

def is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_ID

# --- States ---
class BuyState(StatesGroup):
    waiting_for_tracking = State()
class AdminState(StatesGroup):
    waiting_for_server_details = State()
    waiting_for_service_details = State()
    waiting_for_broadcast = State()
class SupportState(StatesGroup):
    waiting_for_ticket_text = State()

# --- Helper Functions ---
def gen_uuid():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def gen_sub_link(server_url, uuid):
    return f"{server_url}/sub/{uuid}"

def generate_qr(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

def get_setting(key):
    db = get_db()
    s = db.query(Settings).filter(Settings.key == key).first()
    db.close()
    return s.value if s else None

# --- User Handlers ---
@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    db = get_db()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user:
        # سیستم زیرمجموعه‌گیری
        args = message.text.split()
        inviter = None
        if len(args) > 1 and args[1].isdigit():
            inviter_id = int(args[1])
            if inviter_id != message.from_user.id:
                inviter = db.query(User).filter(User.telegram_id == inviter_id).first()
                if inviter:
                    # شارژ کیف پول دعوت کننده (مثلا 10 هزار تومان)
                    inviter.wallet += 10000 
        
        user = User(telegram_id=message.from_user.id, username=message.from_user.username, invited_by=inviter_id if inviter else None)
        db.add(user)
        db.commit()

    # بررسی عضویت اجباری
    channel = get_setting("force_channel")
    if channel:
        try:
            member = await message.bot.get_chat_member(channel, message.from_user.id)
            if member.status not in ['member', 'administrator', 'creator']:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="عضویت در کانال", url=f"https://t.me/{channel.replace('@', '')}")],
                    [InlineKeyboardButton(text="✅ عضو شدم", callback_data="check_join")]
                ])
                await message.answer("برای استفاده از ربات ابتدا در کانال عضو شوید:", reply_markup=kb)
                db.close()
                return
        except:
            pass

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 خرید اشتراک", callback_data="buy_menu")],
        [InlineKeyboardButton(text="🔧 سرویس‌های من", callback_data="my_services"), InlineKeyboardButton(text="💰 کیف پول", callback_data="wallet_menu")],
        [InlineKeyboardButton(text="🎁 اکانت تست", callback_data="free_test")],
        [InlineKeyboardButton(text="💼 زیرمجموعه‌گیری", callback_data="affiliate"), InlineKeyboardButton(text="📚 آموزش‌ها", callback_data="tutorials")],
        [InlineKeyboardButton(text="🎧 ارتباط با پشتیبانی", callback_data="open_ticket")]
    ])
    await message.answer("به ربات DAC خوش آمدید. لطفا یکی از گزینه‌ها را انتخاب کنید:", reply_markup=kb)
    db.close()

@router.callback_query(F.data == "check_join")
async def check_join(callback: CallbackQuery):
    channel = get_setting("force_channel")
    member = await callback.bot.get_chat_member(channel, callback.from_user.id)
    if member.status in ['member', 'administrator', 'creator']:
        await callback.message.delete()
        await start_cmd(callback.message, callback.bot.fsm.get_context(callback))
    else:
        await callback.answer("شما هنوز عضو کانال نشده‌اید!", show_alert=True)

@router.callback_query(F.data == "buy_menu")
async def buy_menu(callback: CallbackQuery):
    sale_status = get_setting("sale_status")
    if sale_status == "inactive":
        await callback.answer("فروش در حال حاضر غیرفعال است.", show_alert=True)
        return
    db = get_db()
    categories = db.query(Service.category).distinct().all()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[0]}")] for cat in categories
    ])
    await callback.message.edit_text("دسته بندی را انتخاب کنید:", reply_markup=kb)
    db.close()

@router.callback_query(F.data.startswith("cat_"))
async def show_services(callback: CallbackQuery):
    cat = callback.data.split("_", 1)[1]
    db = get_db()
    services = db.query(Service).filter(Service.category == cat, Service.is_active == True).all()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{s.name} | {s.days} روز - {s.traffic_gb} گیگ | {int(s.price_toman)} تومان", callback_data=f"srv_{s.id}")] for s in services
    ] + [[InlineKeyboardButton(text="بازگشت", callback_data="buy_menu")]])
    await callback.message.edit_text("سرویس مورد نظر را انتخاب کنید:", reply_markup=kb)
    db.close()

@router.callback_query(F.data.startswith("srv_"))
async def process_service(callback: CallbackQuery, state: FSMContext):
    srv_id = int(callback.data.split("_")[1])
    db = get_db()
    srv = db.query(Service).filter(Service.id == srv_id).first()
    await state.update_data(selected_service=srv_id, amount=srv.price_toman)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 کارت به کارت", callback_data=f"pay_card_{srv.price_toman}")],
        [InlineKeyboardButton(text="₿ ارز دیجیتال", callback_data=f"pay_crypto_{srv.price_crypto}")],
        [InlineKeyboardButton(text="💰 پرداخت از کیف پول", callback_data="pay_wallet")]
    ])
    await callback.message.edit_text(f"پرداخت مبلغ: {int(srv.price_toman)} تومان\nروش پرداخت را انتخاب کنید:", reply_markup=kb)
    db.close()

@router.callback_query(F.data.startswith("pay_card_"))
async def card_payment(callback: CallbackQuery, state: FSMContext):
    amount = callback.data.split("_")[2]
    card = get_setting("card_number") or "6037XXXXXXXXXXXX"
    await state.update_data(currency="toman")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ واریز انجام شد", callback_data="paid_done")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="buy_menu")]
    ])
    await callback.message.edit_text(f"مبلغ: {amount} تومان\nشماره کارت: {card}\nبه نام:DAC Store\nپس از واریز دکمه سبز را بزنید:", reply_markup=kb)

@router.callback_query(F.data == "paid_done")
async def paid_done(callback: CallbackQuery, state: FSMContext):
    await BuyState.waiting_for_tracking.set()
    await callback.message.edit_text("شناسه پرداخت یا کد رهگیری خود را ارسال کنید:")
    await state.set_state(BuyState.waiting_for_tracking)

@router.message(BuyState.waiting_for_tracking)
async def save_tracking(message: Message, state: FSMContext):
    data = await state.get_data()
    db = get_db()
    pay = Payment(user_telegram_id=message.from_user.id, amount=data['amount'], currency=data['currency'], tracking_code=message.text)
    db.add(pay)
    db.commit()
    
    # اطلاع به ادمین
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید و ساخت اکانت", callback_data=f"approve_pay_{pay.id}")],
        [InlineKeyboardButton(text="❌ رد درخواست", callback_data=f"reject_pay_{pay.id}")]
    ])
    await message.bot.send_message(settings.ADMIN_ID, f"درخواست پرداخت جدید:\nمبلغ: {data['amount']}\nشناسه: {message.text}", reply_markup=kb)
    await message.answer("درخواست شما برای ادمین ارسال شد. پس از تایید، اکانت برای شما ارسال می‌شود.")
    await state.clear()
    db.close()

# --- Admin Handlers ---
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 وضعیت فروش", callback_data="admin_toggle_sale")],
        [InlineKeyboardButton(text="🖥 اضافه کردن سرور", callback_data="admin_add_server")],
        [InlineKeyboardButton(text="📦 اضافه کردن سرویس", callback_data="admin_add_service")],
        [InlineKeyboardButton(text="🎫 مدیریت کد تخفیف", callback_data="admin_discount")],
        [InlineKeyboardButton(text="📢 پیام همگانی", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📚 مدیریت آموزش‌ها", callback_data="admin_tutorial")],
        [InlineKeyboardButton(text="⚙ تنظیمات (کانال اجباری/شماره کارت)", callback_data="admin_settings")],
        [InlineKeyboardButton(text="👥 مدیریت نمایندگان", callback_data="admin_resellers")],
        [InlineKeyboardButton(text="📩 تیکت‌های باز", callback_data="admin_tickets")]
    ])
    await message.answer("پنل مدیریت DAC:", reply_markup=kb)

@router.callback_query(F.data == "admin_toggle_sale")
async def toggle_sale(callback: CallbackQuery):
    db = get_db()
    current = get_setting("sale_status")
    new_val = "inactive" if current == "active" else "active"
    s = db.query(Settings).filter(Settings.key == "sale_status").first()
    if not s:
        s = Settings(key="sale_status", value=new_val)
        db.add(s)
    else:
        s.value = new_val
    db.commit()
    await callback.answer(f"فروش {'فعال' if new_val == 'active' else 'غیرفعال'} شد.", show_alert=True)
    db.close()

@router.callback_query(F.data == "admin_add_server")
async def add_server_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("اطلاعات سرور را به این شکل ارسال کنید:\nنام | نوع(local/remote) | آدرس پنل | یوزرنیم | پسورد\n\nمثال:\nسرور ایران | local | http://127.0.0.1:54321 | admin | 1234")
    await state.set_state(AdminState.waiting_for_server_details)

@router.message(AdminState.waiting_for_server_details)
async def save_server(message: Message, state: FSMContext):
    parts = message.text.split(" | ")
    if len(parts) != 5: return await message.answer("فرمت اشتباه است.")
    db = get_db()
    srv = Server(name=parts[0], type=parts[1], panel_url=parts[2], panel_user=parts[3], panel_pass=parts[4])
    db.add(srv)
    db.commit()
    await message.answer("سرور با موفقیت اضافه شد.")
    await state.clear()
    db.close()

@router.callback_query(F.data == "admin_add_service")
async def add_service_prompt(callback: CallbackQuery, state: FSMContext):
    db = get_db()
    inbounds = db.query(Inbound).all()
    if not inbounds: return await callback.answer("ابتدا یک سرور و اینباند اضافه کنید!", show_alert=True)
    txt = "اطلاعات سرویس را ارسال کنید (دستی/خودکار با عبارت manual/auto مشخص کنید):\n"
    txt += "دسته‌بندی | نام | روز | ترافیک(گیگ) | قیمت تومان | قیمت Represent | قیمت ارز | نوع(auto/manual) | آیدی اینباند\n"
    txt += "مثال:\nویژه | یک ماهه | 30 | 50 | 150000 | 120000 | 3 | auto | 1"
    await callback.message.answer(txt)
    await state.set_state(AdminState.waiting_for_service_details)

@router.message(AdminState.waiting_for_service_details)
async def save_service(message: Message, state: FSMContext):
    try:
        parts = message.text.split(" | ")
        db = get_db()
        srv = Service(category=parts[0], name=parts[1], days=int(parts[2]), traffic_gb=float(parts[3]), 
                      price_toman=float(parts[4]), reseller_price=float(parts[5]), price_crypto=float(parts[6]),
                      is_manual=(parts[7]=="manual"), inbound_id=int(parts[8]))
        db.add(srv)
        db.commit()
        await message.answer("سرویس با موفقیت اضافه شد.")
    except:
        await message.answer("خطا در فرمت.")
    await state.clear()

# تایید پرداخت و ساخت خودکار اکانت توسط ادمین
@router.callback_query(F.data.startswith("approve_pay_"))
async def approve_payment(callback: CallbackQuery):
    pay_id = int(callback.data.split("_")[2])
    db = get_db()
    pay = db.query(Payment).filter(Payment.id == pay_id).first()
    pay.status = "approved"
    
    # اینجا باید لاجیک ساخت اکانت از طریق xui_api قرار بگیرد
    # برای نمونه یک لینک ساختگی میفرستیم
    fake_uuid = gen_uuid()
    sub_link = f"https://sub.dac.ir/{fake_uuid}"
    
    usr_srv = UserServices(user_telegram_id=pay.user_telegram_id, service_id=1, uuid=fake_uuid, sub_link=sub_link, expire_date=datetime.datetime.now() + datetime.timedelta(days=30), traffic_limit=50)
    db.add(usr_srv)
    db.commit()
    
    # ارسال کانفیگ + QR کد به کاربر
    qr = generate_qr(sub_link)
    await callback.bot.send_photo(pay.user_telegram_id, qr, caption=f"✅ پرداخت شما تایید شد.\n\n🔗 لینک اشتراک:\n{sub_link}\n🔗 لینک اتصال:\nvless://{fake_uuid}@127.0.0.1:443?type=tcp&security=tls#DAC")
    
    await callback.message.edit_text("✅ تایید شد و اکانت ارسال گردید.")
    db.close()

@router.callback_query(F.data.startswith("reject_pay_"))
async def reject_payment(callback: CallbackQuery):
    pay_id = int(callback.data.split("_")[2])
    db = get_db()
    pay = db.query(Payment).filter(Payment.id == pay_id).first()
    pay.status = "rejected"
    db.commit()
    await callback.bot.send_message(pay.user_telegram_id, "❌ پرداخت شما رد شد. لطفا مجددا تلاش کنید یا به پشتیبانی پیام دهید.")
    await callback.message.edit_text("❌ رد شد.")
    db.close()

# --- Support System ---
@router.callback_query(F.data == "open_ticket")
async def open_ticket(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("متن پیام خود را برای پشتیبانی بنویسید:")
    await state.set_state(SupportState.waiting_for_ticket_text)

@router.message(SupportState.waiting_for_ticket_text)
async def save_ticket(message: Message, state: FSMContext):
    db = get_db()
    ticket = Ticket(user_telegram_id=message.from_user.id, text=message.text)
    db.add(ticket)
    db.commit()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="پاسخ به این تیکت", callback_data=f"reply_ticket_{ticket.id}")]
    ])
    await message.bot.send_message(settings.ADMIN_ID, f"تیکت جدید از {message.from_user.id}:\n{message.text}", reply_markup=kb)
    await message.answer("تیکت شما ثبت شد و در اسرع وقت پاسخ داده می‌شود.")
    await state.clear()
    db.close()

@router.callback_query(F.data.startswith("reply_ticket_"))
async def reply_ticket_prompt(callback: CallbackQuery, state: FSMContext):
    await state.update_data(ticket_id=int(callback.data.split("_")[2]), user_id=callback.message.text.split(" ")[2]) # استخراج آیدی یوزر ساده شده
    await callback.message.answer("پاسخ خود را ارسال کنید:")
    await state.set_state(AdminState.waiting_for_broadcast) # استفاده موقت از استیت

# --- Free Test Account ---
@router.callback_query(F.data == "free_test")
async def free_test(callback: CallbackQuery):
    db = get_db()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    if user.is_test_used:
        return await callback.answer("شما قبلا از تست رایگان استفاده کرده‌اید.", show_alert=True)
    
    user.is_test_used = True
    db.commit()
    await callback.message.answer("🎁 اکانت تست ۱ روزه ۱ گیگابایتی برای شما ساخته شد.\nلینک: ...")
    db.close()

# --- Reseller System (ساختار پایه) ---
@router.message(Command("reseller"))
async def reseller_panel(message: Message):
    db = get_db()
    res = db.query(Reseller).filter(Reseller.telegram_id == message.from_user.id).first()
    if not res: return await message.answer("شما دسترسی نمایندگی ندارید.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 موجودی کیف پول", callback_data="res_wallet")],
        [InlineKeyboardButton(text="🛒 فروش سرویس", callback_data="buy_menu")] # نماینده هم از منوی خرید استفاده میکند اما قیمت متفاوت محاسبه میشود
    ])
    await message.answer(f"پنل نماینده DAC\nموجودی: {res.wallet} تومان", reply_markup=kb)
    db.close()
