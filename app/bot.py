import asyncio, logging, os, re
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand

# Visual message font: keeps Telegram HTML tags, commands, URLs and <code> values intact.
# This affects bot-generated messages only; actual slash commands remain ASCII/Telegram-safe.
import html as _html

_UPPER = dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ', '𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙'))
_LOWER = dict(zip('abcdefghijklmnopqrstuvwxyz', 'ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ'))

def _style_plain(part: str) -> str:
    # Keep slash commands exactly usable/copyable inside bot messages.
    protected = []
    def hold(m):
        protected.append(m.group(0)); return f'\x00{len(protected)-1}\x00'
    part = re.sub(r'(?<![\w])/[A-Za-z0-9_]+(?:@[A-Za-z0-9_]+)?', hold, part)
    # Keep URLs and @handles unchanged so links/mentions remain functional.
    part = re.sub(r'https?://[^\s<>]+', hold, part)
    part = re.sub(r'@[A-Za-z0-9_]+', hold, part)
    part = ''.join(_UPPER.get(ch, _LOWER.get(ch, ch)) for ch in part)
    for i, value in enumerate(protected):
        part = part.replace(f'\x00{i}\x00', value)
    return part

def styled_message(text):
    if not isinstance(text, str):
        return text
    # Protect HTML tags and code blocks. Code/IDs must stay plain for copying.
    chunks = re.split(r'(<code>.*?</code>|<[^>]+>)', text, flags=re.S | re.I)
    out=[]
    for chunk in chunks:
        if not chunk:
            continue
        if re.fullmatch(r'<code>.*?</code>', chunk, flags=re.S | re.I) or re.fullmatch(r'<[^>]+>', chunk, flags=re.S):
            out.append(chunk)
        else:
            out.append(_style_plain(chunk))
    return ''.join(out)

# Patch only outgoing bot text. Inline-button labels and actual BotCommand names stay untouched.
_original_bot_send_message = Bot.send_message
async def _styled_bot_send_message(self, chat_id, text, *args, **kwargs):
    return await _original_bot_send_message(self, chat_id, styled_message(text), *args, **kwargs)
Bot.send_message = _styled_bot_send_message

_original_bot_send_photo = Bot.send_photo
async def _styled_bot_send_photo(self, chat_id, photo, *args, **kwargs):
    if 'caption' in kwargs:
        kwargs['caption'] = styled_message(kwargs['caption'])
    elif args:
        # aiogram's caption is a keyword in current versions; leave positional args untouched for compatibility.
        pass
    return await _original_bot_send_photo(self, chat_id, photo, *args, **kwargs)
Bot.send_photo = _styled_bot_send_photo

_original_message_answer = Message.answer
async def _styled_message_answer(self, text=None, *args, **kwargs):
    if text is not None:
        text = styled_message(text)
    return await _original_message_answer(self, text, *args, **kwargs)
Message.answer = _styled_message_answer

_original_message_answer_photo = Message.answer_photo
async def _styled_message_answer_photo(self, photo, *args, **kwargs):
    if 'caption' in kwargs:
        kwargs['caption'] = styled_message(kwargs['caption'])
    return await _original_message_answer_photo(self, photo, *args, **kwargs)
Message.answer_photo = _styled_message_answer_photo

_original_message_edit_text = Message.edit_text
async def _styled_message_edit_text(self, text, *args, **kwargs):
    return await _original_message_edit_text(self, styled_message(text), *args, **kwargs)
Message.edit_text = _styled_message_edit_text

_original_message_edit_caption = Message.edit_caption
async def _styled_message_edit_caption(self, caption=None, *args, **kwargs):
    if caption is not None:
        caption = styled_message(caption)
    return await _original_message_edit_caption(self, caption, *args, **kwargs)
Message.edit_caption = _styled_message_edit_caption

_original_callback_answer = CallbackQuery.answer
async def _styled_callback_answer(self, text=None, *args, **kwargs):
    if text is not None:
        text = styled_message(text)
    return await _original_callback_answer(self, text, *args, **kwargs)
CallbackQuery.answer = _styled_callback_answer

from motor.motor_asyncio import AsyncIOMotorClient

BOT_TOKEN=os.getenv('BOT_TOKEN','')
MONGO_URI=os.getenv('MONGO_URI','')
MONGO_DB=os.getenv('MONGO_DB','telegram_store')
ADMIN_IDS={int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}
UPI_ID=os.getenv('UPI_ID','yourupi@upi')
FORCE_CHANNEL='@jp_network'
FORCE_CHANNEL_URL='https://t.me/jp_network'
START_PHOTO='https://cdn.phototourl.com/free/2026-08-20-0e143e7d-9bff-42fa-bb3c-d62a2f00de4c.png'
if not BOT_TOKEN or not MONGO_URI or not ADMIN_IDS: raise RuntimeError('Set BOT_TOKEN, MONGO_URI and ADMIN_IDS')

bot=Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML')); dp=Dispatcher(); router=Router(); dp.include_router(router)
db=AsyncIOMotorClient(MONGO_URI)[MONGO_DB]
users, deposits, products, orders, support, settings=(db[x] for x in ('users','deposits','products','orders','support','settings'))

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🛒 Buy Products',callback_data='products')],
        [InlineKeyboardButton(text='💰 Wallet / Deposit',callback_data='wallet')],
        [InlineKeyboardButton(text='📦 My Orders',callback_data='orders')],
        [InlineKeyboardButton(text='💬 Support (5 min)',callback_data='support')]])

async def get_payment_settings():
    p=await settings.find_one({'_id':'payment'})
    if not p:
        p={'_id':'payment','upi_id':UPI_ID,'qr_file_id':None,
           'instructions':'Pay using UPI/QR and send the payment screenshot here.',
           'min_deposit':1.0,'max_deposit':0.0}
        await settings.insert_one(p)
    return p

def admin_payment_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💳 UPI ID',callback_data='ps:upi'),InlineKeyboardButton(text='📷 QR Code',callback_data='ps:qr')],
        [InlineKeyboardButton(text='💬 Payment Text',callback_data='ps:text')],
        [InlineKeyboardButton(text='💰 Minimum Deposit',callback_data='ps:min'),InlineKeyboardButton(text='💰 Maximum Deposit',callback_data='ps:max')],
        [InlineKeyboardButton(text='📋 View Settings',callback_data='ps:view')]
    ])

async def show_payment_settings(target):
    p=await get_payment_settings()
    mx='No limit' if float(p.get('max_deposit',0))<=0 else f"₹{float(p['max_deposit']):.2f}"
    qr='✅ Set' if p.get('qr_file_id') else '❌ Not set'
    text=(f"⚙️ <b>Payment Settings</b>\n\n"
          f"💳 UPI ID: <code>{p['upi_id']}</code>\n"
          f"📷 QR: {qr}\n"
          f"💬 Instructions: {p['instructions']}\n"
          f"💰 Minimum: ₹{float(p.get('min_deposit',1)):.2f}\n"
          f"💰 Maximum: {mx}")
    await target.answer(text,reply_markup=admin_payment_kb())

def join_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📢 Join Channel',url=FORCE_CHANNEL_URL)],
        [InlineKeyboardButton(text='✅ I Joined — Verify',callback_data='verify_join')]])

async def is_joined(user_id:int):
    try:
        member=await bot.get_chat_member(FORCE_CHANNEL,user_id)
        return member.status in ('member','administrator','creator')
    except Exception:
        return False

async def send_join_gate(m:Message):
    text=("👋 <b>Welcome to Waste Botz</b>\n\n"
          "📢 Please join our channel first to continue.\n"
          "After joining, tap <b>✅ I Joined — Verify</b>.")
    await m.answer_photo(START_PHOTO,caption=text,reply_markup=join_kb())

async def send_verified_start(m:Message):
    text=("🎉 <b>Waste Botz</b>\n\n"
          "✅ Verification successful!\n\n"
          "🛍️ <b>All-in-One Store & Support Bot</b>\n"
          "💰 Wallet • 🛒 Products • 📦 Orders • 💬 Support\n\n"
          "Use the buttons below to continue.")
    await m.answer_photo(START_PHOTO,caption=text,reply_markup=main_kb())

async def save_user(u):
    now=datetime.now(timezone.utc)
    await users.update_one({'_id':u.id},{'$set':{'name':u.full_name,'username':u.username,'updated_at':now},'$setOnInsert':{'balance':0.0,'created_at':now}},upsert=True)

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
    await bot.send_message(c.from_user.id,
        '🎉 <b>Verified successfully!</b>\n\nUse the commands/buttons below to continue.\n\n'
        '• /start — Main menu\n• 💰 Wallet / Deposit\n• 🛒 Buy Products\n• 📦 My Orders\n• 💬 Support',
        reply_markup=main_kb())

@router.callback_query(F.data=='home')
async def home(c:CallbackQuery):
    await update_menu_message(c,'🛍️ <b>Digital Store</b>\n\nChoose an option:',main_kb()); await c.answer()

@router.callback_query(F.data=='wallet')
async def wallet(c:CallbackQuery):
    u=await users.find_one({'_id':c.from_user.id}); bal=float((u or {}).get('balance',0))
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Deposit',callback_data='deposit')],[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]])
    await update_menu_message(c,f'💰 <b>Wallet</b>\n\nBalance: <b>₹{bal:.2f}</b>',kb); await c.answer()

@router.callback_query(F.data=='deposit')
async def deposit(c:CallbackQuery):
    p=await get_payment_settings()
    text=(f"💳 <b>Deposit</b>\n\nSend any amount between ₹{float(p.get('min_deposit',1)):.2f}"
          f" and {('₹'+format(float(p['max_deposit']),'.2f')) if float(p.get('max_deposit',0))>0 else 'No maximum limit'}.\n\n"
          f"UPI ID: <code>{p['upi_id']}</code>\n\n{p['instructions']}\n\n"
          "After payment, send the screenshot here. Balance is added only after admin verification.")
    # Mark this user as waiting for the deposit amount.
    await users.update_one({'_id':c.from_user.id},{'$set':{'deposit_pending':True}},upsert=True)
    if p.get('qr_file_id'):
        await bot.send_photo(c.from_user.id,p['qr_file_id'],caption=text)
    else:
        await c.message.answer(text)
    await c.answer()

@router.message(F.text.regexp(r'^\d+(\.\d{1,2})?$'))
async def amount(m:Message):
    p=await get_payment_settings()
    if m.from_user.id in ADMIN_IDS and p.get('admin_pending') in ('min','max'):
        try:
            v=float(m.text.strip())
        except ValueError:
            return await m.answer('Send a number, e.g. 100.')
        if v<0:
            return await m.answer('Amount cannot be negative.')
        action=p['admin_pending']
        field='min_deposit' if action=='min' else 'max_deposit'
        await settings.update_one({'_id':'payment'},{'$set':{field:v},'$unset':{'admin_pending':''}})
        return await m.answer(f"✅ {'Minimum' if action=='min' else 'Maximum'} Deposit set to " + ('No limit.' if action=='max' and v==0 else f'₹{v:.2f}.'))

    u=await users.find_one({'_id':m.from_user.id})
    if not (u or {}).get('deposit_pending'):
        return

    amt=float(m.text.strip())
    if amt<=0:
        return await m.answer('Enter a valid amount.')
    if amt<float(p.get('min_deposit',1)):
        return await m.answer(f"Minimum deposit is ₹{float(p.get('min_deposit',1)):.2f}.")
    if float(p.get('max_deposit',0))>0 and amt>float(p['max_deposit']):
        return await m.answer(f"Maximum deposit is ₹{float(p['max_deposit']):.2f}.")

    now=datetime.now(timezone.utc)
    await deposits.insert_one({'user_id':m.from_user.id,'amount':amt,'status':'awaiting_screenshot','created_at':now})
    await users.update_one({'_id':m.from_user.id},{'$unset':{'deposit_pending':''}})
    text=(f"💳 <b>Deposit Request</b>\nAmount: ₹{amt:.2f}\nUPI: <code>{p['upi_id']}</code>\n\n"
          f"{p['instructions']}\n\nComplete payment and send screenshot.")
    if p.get('qr_file_id'):
        await bot.send_photo(m.chat.id,p['qr_file_id'],caption=text)
    else:
        await m.answer(text)

def inventory_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='➕ Add Account',callback_data='inv:add'), InlineKeyboardButton(text='➖ Remove Account',callback_data='inv:remove')],
        [InlineKeyboardButton(text='📦 Account Stock',callback_data='inv:stock')],
        [InlineKeyboardButton(text='💳 Payment Settings',callback_data='inv:payment')],
    ])

def main_menu_text():
    return '🛍️ <b>Waste Botz</b>\n\nChoose an option:'

async def update_menu_message(c: CallbackQuery, text: str, reply_markup):
    # /start shows the main menu as a photo; edit_caption is required for that message.
    if c.message.photo:
        await c.message.edit_caption(caption=text, reply_markup=reply_markup)
    else:
        await c.message.edit_text(text, reply_markup=reply_markup)


@router.message(F.text == '/buy')
async def cmd_buy(m:Message):
    if not await is_joined(m.from_user.id): return await send_join_gate(m)
    ps=await products.find({'active':True}).to_list(30)
    rows=[[InlineKeyboardButton(text=f"{p['name']} — ₹{float(p['price']):.2f}",callback_data=f"account:{p['_id']}")] for p in ps]
    rows.append([InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')])
    await m.answer('🛒 <b>Products</b>\n\nChoose a product:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.message(F.text == '/wallet')
async def cmd_wallet(m:Message):
    if not await is_joined(m.from_user.id): return await send_join_gate(m)
    u=await users.find_one({'_id':m.from_user.id}); bal=float((u or {}).get('balance',0))
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Deposit',callback_data='deposit')],[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]])
    await m.answer(f'💰 <b>Wallet</b>\n\nBalance: <b>₹{bal:.2f}</b>',reply_markup=kb)

@router.message(F.text == '/orders')
async def cmd_orders(m:Message):
    if not await is_joined(m.from_user.id): return await send_join_gate(m)
    docs=await orders.find({'user_id':m.from_user.id}).sort('created_at',-1).to_list(10)
    text='📦 <b>My Orders</b>\n\n'+('\n'.join(f"• {o['product_name']} — ₹{float(o['amount']):.2f} — {o['status']}" for o in docs) if docs else 'No orders yet.')
    await m.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]]))

@router.message(F.text == '/support')
async def cmd_support(m:Message):
    if not await is_joined(m.from_user.id): return await send_join_gate(m)
    now=datetime.now(timezone.utc)
    await support.insert_one({'user_id':m.from_user.id,'status':'open','expires_at':now+timedelta(minutes=5),'created_at':now})
    await m.answer('💬 <b>Support session started.</b>\nYou have 5 minutes to send your payment/order questions.')

async def show_admin_panel(m:Message):
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📦 Account Stock',callback_data='inv:stock')],
        [InlineKeyboardButton(text='➕ Add Account',callback_data='inv:add'),InlineKeyboardButton(text='➖ Remove Account',callback_data='inv:remove')],
        [InlineKeyboardButton(text='💳 Payment Settings',callback_data='inv:payment')],
    ])
    await m.answer('🛠️ <b>Admin Panel</b>\n\nManage account inventory and payment settings:',reply_markup=kb)

@router.message(F.text == '/admin')
async def admin_panel(m:Message):
    if m.from_user.id not in ADMIN_IDS: return await m.answer('Not authorized.')
    await show_admin_panel(m)

@router.callback_query(F.data == 'inv:payment')
async def inv_payment(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    await c.message.edit_text('💳 <b>Payment Settings</b>\n\nChoose an option:',reply_markup=admin_payment_kb()); await c.answer()

@router.callback_query(F.data == 'inv:stock')
async def inv_stock(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    docs=await products.find({'active':True}).sort('country',1).to_list(100)
    if not docs:
        text='📦 <b>Account Stock</b>\n\nNo accounts in stock.'
    else:
        lines=[]
        for p in docs:
            lines.append(f"🌍 <b>{p.get('country','Unknown')}</b> — <code>{p.get('number',p.get('name',''))}</code> — ₹{float(p.get('price',0)):.2f}")
        text='📦 <b>Account Stock</b>\n\n'+'\n'.join(lines)
    await c.message.edit_text(text,reply_markup=inventory_admin_kb()); await c.answer()

@router.callback_query(F.data == 'inv:add')
async def inv_add_start(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    sid=f'inventory_session:{c.from_user.id}'
    await settings.update_one({'_id':sid},{'$set':{'pending':'add_country','admin_id':c.from_user.id},'$unset':{'country':'','number':''}},upsert=True)
    await c.message.answer('Add Account\n\nSend the Country name.'); await c.answer()

@router.callback_query(F.data == 'inv:remove')
async def inv_remove_start(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    sid=f'inventory_session:{c.from_user.id}'
    await settings.update_one({'_id':sid},{'$set':{'pending':'remove_number','admin_id':c.from_user.id},'$unset':{'country':'','number':''}},upsert=True)
    await c.message.answer('Remove Account\n\nSend the exact number to remove from stock.'); await c.answer()


@router.callback_query(F.data=='ps:view')
async def ps_view(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    await show_payment_settings(c.message); await c.answer()

@router.callback_query(F.data.in_({'ps:upi','ps:text','ps:min','ps:max','ps:qr'}))
async def ps_action(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    action=c.data.split(':',1)[1]
    prompts={'upi':'Send the new UPI ID.','text':'Send the new payment instructions.','min':'Send the minimum deposit amount, e.g. 10.','max':'Send the maximum deposit amount, e.g. 5000. Send 0 for no limit.','qr':'Send the new QR image as a photo.'}
    await settings.update_one({'_id':'payment'},{'$set':{'admin_pending':action}},upsert=True)
    await c.message.answer('✏️ '+prompts[action])
    await c.answer()

@router.message(F.photo)
async def payment_or_qr_photo(m:Message):
    if m.from_user.id in ADMIN_IDS:
        p=await get_payment_settings()
        if p.get('admin_pending')=='qr':
            await settings.update_one({'_id':'payment'},{'$set':{'qr_file_id':m.photo[-1].file_id},'$unset':{'admin_pending':''}})
            return await m.answer('✅ QR Code uploaded/changed successfully.')
    dep=await deposits.find_one({'user_id':m.from_user.id,'status':'awaiting_screenshot'},sort=[('created_at',-1)])
    if not dep: return await m.answer('Start a deposit first.')
    await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'pending_review','screenshot_file_id':m.photo[-1].file_id}})
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Approve',callback_data=f"dep_ok:{dep['_id']}"),InlineKeyboardButton(text='❌ Reject',callback_data=f"dep_no:{dep['_id']}")]])
    for aid in ADMIN_IDS:
        await bot.send_photo(aid,m.photo[-1].file_id,caption=f"💳 <b>Deposit Request</b>\nBuyer: {m.from_user.full_name}\nUser ID: <code>{m.from_user.id}</code>\nAmount: ₹{dep['amount']:.2f}",reply_markup=kb)
    await m.answer('📨 Screenshot received. Admin will verify it.')

async def find_user_for_admin(identifier: str):
    identifier=identifier.strip()
    if identifier.startswith('@'):
        identifier=identifier[1:]
    if identifier.isdigit():
        return await users.find_one({'_id':int(identifier)})
    return await users.find_one({'username':{'$regex':f'^{re.escape(identifier)}$','$options':'i'}})

@router.message(Command('addfund'))
@router.message(Command('addfunds'))
async def admin_addfund(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    parts=m.text.split()
    if len(parts)!=3: return await m.answer('Usage: /addfund USER_ID_OR_USERNAME AMOUNT')
    try: amount=float(parts[2])
    except ValueError: return await m.answer('❌ Amount must be a number.')
    if amount<=0: return await m.answer('❌ Amount must be greater than 0.')
    u=await find_user_for_admin(parts[1])
    if not u: return await m.answer('❌ User not found. The user must have started the bot first.')
    now=datetime.now(timezone.utc)
    await users.update_one({'_id':u['_id']},{'$inc':{'balance':amount},'$set':{'updated_at':now}})
    await db.wallet_transactions.insert_one({'user_id':u['_id'],'type':'admin_add','amount':amount,'admin_id':m.from_user.id,'created_at':now})
    newbal=float(u.get('balance',0))+amount
    await m.answer(f'✅ Added <b>₹{amount:.2f}</b> to <code>{u["_id"]}</code>.\n💰 New balance: <b>₹{newbal:.2f}</b>')
    try:
        await bot.send_message(u['_id'],f'💰 <b>Funds Added</b>\n₹{amount:.2f} was added to your wallet by admin.\nNew balance: ₹{newbal:.2f}')
    except Exception:
        pass

@router.message(Command('removefund'))
@router.message(Command('removefunds'))
async def admin_removefund(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    parts=m.text.split()
    if len(parts)!=3: return await m.answer('Usage: /removefund USER_ID_OR_USERNAME AMOUNT')
    try: amount=float(parts[2])
    except ValueError: return await m.answer('❌ Amount must be a number.')
    if amount<=0: return await m.answer('❌ Amount must be greater than 0.')
    u=await find_user_for_admin(parts[1])
    if not u: return await m.answer('❌ User not found. The user must have started the bot first.')
    current=float(u.get('balance',0))
    if amount>current: return await m.answer(f'❌ Insufficient balance. Current balance: ₹{current:.2f}')
    now=datetime.now(timezone.utc)
    result=await users.update_one({'_id':u['_id'],'balance':{'$gte':amount}},{'$inc':{'balance':-amount},'$set':{'updated_at':now}})
    if result.modified_count!=1: return await m.answer('❌ Balance changed; please check the balance again.')
    await db.wallet_transactions.insert_one({'user_id':u['_id'],'type':'admin_remove','amount':amount,'admin_id':m.from_user.id,'created_at':now})
    newbal=current-amount
    await m.answer(f'✅ Removed <b>₹{amount:.2f}</b> from <code>{u["_id"]}</code>.\n💰 New balance: <b>₹{newbal:.2f}</b>')
    try:
        await bot.send_message(u['_id'],f'💰 <b>Funds Removed</b>\n₹{amount:.2f} was removed from your wallet by admin.\nNew balance: ₹{newbal:.2f}')
    except Exception:
        pass

@router.message(F.text)
async def admin_payment_text(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    sid=f'inventory_session:{m.from_user.id}'
    inv=await settings.find_one({'_id':sid})
    inv_pending=(inv or {}).get('pending')
    value=m.text.strip()
    if inv_pending:
        if inv_pending=='add_country':
            await settings.update_one({'_id':sid},{'$set':{'pending':'add_number','country':value}})
            return await m.answer('2️⃣ Send the <b>number</b>.')
        if inv_pending=='add_number':
            await settings.update_one({'_id':sid},{'$set':{'pending':'add_price','number':value}})
            return await m.answer('3️⃣ Send the <b>price</b>, e.g. <code>95</code>.')
        if inv_pending=='add_price':
            try: price=float(value)
            except: return await m.answer('Send a valid price, e.g. 95.')
            if price<=0: return await m.answer('Price must be greater than 0.')
            country=inv.get('country','Unknown'); number=inv.get('number','')
            exists=await products.find_one({'number':number,'active':True})
            if exists:
                return await m.answer('❌ This number is already in stock.')
            await products.insert_one({'name':number,'number':number,'country':country,'price':price,'active':True,'created_at':datetime.now(timezone.utc)})
            await settings.update_one({'_id':sid},{'$unset':{'pending':'','country':'','number':'','admin_id':''}})
            return await m.answer(f'✅ Account added.\n🌍 Country: <b>{country}</b>\n📱 Number: <code>{number}</code>\n💰 Price: ₹{price:.2f}')
        if inv_pending=='remove_number':
            r=await products.update_one({'number':value,'active':True},{'$set':{'active':False,'removed_at':datetime.now(timezone.utc)}})
            await settings.update_one({'_id':sid},{'$unset':{'pending':'','admin_id':''}})
            return await m.answer('✅ Account removed from stock.' if r.modified_count else '❌ Number not found in active stock.')
    p=await get_payment_settings(); action=p.get('admin_pending')
    if not action: return
    if action=='upi':
        if not value: return await m.answer('Send a valid UPI ID.')
        await settings.update_one({'_id':'payment'},{'$set':{'upi_id':value},'$unset':{'admin_pending':''}})
        await m.answer(f'✅ UPI ID changed to <code>{value}</code>.')
    elif action=='text':
        await settings.update_one({'_id':'payment'},{'$set':{'instructions':value},'$unset':{'admin_pending':''}})
        await m.answer('✅ Payment Instructions updated.')
    elif action in ('min','max'):
        try: v=float(value)
        except: return await m.answer('Send a number, e.g. 100.')
        if v<0: return await m.answer('Amount cannot be negative.')
        if action=='min':
            await settings.update_one({'_id':'payment'},{'$set':{'min_deposit':v},'$unset':{'admin_pending':''}})
            await m.answer(f'✅ Minimum Deposit set to ₹{v:.2f}.')
        else:
            await settings.update_one({'_id':'payment'},{'$set':{'max_deposit':v},'$unset':{'admin_pending':''}})
            await m.answer('✅ Maximum Deposit set to '+('No limit.' if v==0 else f'₹{v:.2f}.'))


async def screenshot(m:Message):
    dep=await deposits.find_one({'user_id':m.from_user.id,'status':'awaiting_screenshot'},sort=[('created_at',-1)])
    if not dep: return await m.answer('Start a deposit first.')
    await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'pending_review','screenshot_file_id':m.photo[-1].file_id}})
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Approve',callback_data=f"dep_ok:{dep['_id']}"),InlineKeyboardButton(text='❌ Reject',callback_data=f"dep_no:{dep['_id']}")]])
    for aid in ADMIN_IDS:
        await bot.send_photo(aid,m.photo[-1].file_id,caption=f"💳 <b>Deposit Request</b>\nBuyer: {m.from_user.full_name}\nUser ID: <code>{m.from_user.id}</code>\nAmount: ₹{dep['amount']:.2f}",reply_markup=kb)
    await m.answer('📨 Screenshot received. Admin will verify it.')

@router.callback_query(F.data.startswith('dep_ok:'))
async def dep_ok(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    d=await deposits.find_one({'_id':ObjectId(c.data.split(':')[1])})
    if not d or d['status']!='pending_review': return await c.answer('Already processed.',show_alert=True)
    now=datetime.now(timezone.utc); await deposits.update_one({'_id':d['_id']},{'$set':{'status':'approved','approved_by':c.from_user.id,'approved_at':now}})
    await users.update_one({'_id':d['user_id']},{'$inc':{'balance':d['amount']}},upsert=True)
    await bot.send_message(d['user_id'],f"✅ <b>Deposit approved</b>\n₹{d['amount']:.2f} added to your wallet.")
    await c.message.edit_caption((c.message.caption or '')+'\n\n✅ APPROVED',reply_markup=None); await c.answer('Approved')

@router.callback_query(F.data.startswith('dep_no:'))
async def dep_no(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    d=await deposits.find_one({'_id':ObjectId(c.data.split(':')[1])})
    if not d or d['status']!='pending_review': return await c.answer('Already processed.',show_alert=True)
    now=datetime.now(timezone.utc); await deposits.update_one({'_id':d['_id']},{'$set':{'status':'rejected','rejected_by':c.from_user.id,'rejected_at':now}})
    await bot.send_message(d['user_id'],'❌ Your deposit was rejected after verification.')
    await c.message.edit_caption((c.message.caption or '')+'\n\n❌ REJECTED',reply_markup=None); await c.answer('Rejected')

@router.callback_query(F.data=='products')
async def show_products(c:CallbackQuery):
    ps=await products.find({'active':True}).to_list(100)
    countries=sorted({p.get('country') for p in ps if p.get('country')})
    if countries:
        rows=[[InlineKeyboardButton(text=f'🌍 {country}',callback_data=f'country:{country}')] for country in countries]
    else:
        rows=[[InlineKeyboardButton(text=f"{p['name']} — ₹{float(p['price']):.2f}",callback_data=f"account:{p['_id']}")] for p in ps]
    rows.append([InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')])
    await update_menu_message(c,'🛒 <b>Products</b>\n\nChoose a country:',InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@router.callback_query(F.data.startswith('country:'))
async def country_products(c:CallbackQuery):
    country=c.data.split(':',1)[1]
    ps=await products.find({'active':True,'country':country}).to_list(100)
    rows=[[InlineKeyboardButton(text=f"{p.get('number',p['name'])} — ₹{float(p['price']):.2f}",callback_data=f"account:{p['_id']}")] for p in ps]
    rows.append([InlineKeyboardButton(text='⬅️ Countries',callback_data='products')])
    await update_menu_message(c,f'🌍 <b>{country}</b>\n\nChoose an account:',InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@router.callback_query(F.data.startswith('account:'))
async def account_preview(c:CallbackQuery):
    p=await products.find_one({'_id':ObjectId(c.data.split(':')[1]),'active':True})
    if not p:
        return await c.answer('Unavailable.',show_alert=True)
    number=p.get('number',p.get('name',''))
    price=float(p.get('price',0))
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'💳 Buy Now — ₹{price:.2f}',callback_data=f"buy:{p['_id']}")],
        [InlineKeyboardButton(text='⬅️ Back',callback_data=f"country:{p.get('country','')}")]
    ])
    await update_menu_message(c,
        f"📱 <b>Account Details</b>\n\n🌍 Country: <b>{p.get('country','Unknown')}</b>\n📞 Number: <code>{number}</code>\n💰 Price: <b>₹{price:.2f}</b>\n\nTap <b>Buy Now</b> to continue.",kb)
    await c.answer()

@router.callback_query(F.data.startswith('buy:'))
async def buy(c:CallbackQuery):
    p=await products.find_one({'_id':ObjectId(c.data.split(':')[1]),'active':True})
    if not p: return await c.answer('Unavailable.',show_alert=True)
    u=await users.find_one({'_id':c.from_user.id}); bal=float((u or {}).get('balance',0))
    if bal<p['price']: return await c.answer('Insufficient wallet balance.',show_alert=True)
    await users.update_one({'_id':c.from_user.id},{'$inc':{'balance':-p['price']}})
    o={'user_id':c.from_user.id,'product_id':p['_id'],'product_name':p['name'],'amount':p['price'],'country':p.get('country','Unknown'),'number':p.get('number',p['name']),'status':'pending_admin','created_at':datetime.now(timezone.utc)}
    r=await orders.insert_one(o)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Confirm',callback_data=f"ord_ok:{r.inserted_id}"),InlineKeyboardButton(text='↩️ Refund',callback_data=f"ord_ref:{r.inserted_id}")]])
    for aid in ADMIN_IDS:
        await bot.send_message(aid,f"🛒 <b>New Order</b>\nBuyer: {c.from_user.full_name}\nUser ID: <code>{c.from_user.id}</code>\nCountry: <b>{p.get('country','Unknown')}</b>\nNumber: <code>{p.get('number',p['name'])}</code>\nAmount: ₹{float(p['price']):.2f}\nOrder ID: <code>{r.inserted_id}</code>",reply_markup=kb)
    await update_menu_message(c,f"✅ <b>Order created</b>\n\nCountry: {p.get('country','Unknown')}\nNumber: <code>{p.get('number',p['name'])}</code>\nAmount: ₹{float(p['price']):.2f}\nOrder ID: <code>{r.inserted_id}</code>\n\nAdmin will confirm your order.",None)
    await c.answer()

@router.callback_query(F.data.startswith('ord_ok:'))
async def ord_ok(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    oid=ObjectId(c.data.split(':')[1]); o=await orders.find_one({'_id':oid})
    if not o or o['status']!='pending_admin': return await c.answer('Already processed.',show_alert=True)
    await orders.update_one({'_id':oid},{'$set':{'status':'confirmed','confirmed_by':c.from_user.id,'confirmed_at':datetime.now(timezone.utc)}})
    await bot.send_message(o['user_id'],f'✅ Order <code>{oid}</code> confirmed.')
    await c.message.edit_reply_markup(reply_markup=None); await c.answer('Confirmed')

@router.callback_query(F.data.startswith('ord_ref:'))
async def ord_ref(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    oid=ObjectId(c.data.split(':')[1]); o=await orders.find_one({'_id':oid})
    if not o or o['status']!='pending_admin': return await c.answer('Already processed.',show_alert=True)
    await orders.update_one({'_id':oid},{'$set':{'status':'refunded','refunded_by':c.from_user.id,'refunded_at':datetime.now(timezone.utc)}})
    await users.update_one({'_id':o['user_id']},{'$inc':{'balance':o['amount']}})
    await bot.send_message(o['user_id'],f'↩️ Order <code>{oid}</code> refunded to your wallet.')
    await c.message.edit_reply_markup(reply_markup=None); await c.answer('Refunded')

@router.callback_query(F.data=='orders')
async def orders_list(c:CallbackQuery):
    docs=await orders.find({'user_id':c.from_user.id}).sort('created_at',-1).to_list(10)
    text='📦 <b>My Orders</b>\n\n'+('\n'.join(f"• {o['product_name']} — ₹{o['amount']:.2f} — {o['status']}" for o in docs) if docs else 'No orders yet.')
    await update_menu_message(c,text,InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]])); await c.answer()

@router.callback_query(F.data=='support')
async def support_start(c:CallbackQuery):
    now=datetime.now(timezone.utc)
    await support.insert_one({'user_id':c.from_user.id,'status':'open','expires_at':now+timedelta(minutes=5),'created_at':now})
    await c.message.answer('💬 <b>Support session started.</b>\nYou have 5 minutes to send your payment/order questions.'); await c.answer()

async def cleanup():
    while True:
        now=datetime.now(timezone.utc)
        await support.update_many({'status':'open','expires_at':{'$lte':now}},{'$set':{'status':'closed','closed_at':now}})
        await asyncio.sleep(10)

async def main():
    logging.basicConfig(level=logging.INFO)
    # Keep the existing force-command menu and add the wallet admin aliases.
    await bot.set_my_commands([
        BotCommand(command='start',description='𝐒ᴛᴀʀᴛ / 𝐕ᴇʀɪғʏ & 𝐌ᴀɪɴ 𝐌ᴇɴᴜ'),
        BotCommand(command='buy',description='𝐁ᴜʏ 𝐏ʀᴏᴅᴜᴄᴛs'),
        BotCommand(command='wallet',description='𝐖ᴀʟʟᴇᴛ & 𝐃ᴇᴘᴏsɪᴛ'),
        BotCommand(command='orders',description='𝐌ʏ 𝐎ʀᴅᴇʀs'),
        BotCommand(command='support',description='𝐒ᴜᴘᴘᴏʀᴛ (5 ᴍɪɴ)'),
        BotCommand(command='admin',description='𝐀ᴅᴍɪɴ 𝐏ᴀɴᴇʟ'),
        BotCommand(command='addfund',description='𝐀ᴅᴅ ғᴜɴᴅs ᴛᴏ ᴀ ᴜsᴇʀ (𝐀ᴅᴍɪɴ)'),
        BotCommand(command='removefund',description='𝐑ᴇᴍᴏᴠᴇ ғᴜɴᴅs ғʀᴏᴍ ᴀ ᴜsᴇʀ (𝐀ᴅᴍɪɴ)')
    ])
    await asyncio.gather(dp.start_polling(bot),cleanup())

if __name__=='__main__': asyncio.run(main())
