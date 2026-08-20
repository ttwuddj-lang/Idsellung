import asyncio, logging, os, re
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from motor.motor_asyncio import AsyncIOMotorClient

BOT_TOKEN=os.getenv('BOT_TOKEN','')
MONGO_URI=os.getenv('MONGO_URI','')
MONGO_DB=os.getenv('MONGO_DB','telegram_store')
ADMIN_IDS={int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}
UPI_ID=os.getenv('UPI_ID','yourupi@upi')
FORCE_CHANNEL='@jp_network'
FORCE_CHANNEL_URL='https://t.me/jp_network'
START_PHOTO='https://cdn.phototourl.com/free/2026-08-20-0e143e7d-9bff-42fa-bb3c-d62a2f00de4c.png'
DEPOSIT_WINDOW_MINUTES=30
if not BOT_TOKEN or not MONGO_URI or not ADMIN_IDS:
    raise RuntimeError('Set BOT_TOKEN, MONGO_URI and ADMIN_IDS')

bot=Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp=Dispatcher(); router=Router(); dp.include_router(router)
db=AsyncIOMotorClient(MONGO_URI)[MONGO_DB]
users, deposits, products, orders, support, settings=(db[x] for x in ('users','deposits','products','orders','support','settings'))


BOT_COMMANDS = [
    BotCommand(command="start", description="Start / Main Menu"),
    BotCommand(command="buy", description="Buy Products"),
    BotCommand(command="wallet", description="Wallet & Deposit"),
    BotCommand(command="orders", description="My Orders"),
    BotCommand(command="support", description="Support"),
    BotCommand(command="admin", description="Admin Panel"),
]


def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🛒 Buy Products',callback_data='products')],
        [InlineKeyboardButton(text='💰 Wallet / Deposit',callback_data='wallet')],
        [InlineKeyboardButton(text='📦 My Orders',callback_data='orders')],
        [InlineKeyboardButton(text='💬 Support (5 min)',callback_data='support')]
    ])


def wallet_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='➕ Deposit',callback_data='deposit')],
        [InlineKeyboardButton(text='🧾 Deposit History',callback_data='deposit_history')],
        [InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]
    ])


def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⚙️ Payment Settings',callback_data='admin:payment')],
        [InlineKeyboardButton(text='📋 Manage Products',callback_data='admin:products')],
        [InlineKeyboardButton(text='👤 Manage User Funds',callback_data='admin:users')]
    ])


def admin_payment_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💳 UPI ID',callback_data='ps:upi'),InlineKeyboardButton(text='📷 QR Code',callback_data='ps:qr')],
        [InlineKeyboardButton(text='💬 Payment Text',callback_data='ps:text')],
        [InlineKeyboardButton(text='💰 Minimum Deposit',callback_data='ps:min'),InlineKeyboardButton(text='💰 Maximum Deposit',callback_data='ps:max')],
        [InlineKeyboardButton(text='📋 View Settings',callback_data='ps:view')],
        [InlineKeyboardButton(text='⬅️ Admin Panel',callback_data='admin:home')]
    ])


async def get_payment_settings():
    p=await settings.find_one({'_id':'payment'})
    if not p:
        p={'_id':'payment','upi_id':UPI_ID,'qr_file_id':None,
           'instructions':'Pay using UPI/QR and send the payment screenshot here.',
           'min_deposit':1.0,'max_deposit':0.0}
        await settings.insert_one(p)
    return p


async def save_user(u):
    now=datetime.now(timezone.utc)
    await users.update_one(
        {'_id':u.id},
        {'$set':{'name':u.full_name,'username':u.username,'updated_at':now},
         '$setOnInsert':{'balance':0.0,'total_deposited':0.0,'created_at':now}},
        upsert=True)


def join_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📢 Join Channel',url=FORCE_CHANNEL_URL)],
        [InlineKeyboardButton(text='✅ I Joined — Verify',callback_data='verify_join')]
    ])


async def is_joined(user_id:int):
    try:
        member=await bot.get_chat_member(FORCE_CHANNEL,user_id)
        return member.status in ('member','administrator','creator')
    except Exception:
        return False


async def send_join_gate(m:Message):
    text=('👋 <b>Welcome to Waste Botz</b>\n\n'
          '📢 Please join our channel first to continue.\n'
          'After joining, tap <b>✅ I Joined — Verify</b>.')
    await m.answer_photo(START_PHOTO,caption=text,reply_markup=join_kb())


async def send_verified_start(m:Message):
    text=('🎉 <b>Waste Botz</b>\n\n'
          '✅ <b>Verification successful!</b>\n\n'
          '🛍️ <b>All-in-One Store &amp; Support Bot</b>\n'
          '💰 Wallet • 🛒 Products • 📦 Orders • 💬 Support\n\n'
          '📌 <b>Available Commands</b>\n'
          '• /start — Main Menu\n'
          '• /buy — Buy Products\n'
          '• /wallet — Wallet &amp; Deposit\n'
          '• /orders — My Orders\n'
          '• /support — Support (5 min)\n\n'
          'Use the buttons below or type any command above to continue.')
    await m.answer_photo(START_PHOTO,caption=text,reply_markup=main_kb())


@router.message(CommandStart())
async def start(m:Message):
    await save_user(m.from_user)
    if not await is_joined(m.from_user.id):
        return await send_join_gate(m)
    await send_verified_start(m)


@router.callback_query(F.data=='verify_join')
async def verify_join(c:CallbackQuery):
    if not await is_joined(c.from_user.id):
        await c.answer('❌ Please join the channel first.',show_alert=True)
        return
    await c.answer('✅ Verified!')
    await send_verified_start(c.message)


async def require_join_for_command(m:Message):
    if m.from_user.id in ADMIN_IDS:
        return True
    if not await is_joined(m.from_user.id):
        await send_join_gate(m)
        return False
    return True


@router.message(Command('buy'))
async def cmd_buy(m:Message):
    if not await require_join_for_command(m): return
    await show_products_from_message(m)


@router.message(Command('wallet'))
async def cmd_wallet(m:Message):
    if not await require_join_for_command(m): return
    await save_user(m.from_user)
    u=await users.find_one({'_id':m.from_user.id}) or {}
    bal=float(u.get('balance',0)); total=float(u.get('total_deposited',0))
    await m.answer(
        f'💰 <b>Wallet</b>\n\n💎 Balance: <b>₹{bal:.2f}</b>\n'
        f'📊 Total Deposited: <b>₹{total:.2f}</b>\n\nChoose an option below.',
        reply_markup=wallet_kb())


@router.message(Command('orders'))
async def cmd_orders(m:Message):
    if not await require_join_for_command(m): return
    docs=await orders.find({'user_id':m.from_user.id}).sort('created_at',-1).to_list(10)
    text='📦 <b>My Orders</b>\n\n'+(
        '\n'.join(f"• {o['product_name']} — ₹{float(o['amount']):.2f} — {o['status']}" for o in docs)
        if docs else 'No orders yet.')
    await m.answer(text,reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]]))


@router.message(Command('support'))
async def cmd_support(m:Message):
    if not await require_join_for_command(m): return
    now=datetime.now(timezone.utc)
    await support.insert_one({'user_id':m.from_user.id,'status':'open',
                              'expires_at':now+timedelta(minutes=5),'created_at':now})
    await m.answer('💬 <b>Support session started.</b>\nYou have 5 minutes to send your payment/order questions.')


async def show_products_from_message(m:Message):
    ps=await products.find({'active':True}).to_list(30)
    rows=[[InlineKeyboardButton(text=f"{p['name']} — ₹{float(p['price']):.2f}",callback_data=f"buy:{p['_id']}")] for p in ps]
    rows.append([InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')])
    await m.answer('🛒 <b>Products</b>\n\nChoose a product:',
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data=='home')
async def home(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS and not await is_joined(c.from_user.id):
        await c.answer('❌ Join the channel first.', show_alert=True)
        return
    await c.message.edit_text('🛍️ <b>Waste Botz</b>\n\nChoose an option:',reply_markup=main_kb())
    await c.answer()


@router.callback_query(F.data=='wallet')
async def wallet(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS and not await is_joined(c.from_user.id):
        await c.answer('❌ Join the channel first.',show_alert=True); return
    await save_user(c.from_user)
    u=await users.find_one({'_id':c.from_user.id}) or {}
    bal=float(u.get('balance',0)); total=float(u.get('total_deposited',0))
    text=(f'💰 <b>Wallet</b>\n\n'
          f'💎 Balance: <b>₹{bal:.2f}</b>\n'
          f'📊 Total Deposited: <b>₹{total:.2f}</b>\n\n'
          'Choose an option below.')
    await c.message.answer(text,reply_markup=wallet_kb()); await c.answer()


@router.callback_query(F.data=='deposit')
async def deposit(c:CallbackQuery):
    p=await get_payment_settings()
    minimum=float(p.get('min_deposit',1)); maximum=float(p.get('max_deposit',0))
    limit=f'₹{maximum:.2f}' if maximum>0 else 'No maximum limit'
    text=(f'💳 <b>Deposit</b>\n\n'
          f'Enter the amount you want to deposit.\n'
          f'💰 Minimum: ₹{minimum:.2f}\n'
          f'💰 Maximum: {limit}\n\n'
          f'💳 UPI ID: <code>{p["upi_id"]}</code>\n\n'
          f'{p["instructions"]}\n\n'
          f'⏱️ You have <b>{DEPOSIT_WINDOW_MINUTES} minutes</b> to complete this deposit.')
    if p.get('qr_file_id'):
        await bot.send_photo(c.from_user.id,p['qr_file_id'],caption=text)
    else:
        await c.message.answer(text)
    await c.answer()


@router.message(F.text.regexp(r'^\d+(\.\d{1,2})?$'))
async def amount(m:Message):
    await save_user(m.from_user)
    p=await get_payment_settings()
    try: amt=float(m.text.strip())
    except ValueError: return await m.answer('Enter a valid amount, e.g. 100.')
    if amt<=0: return await m.answer('Enter a valid amount.')
    minimum=float(p.get('min_deposit',1)); maximum=float(p.get('max_deposit',0))
    if amt<minimum: return await m.answer(f'Minimum deposit is ₹{minimum:.2f}.')
    if maximum>0 and amt>maximum: return await m.answer(f'Maximum deposit is ₹{maximum:.2f}.')
    now=datetime.now(timezone.utc)
    # Keep only one active deposit request per user.
    await deposits.update_many({'user_id':m.from_user.id,'status':'awaiting_screenshot'}, {'$set':{'status':'expired','expired_at':now}})
    expires=now+timedelta(minutes=DEPOSIT_WINDOW_MINUTES)
    r=await deposits.insert_one({'user_id':m.from_user.id,'amount':amt,'status':'awaiting_screenshot','created_at':now,'expires_at':expires})
    text=(f'💳 <b>Deposit Request</b>\n\n'
          f'Amount: <b>₹{amt:.2f}</b>\n'
          f'UPI: <code>{p["upi_id"]}</code>\n\n'
          f'{p["instructions"]}\n\n'
          f'⏱️ Request expires in <b>{DEPOSIT_WINDOW_MINUTES} minutes</b>.\n'
          'After payment, send the screenshot here.')
    if p.get('qr_file_id'):
        await bot.send_photo(m.chat.id,p['qr_file_id'],caption=text)
    else:
        await m.answer(text)


@router.callback_query(F.data=='deposit_history')
async def deposit_history(c:CallbackQuery):
    docs=await deposits.find({'user_id':c.from_user.id}).sort('created_at',-1).to_list(10)
    if not docs:
        text='🧾 <b>Deposit History</b>\n\nNo deposits yet.'
    else:
        lines=[]
        for d in docs:
            status=d.get('status','unknown').replace('_',' ').title()
            lines.append(f'• ₹{float(d.get("amount",0)):.2f} — {status}')
        text='🧾 <b>Deposit History</b>\n\n'+'\n'.join(lines)
    await c.message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ Wallet',callback_data='wallet')]])); await c.answer()


async def forward_deposit_to_admin(m:Message, dep):
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Approve',callback_data=f"dep_ok:{dep['_id']}"),InlineKeyboardButton(text='❌ Reject',callback_data=f"dep_no:{dep['_id']}")]])
    for aid in ADMIN_IDS:
        await bot.send_photo(aid,m.photo[-1].file_id,
            caption=(f'💳 <b>Deposit Request</b>\n'
                     f'Buyer: {m.from_user.full_name}\n'
                     f'User ID: <code>{m.from_user.id}</code>\n'
                     f'Amount: ₹{float(dep["amount"]):.2f}\n'
                     f'⏱️ Expires: {dep["expires_at"].strftime("%H:%M:%S UTC")}'),
            reply_markup=kb)


@router.message(F.photo)
async def payment_or_admin_photo(m:Message):
    # Admin QR setup
    if m.from_user.id in ADMIN_IDS:
        p=await get_payment_settings()
        if p.get('admin_pending')=='qr':
            await settings.update_one({'_id':'payment'},{'$set':{'qr_file_id':m.photo[-1].file_id},'$unset':{'admin_pending':''}})
            return await m.answer('✅ QR Code uploaded/changed successfully.')

    dep=await deposits.find_one({'user_id':m.from_user.id,'status':'awaiting_screenshot'},sort=[('created_at',-1)])
    if not dep: return await m.answer('Start a deposit first.')
    now=datetime.now(timezone.utc)
    if dep.get('expires_at') and now>dep['expires_at']:
        await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'expired','expired_at':now}})
        return await m.answer('⏱️ This deposit request expired. Please start a new deposit.')
    await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'pending_review','screenshot_file_id':m.photo[-1].file_id,'submitted_at':now}})
    await forward_deposit_to_admin(m,dep)
    await m.answer('📨 Screenshot received. Admin will verify your payment.')



async def find_user_for_admin(identifier: str):
    identifier = identifier.strip()
    if identifier.startswith('@'):
        identifier = identifier[1:]
    if identifier.isdigit():
        return await users.find_one({'_id': int(identifier)})
    return await users.find_one({'username': {'$regex': f'^{re.escape(identifier)}$', '$options': 'i'}})

def admin_user_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⬅️ Admin Panel', callback_data='admin:home')]
    ])

@router.callback_query(F.data=='admin:users')
async def admin_users(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer('Not authorized.',show_alert=True)
    await c.message.edit_text(
        '👤 <b>User Funds Manager</b>\n\n'
        'Use these admin commands:\n\n'
        '<code>/balance USER_ID_OR_USERNAME</code>\n'
        '<code>/addfunds USER_ID_OR_USERNAME AMOUNT</code>\n'
        '<code>/removefunds USER_ID_OR_USERNAME AMOUNT</code>\n\n'
        'Example:\n'
        '<code>/addfunds 123456789 500</code>\n'
        '<code>/removefunds @username 100</code>',
        reply_markup=admin_user_kb())
    await c.answer()

async def admin_user_lookup(m:Message, identifier:str):
    u=await find_user_for_admin(identifier)
    if not u:
        await m.answer('❌ User not found. The user must have started the bot first.')
        return None
    return u

@router.message(Command('balance'))
async def admin_balance(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    parts=m.text.split(maxsplit=1)
    if len(parts)<2: return await m.answer('Usage: /balance USER_ID_OR_USERNAME')
    u=await admin_user_lookup(m,parts[1])
    if not u: return
    await m.answer(
        f'👤 <b>User Balance</b>\n\n'
        f'Name: <b>{u.get("name","Unknown")}</b>\n'
        f'Username: @{u.get("username") or "none"}\n'
        f'ID: <code>{u["_id"]}</code>\n\n'
        f'💰 Balance: <b>₹{float(u.get("balance",0)):.2f}</b>\n'
        f'📊 Total Deposited: <b>₹{float(u.get("total_deposited",0)):.2f}</b>')

@router.message(Command('addfunds'))
async def admin_addfunds(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    parts=m.text.split()
    if len(parts)!=3: return await m.answer('Usage: /addfunds USER_ID_OR_USERNAME AMOUNT')
    try: amount=float(parts[2])
    except ValueError: return await m.answer('❌ Amount must be a number.')
    if amount<=0: return await m.answer('❌ Amount must be greater than 0.')
    u=await admin_user_lookup(m,parts[1])
    if not u: return
    now=datetime.now(timezone.utc)
    await users.update_one({'_id':u['_id']},{'$inc':{'balance':amount},'$set':{'updated_at':now}})
    await db.wallet_transactions.insert_one({
        'user_id':u['_id'],'type':'admin_add','amount':amount,
        'admin_id':m.from_user.id,'created_at':now
    })
    newbal=float(u.get('balance',0))+amount
    await m.answer(f'✅ Added <b>₹{amount:.2f}</b> to <code>{u["_id"]}</code>.\n💰 New balance: <b>₹{newbal:.2f}</b>')
    try:
        await bot.send_message(u['_id'],f'💰 <b>Funds Added</b>\n₹{amount:.2f} was added to your wallet by admin.\nNew balance: ₹{newbal:.2f}')
    except Exception: pass

@router.message(Command('removefunds'))
async def admin_removefunds(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    parts=m.text.split()
    if len(parts)!=3: return await m.answer('Usage: /removefunds USER_ID_OR_USERNAME AMOUNT')
    try: amount=float(parts[2])
    except ValueError: return await m.answer('❌ Amount must be a number.')
    if amount<=0: return await m.answer('❌ Amount must be greater than 0.')
    u=await admin_user_lookup(m,parts[1])
    if not u: return
    current=float(u.get('balance',0))
    if amount>current:
        return await m.answer(f'❌ Insufficient balance. Current balance: ₹{current:.2f}')
    now=datetime.now(timezone.utc)
    result=await users.update_one(
        {'_id':u['_id'],'balance':{'$gte':amount}},
        {'$inc':{'balance':-amount},'$set':{'updated_at':now}})
    if result.modified_count!=1:
        return await m.answer('❌ Balance changed; please check the balance again.')
    await db.wallet_transactions.insert_one({
        'user_id':u['_id'],'type':'admin_remove','amount':amount,
        'admin_id':m.from_user.id,'created_at':now
    })
    newbal=current-amount
    await m.answer(f'✅ Removed <b>₹{amount:.2f}</b> from <code>{u["_id"]}</code>.\n💰 New balance: <b>₹{newbal:.2f}</b>')
    try:
        await bot.send_message(u['_id'],f'💰 <b>Funds Removed</b>\n₹{amount:.2f} was removed from your wallet by admin.\nNew balance: ₹{newbal:.2f}')
    except Exception: pass

@router.message(F.text)
async def admin_payment_text(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    p=await get_payment_settings(); action=p.get('admin_pending')
    if not action: return
    value=m.text.strip()
    if action=='upi':
        await settings.update_one({'_id':'payment'},{'$set':{'upi_id':value},'$unset':{'admin_pending':''}})
        return await m.answer(f'✅ UPI ID changed to <code>{value}</code>.')
    if action=='text':
        await settings.update_one({'_id':'payment'},{'$set':{'instructions':value},'$unset':{'admin_pending':''}})
        return await m.answer('✅ Payment Instructions updated.')
    if action in ('min','max'):
        try: v=float(value)
        except ValueError: return await m.answer('Send a number, e.g. 100.')
        if v<0: return await m.answer('Amount cannot be negative.')
        if action=='min':
            await settings.update_one({'_id':'payment'},{'$set':{'min_deposit':v},'$unset':{'admin_pending':''}})
            return await m.answer(f'✅ Minimum Deposit set to ₹{v:.2f}.')
        await settings.update_one({'_id':'payment'},{'$set':{'max_deposit':v},'$unset':{'admin_pending':''}})
        return await m.answer('✅ Maximum Deposit set to '+('No limit.' if v==0 else f'₹{v:.2f}.'))


@router.message(Command('admin'))
async def admin_panel(m:Message):
    if m.from_user.id not in ADMIN_IDS: return await m.answer('Not authorized.')
    await m.answer('🛠️ <b>Admin Panel</b>\n\nChoose what you want to manage:',reply_markup=admin_kb())


@router.callback_query(F.data=='admin:home')
async def admin_home(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    await c.message.edit_text('🛠️ <b>Admin Panel</b>\n\nChoose what you want to manage:',reply_markup=admin_kb()); await c.answer()


@router.callback_query(F.data=='admin:payment')
async def admin_payment(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    await c.message.edit_text('⚙️ <b>Payment Settings</b>',reply_markup=admin_payment_kb()); await c.answer()


@router.callback_query(F.data=='ps:view')
async def ps_view(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    p=await get_payment_settings(); mx='No limit' if float(p.get('max_deposit',0))<=0 else f'₹{float(p["max_deposit"]):.2f}'
    qr='✅ Set' if p.get('qr_file_id') else '❌ Not set'
    text=(f'⚙️ <b>Payment Settings</b>\n\n💳 UPI ID: <code>{p["upi_id"]}</code>\n📷 QR: {qr}\n💬 Instructions: {p["instructions"]}\n💰 Minimum: ₹{float(p.get("min_deposit",1)):.2f}\n💰 Maximum: {mx}')
    await c.message.edit_text(text,reply_markup=admin_payment_kb()); await c.answer()


@router.callback_query(F.data.in_({'ps:upi','ps:text','ps:min','ps:max','ps:qr'}))
async def ps_action(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    action=c.data.split(':',1)[1]
    prompts={'upi':'Send the new UPI ID.','text':'Send the new payment instructions.','min':'Send the minimum deposit amount, e.g. 10.','max':'Send the maximum deposit amount, e.g. 5000. Send 0 for no limit.','qr':'Send the new QR image as a photo.'}
    await settings.update_one({'_id':'payment'},{'$set':{'admin_pending':action}},upsert=True)
    await c.message.answer('✏️ '+prompts[action]); await c.answer()


@router.callback_query(F.data=='admin:products')
async def admin_products(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    docs=await products.find({}).sort('created_at',-1).to_list(30)
    lines=[f"• <b>{p.get('name','Unnamed')}</b> — ₹{float(p.get('price',0)):.2f} — {'🟢 Active' if p.get('active',True) else '🔴 Disabled'}" for p in docs]
    text='📋 <b>Manage Products</b>\n\n'+('\n'.join(lines) if lines else 'No products yet.')+'\n\nCommands:\n<code>/addproduct Name | 100</code>\n<code>/disableproduct PRODUCT_ID</code>\n<code>/enableproduct PRODUCT_ID</code>\n<code>/deleteproduct PRODUCT_ID</code>'
    await c.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ Admin Panel',callback_data='admin:home')]])); await c.answer()


@router.message(F.text.startswith('/addproduct'))
async def addproduct(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    raw=m.text.partition(' ')[2].strip()
    try: name, price=raw.rsplit('|',1); price=float(price.strip()); name=name.strip()
    except Exception: return await m.answer('Usage: /addproduct Product Name | 100')
    if not name or price<=0: return await m.answer('Use a valid product name and positive price.')
    r=await products.insert_one({'name':name,'price':price,'active':True,'created_at':datetime.now(timezone.utc)})
    await m.answer(f'✅ Product added. ID: <code>{r.inserted_id}</code>')


async def product_status(m:Message, active:bool):
    if m.from_user.id not in ADMIN_IDS: return
    raw=m.text.partition(' ')[2].strip()
    try: oid=ObjectId(raw)
    except Exception: return await m.answer('Invalid product ID.')
    r=await products.update_one({'_id':oid},{'$set':{'active':active}})
    await m.answer('✅ Updated.' if r.modified_count else 'Product not found.')


@router.message(F.text.startswith('/disableproduct'))
async def disableproduct(m:Message): await product_status(m,False)

@router.message(F.text.startswith('/enableproduct'))
async def enableproduct(m:Message): await product_status(m,True)


@router.message(F.text.startswith('/deleteproduct'))
async def deleteproduct(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    try: oid=ObjectId(m.text.partition(' ')[2].strip())
    except Exception: return await m.answer('Invalid product ID.')
    r=await products.delete_one({'_id':oid})
    await m.answer('🗑️ Product deleted.' if r.deleted_count else 'Product not found.')


@router.callback_query(F.data.startswith('dep_ok:'))
async def dep_ok(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    try: oid=ObjectId(c.data.split(':',1)[1])
    except Exception: return await c.answer('Invalid request.',show_alert=True)
    d=await deposits.find_one({'_id':oid})
    if not d or d.get('status')!='pending_review': return await c.answer('Already processed.',show_alert=True)
    now=datetime.now(timezone.utc)
    await deposits.update_one({'_id':oid},{'$set':{'status':'approved','approved_by':c.from_user.id,'approved_at':now}})
    await users.update_one({'_id':d['user_id']},{'$inc':{'balance':float(d['amount']),'total_deposited':float(d['amount'])}},upsert=True)
    await bot.send_message(d['user_id'],f'✅ <b>Deposit approved</b>\n₹{float(d["amount"]):.2f} added to your wallet.')
    try: await c.message.edit_caption((c.message.caption or '')+'\n\n✅ <b>APPROVED</b>',reply_markup=None)
    except Exception: pass
    await c.answer('Approved')


@router.callback_query(F.data.startswith('dep_no:'))
async def dep_no(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    try: oid=ObjectId(c.data.split(':',1)[1])
    except Exception: return await c.answer('Invalid request.',show_alert=True)
    d=await deposits.find_one({'_id':oid})
    if not d or d.get('status')!='pending_review': return await c.answer('Already processed.',show_alert=True)
    now=datetime.now(timezone.utc)
    await deposits.update_one({'_id':oid},{'$set':{'status':'rejected','rejected_by':c.from_user.id,'rejected_at':now}})
    await bot.send_message(d['user_id'],'❌ Your deposit was rejected after verification.')
    try: await c.message.edit_caption((c.message.caption or '')+'\n\n❌ <b>REJECTED</b>',reply_markup=None)
    except Exception: pass
    await c.answer('Rejected')


@router.callback_query(F.data=='products')
async def show_products(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS and not await is_joined(c.from_user.id):
        await c.answer('❌ Join the channel first.',show_alert=True)
        return
    ps=await products.find({'active':True}).to_list(30)
    rows=[[InlineKeyboardButton(text=f"{p['name']} — ₹{float(p['price']):.2f}",callback_data=f"buy:{p['_id']}")] for p in ps]
    rows.append([InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')])
    await c.message.answer('🛒 <b>Products</b>\n\nChoose a product:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()


@router.callback_query(F.data.startswith('buy:'))
async def buy(c:CallbackQuery):
    try: p=await products.find_one({'_id':ObjectId(c.data.split(':',1)[1]),'active':True})
    except Exception: p=None
    if not p: return await c.answer('Unavailable.',show_alert=True)
    u=await users.find_one({'_id':c.from_user.id}); bal=float((u or {}).get('balance',0)); price=float(p['price'])
    if bal<price: return await c.answer('Insufficient wallet balance.',show_alert=True)
    await users.update_one({'_id':c.from_user.id},{'$inc':{'balance':-price}})
    o={'user_id':c.from_user.id,'product_id':p['_id'],'product_name':p['name'],'amount':price,'status':'pending_admin','created_at':datetime.now(timezone.utc)}
    r=await orders.insert_one(o)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Confirm',callback_data=f'ord_ok:{r.inserted_id}'),InlineKeyboardButton(text='↩️ Refund',callback_data=f'ord_ref:{r.inserted_id}')]])
    for aid in ADMIN_IDS:
        await bot.send_message(aid,f"🛒 <b>New Order</b>\nBuyer: {c.from_user.full_name}\nUser ID: <code>{c.from_user.id}</code>\nProduct: <b>{p['name']}</b>\nAmount: ₹{price:.2f}\nOrder ID: <code>{r.inserted_id}</code>",reply_markup=kb)
    await c.message.edit_text(f'✅ <b>Order created</b>\n\nProduct: {p["name"]}\nAmount: ₹{price:.2f}\nOrder ID: <code>{r.inserted_id}</code>\n\nAdmin will confirm your order.')
    await c.answer()


@router.callback_query(F.data.startswith('ord_ok:'))
async def ord_ok(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    try: oid=ObjectId(c.data.split(':',1)[1])
    except Exception: return await c.answer('Invalid order.',show_alert=True)
    o=await orders.find_one({'_id':oid})
    if not o or o.get('status')!='pending_admin': return await c.answer('Already processed.',show_alert=True)
    await orders.update_one({'_id':oid},{'$set':{'status':'confirmed','confirmed_by':c.from_user.id,'confirmed_at':datetime.now(timezone.utc)}})
    await bot.send_message(o['user_id'],f'✅ Order <code>{oid}</code> confirmed.')
    await c.message.edit_reply_markup(reply_markup=None); await c.answer('Confirmed')


@router.callback_query(F.data.startswith('ord_ref:'))
async def ord_ref(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    try: oid=ObjectId(c.data.split(':',1)[1])
    except Exception: return await c.answer('Invalid order.',show_alert=True)
    o=await orders.find_one({'_id':oid})
    if not o or o.get('status')!='pending_admin': return await c.answer('Already processed.',show_alert=True)
    await orders.update_one({'_id':oid},{'$set':{'status':'refunded','refunded_by':c.from_user.id,'refunded_at':datetime.now(timezone.utc)}})
    await users.update_one({'_id':o['user_id']},{'$inc':{'balance':float(o['amount'])}})
    await bot.send_message(o['user_id'],f'↩️ Order <code>{oid}</code> refunded to your wallet.')
    await c.message.edit_reply_markup(reply_markup=None); await c.answer('Refunded')


@router.callback_query(F.data=='orders')
async def orders_list(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS and not await is_joined(c.from_user.id):
        await c.answer('❌ Join the channel first.',show_alert=True); return
    docs=await orders.find({'user_id':c.from_user.id}).sort('created_at',-1).to_list(10)
    text='📦 <b>My Orders</b>\n\n'+('\n'.join(f"• {o['product_name']} — ₹{float(o['amount']):.2f} — {o['status']}" for o in docs) if docs else 'No orders yet.')
    await c.message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]])); await c.answer()


@router.callback_query(F.data=='support')
async def support_start(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS and not await is_joined(c.from_user.id):
        await c.answer('❌ Join the channel first.',show_alert=True); return
    now=datetime.now(timezone.utc)
    await support.insert_one({'user_id':c.from_user.id,'status':'open','expires_at':now+timedelta(minutes=5),'created_at':now})
    await c.message.answer('💬 <b>Support session started.</b>\nYou have 5 minutes to send your payment/order questions.'); await c.answer()


async def cleanup():
    while True:
        now=datetime.now(timezone.utc)
        await support.update_many({'status':'open','expires_at':{'$lte':now}},{'$set':{'status':'closed','closed_at':now}})
        await deposits.update_many({'status':'awaiting_screenshot','expires_at':{'$lte':now}},{'$set':{'status':'expired','expired_at':now}})
        await asyncio.sleep(10)


async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.set_my_commands([
        BotCommand(command='start', description='Start / Verify & Main Menu'),
        BotCommand(command='buy', description='Buy Products'),
        BotCommand(command='wallet', description='Wallet & Deposit'),
        BotCommand(command='orders', description='My Orders'),
        BotCommand(command='support', description='Support (5 min)'),
        BotCommand(command='admin', description='Admin Panel')
    ])
    await asyncio.gather(dp.start_polling(bot),cleanup())

if __name__=='__main__': asyncio.run(main())
