import asyncio, logging, os
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
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

bot=Bot(BOT_TOKEN); dp=Dispatcher(); router=Router(); dp.include_router(router)
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
    await c.answer()
    await c.message.answer('🛍️ <b>Digital Store</b>\n\nChoose an option:',reply_markup=main_kb())

@router.callback_query(F.data=='wallet')
async def wallet(c:CallbackQuery):
    if not await is_joined(c.from_user.id):
        await c.answer('❌ Please join the channel first.', show_alert=True)
        return
    await save_user(c.from_user)
    u=await users.find_one({'_id':c.from_user.id}); bal=float((u or {}).get('balance',0))
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Deposit',callback_data='deposit')],[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]])
    await c.answer()
    await c.message.answer(f'💰 <b>Wallet</b>\n\nBalance: <b>₹{bal:.2f}</b>',reply_markup=kb)

@router.callback_query(F.data=='deposit')
async def deposit(c:CallbackQuery):
    p=await get_payment_settings()
    text=(f"💳 <b>Deposit</b>\n\nSend any amount between ₹{float(p.get('min_deposit',1)):.2f}"
          f" and {('₹'+format(float(p['max_deposit']),'.2f')) if float(p.get('max_deposit',0))>0 else 'No maximum limit'}.\n\n"
          f"UPI ID: <code>{p['upi_id']}</code>\n\n{p['instructions']}\n\n"
          "After payment, send the screenshot here. Balance is added only after admin verification.")
    if p.get('qr_file_id'):
        await bot.send_photo(c.from_user.id,p['qr_file_id'],caption=text)
    else:
        await c.message.answer(text)
    await c.answer()

@router.message(F.text.regexp(r'^\d+(\.\d{1,2})?$'))
async def amount(m:Message):
    p=await get_payment_settings()
    if m.from_user.id in ADMIN_IDS and p.get('admin_pending_user_id') == m.from_user.id and p.get('admin_pending') in ('min','max'):
        try: v=float(m.text.strip())
        except: return await m.answer('Send a number, e.g. 100.')
        if v<0: return await m.answer('Amount cannot be negative.')
        action=p['admin_pending']
        field='min_deposit' if action=='min' else 'max_deposit'
        await settings.update_one({'_id':'payment'},{'$set':{field:v},'$unset':{'admin_pending':'','admin_pending_user_id':''}})
        return await m.answer(f"✅ {'Minimum' if action=='min' else 'Maximum'} Deposit set to " + ('No limit.' if action=='max' and v==0 else f'₹{v:.2f}.'))
    await save_user(m.from_user); amt=float(m.text)
    if amt<=0: return await m.answer('Enter a valid amount.')
    if amt<float(p.get('min_deposit',1)): return await m.answer(f"Minimum deposit is ₹{float(p.get('min_deposit',1)):.2f}.")
    if float(p.get('max_deposit',0))>0 and amt>float(p['max_deposit']): return await m.answer(f"Maximum deposit is ₹{float(p['max_deposit']):.2f}.")
    now=datetime.now(timezone.utc)
    await deposits.insert_one({'user_id':m.from_user.id,'amount':amt,'status':'awaiting_screenshot','transaction_id':None,'created_at':now,'expires_at':now+timedelta(minutes=30)})
    text=(f"💳 <b>Deposit Request</b>\nAmount: ₹{amt:.2f}\nUPI: <code>{p['upi_id']}</code>\n\n"
          f"{p['instructions']}\n\nComplete payment and send screenshot.")
    if p.get('qr_file_id'):
        await bot.send_photo(m.chat.id,p['qr_file_id'],caption=text)
    else:
        await m.answer(text)


@router.message(Command('admin'))
async def admin_panel(m:Message):
    if m.from_user.id not in ADMIN_IDS: return await m.answer('Not authorized.')
    await m.answer('🛠️ <b>Admin Panel</b>\n\nPayment settings:',reply_markup=admin_payment_kb())

@router.callback_query(F.data=='ps:view')
async def ps_view(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    await show_payment_settings(c.message); await c.answer()

@router.callback_query(F.data.in_({'ps:upi','ps:text','ps:min','ps:max','ps:qr'}))
async def ps_action(c:CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('Not authorized.',show_alert=True)
    action=c.data.split(':',1)[1]
    prompts={'upi':'Send the new UPI ID.','text':'Send the new payment instructions.','min':'Send the minimum deposit amount, e.g. 10.','max':'Send the maximum deposit amount, e.g. 5000. Send 0 for no limit.','qr':'Send the new QR image as a photo.'}
    await settings.update_one({'_id':'payment'},{'$set':{'admin_pending':action,'admin_pending_user_id':c.from_user.id}},upsert=True)
    await c.message.answer('✏️ '+prompts[action])
    await c.answer()

@router.message(F.photo)
async def payment_or_qr_photo(m:Message):
    if m.from_user.id in ADMIN_IDS:
        p=await get_payment_settings()
        if p.get('admin_pending')=='qr':
            await settings.update_one({'_id':'payment'},{'$set':{'qr_file_id':m.photo[-1].file_id},'$unset':{'admin_pending':'','admin_pending_user_id':''}})
            return await m.answer('✅ QR Code uploaded/changed successfully.')
    dep=await deposits.find_one({'user_id':m.from_user.id,'status':'awaiting_screenshot'},sort=[('created_at',-1)])
    if not dep: return await m.answer('Start a deposit first.')
    if not dep.get('transaction_id'):
        return await m.answer('Please send your Transaction ID first, then send the payment screenshot.')
    if dep.get('expires_at') and datetime.now(timezone.utc) > dep['expires_at']:
        await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'expired'}})
        return await m.answer('⏱️ This deposit request has expired. Please start a new deposit.')
    await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'pending_review','screenshot_file_id':m.photo[-1].file_id}})
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Approve',callback_data=f"dep_ok:{dep['_id']}"),InlineKeyboardButton(text='❌ Reject',callback_data=f"dep_no:{dep['_id']}")]])
    for aid in ADMIN_IDS:
        await bot.send_photo(aid,m.photo[-1].file_id,caption=f"💳 <b>Deposit Request</b>\n👤 Buyer: {m.from_user.full_name}\n🔗 Username: @{m.from_user.username or '—'}\n🆔 User ID: <code>{m.from_user.id}</code>\n💰 Amount: ₹{dep['amount']:.2f}\n🧾 Transaction ID: <code>{dep.get('transaction_id') or '—'}</code>",reply_markup=kb)
    await m.answer('📨 Screenshot received. Admin will verify it.')

@router.message(F.text)
async def text_router(m:Message):
    # Admin setting input has priority.
    if m.from_user.id in ADMIN_IDS:
        p=await get_payment_settings(); action=p.get('admin_pending') if p.get('admin_pending_user_id') == m.from_user.id else None
        if action:
            value=m.text.strip()
            if action=='upi':
                if not value: return await m.answer('Send a valid UPI ID.')
                await settings.update_one({'_id':'payment'},{'$set':{'upi_id':value},'$unset':{'admin_pending':'','admin_pending_user_id':''}})
                return await m.answer(f'✅ UPI ID changed to <code>{value}</code>.')
            if action=='text':
                await settings.update_one({'_id':'payment'},{'$set':{'instructions':value},'$unset':{'admin_pending':'','admin_pending_user_id':''}})
                return await m.answer('✅ Payment Instructions updated.')
            if action in ('min','max'):
                try: v=float(value)
                except: return await m.answer('Send a number, e.g. 100.')
                if v<0: return await m.answer('Amount cannot be negative.')
                field='min_deposit' if action=='min' else 'max_deposit'
                await settings.update_one({'_id':'payment'},{'$set':{field:v},'$unset':{'admin_pending':'','admin_pending_user_id':''}})
                return await m.answer(f"✅ {'Minimum' if action=='min' else 'Maximum'} Deposit set to " + ('No limit.' if action=='max' and v==0 else f'₹{v:.2f}.'))

        # Reply to a support notification to answer the user.
        if m.reply_to_message:
            meta=await support.find_one({'admin_message_id':m.reply_to_message.message_id,'status':'open'})
            if meta and meta.get('expires_at') and datetime.now(timezone.utc) <= meta['expires_at']:
                try:
                    await bot.send_message(meta['user_id'], f"💬 <b>Support</b>\n\n{m.text}")
                    return await m.answer('✅ Reply sent to the user.')
                except Exception:
                    return await m.answer('❌ Could not send the reply to the user.')

    # Transaction ID for the user's latest deposit request.
    if m.from_user.id not in ADMIN_IDS:
        dep=await deposits.find_one({'user_id':m.from_user.id,'status':'awaiting_screenshot'},sort=[('created_at',-1)])
        if dep and not dep.get('transaction_id'):
            if dep.get('expires_at') and datetime.now(timezone.utc)>dep['expires_at']:
                await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'expired'}})
                return await m.answer('⏱️ This deposit request has expired. Please start a new deposit.')
            await deposits.update_one({'_id':dep['_id']},{'$set':{'transaction_id':m.text.strip()}})
            return await m.answer('✅ Transaction ID received. Now send your payment screenshot here.')

    # Forward normal support messages during an active session.
    if m.from_user.id not in ADMIN_IDS:
        sess=await support.find_one({'user_id':m.from_user.id,'status':'open'},sort=[('created_at',-1)])
        if sess and sess.get('expires_at') and datetime.now(timezone.utc)<=sess['expires_at']:
            for aid in ADMIN_IDS:
                try:
                    sent=await bot.send_message(aid, f"💬 <b>Support Message</b>\n👤 {m.from_user.full_name}\n🔗 @{m.from_user.username or '—'}\n🆔 <code>{m.from_user.id}</code>\n\n{m.text}")
                    await support.update_one({'_id':sess['_id']},{'$set':{'admin_message_id':sent.message_id}})
                except Exception:
                    pass
            return await m.answer('📨 Message sent to support.')


async def screenshot(m:Message):
    dep=await deposits.find_one({'user_id':m.from_user.id,'status':'awaiting_screenshot'},sort=[('created_at',-1)])
    if not dep: return await m.answer('Start a deposit first.')
    if dep.get('expires_at') and datetime.now(timezone.utc) > dep['expires_at']:
        await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'expired'}})
        return await m.answer('⏱️ This deposit request has expired. Please start a new deposit.')
    await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'pending_review','screenshot_file_id':m.photo[-1].file_id}})
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Approve',callback_data=f"dep_ok:{dep['_id']}"),InlineKeyboardButton(text='❌ Reject',callback_data=f"dep_no:{dep['_id']}")]])
    for aid in ADMIN_IDS:
        await bot.send_photo(aid,m.photo[-1].file_id,caption=f"💳 <b>Deposit Request</b>\n👤 Buyer: {m.from_user.full_name}\n🔗 Username: @{m.from_user.username or '—'}\n🆔 User ID: <code>{m.from_user.id}</code>\n💰 Amount: ₹{dep['amount']:.2f}\n🧾 Transaction ID: <code>{dep.get('transaction_id') or '—'}</code>",reply_markup=kb)
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

async def require_join(m):
    if not await is_joined(m.from_user.id):
        await send_join_gate(m)
        return False
    return True

@router.message(Command('buy'))
async def cmd_buy(m:Message):
    if not await require_join(m): return
    await show_products_for_message(m)

@router.message(Command('wallet'))
async def cmd_wallet(m:Message):
    if not await require_join(m): return
    u=await users.find_one({'_id':m.from_user.id}); bal=float((u or {}).get('balance',0))
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Deposit',callback_data='deposit')],[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]])
    await m.answer(f'💰 <b>Wallet</b>\n\nBalance: <b>₹{bal:.2f}</b>',reply_markup=kb)

@router.message(Command('orders'))
async def cmd_orders(m:Message):
    if not await require_join(m): return
    docs=await orders.find({'user_id':m.from_user.id}).sort('created_at',-1).to_list(10)
    if not docs: return await m.answer('📦 <b>My Orders</b>\n\nNo orders yet.')
    lines=['📦 <b>My Orders</b>','']
    for o in docs:
        lines.append(f"• {o.get('product_name','Product')} — ₹{float(o.get('amount',0)):.2f} — {o.get('status','unknown')}")
    await m.answer('\n'.join(lines))

@router.message(Command('support'))
async def cmd_support(m:Message):
    if not await require_join(m): return
    await m.answer('💬 <b>Support</b>\n\nSend your message here. Support sessions are limited to 5 minutes.')

async def show_products_for_message(m:Message):
    ps=await products.find({'active':True}).to_list(30)
    rows=[[InlineKeyboardButton(text=f"{p['name']} — ₹{p['price']:.2f} • Stock: {int(p.get('stock',0))}",callback_data=f"buy:{p['_id']}")] for p in ps if int(p.get('stock',0)) > 0]
    rows.append([InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')])
    await m.answer('🛒 <b>Products</b>\n\nChoose a product:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.message(Command('setstock'))
async def setstock(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    parts=m.text.split(maxsplit=2)
    if len(parts)!=3: return await m.answer('Usage: /setstock <product_id> <quantity>')
    try: pid=ObjectId(parts[1]); qty=int(parts[2])
    except: return await m.answer('Invalid product ID or quantity.')
    if qty<0: return await m.answer('Quantity cannot be negative.')
    r=await products.update_one({'_id':pid},{'$set':{'stock':qty}})
    if not r.matched_count: return await m.answer('Product not found.')
    await m.answer(f'✅ Stock set to {qty}.')

@router.message(Command('stock'))
async def stock(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    docs=await products.find({}).to_list(50)
    if not docs: return await m.answer('No products found.')
    lines=['📦 <b>Product Inventory</b>','']
    for x in docs:
        lines.append(f"• {x.get('name','Product')} — stock: {int(x.get('stock',0))} — {'🟢' if x.get('active',True) else '🔴'}")
    await m.answer('\n'.join(lines))

async def find_user_by_arg(arg):
    arg=arg.strip()
    if arg.startswith('@'):
        return await users.find_one({'username':arg[1:]})
    try: return await users.find_one({'_id':int(arg)})
    except: return None

@router.message(Command('balance'))
async def cmd_balance(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    parts=m.text.split(maxsplit=1)
    if len(parts)<2: return await m.answer('Usage: /balance <telegram_id or @username>')
    u=await find_user_by_arg(parts[1]);
    if not u: return await m.answer('User not found.')
    await m.answer(f"👤 <b>User Balance</b>\nID: <code>{u['_id']}</code>\nUsername: @{u.get('username') or '—'}\nBalance: <b>₹{float(u.get('balance',0)):.2f}</b>")

@router.message(Command('addfunds'))
async def cmd_addfunds(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    parts=m.text.split()
    if len(parts)!=3: return await m.answer('Usage: /addfunds <telegram_id or @username> <amount>')
    u=await find_user_by_arg(parts[1])
    if not u: return await m.answer('User not found.')
    try: amount=float(parts[2])
    except: return await m.answer('Invalid amount.')
    if amount<=0: return await m.answer('Amount must be positive.')
    await users.update_one({'_id':u['_id']},{'$inc':{'balance':amount}})
    await db.fund_history.insert_one({'user_id':u['_id'],'admin_id':m.from_user.id,'action':'add','amount':amount,'created_at':datetime.now(timezone.utc)})
    await m.answer(f'✅ Added ₹{amount:.2f}.')
    try: await bot.send_message(u['_id'],f'💰 Admin added ₹{amount:.2f} to your wallet.')
    except: pass

@router.message(Command('removefunds'))
async def cmd_removefunds(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    parts=m.text.split()
    if len(parts)!=3: return await m.answer('Usage: /removefunds <telegram_id or @username> <amount>')
    u=await find_user_by_arg(parts[1])
    if not u: return await m.answer('User not found.')
    try: amount=float(parts[2])
    except: return await m.answer('Invalid amount.')
    if amount<=0: return await m.answer('Amount must be positive.')
    if float(u.get('balance',0))<amount: return await m.answer('Insufficient user balance.')
    await users.update_one({'_id':u['_id']},{'$inc':{'balance':-amount}})
    await db.fund_history.insert_one({'user_id':u['_id'],'admin_id':m.from_user.id,'action':'remove','amount':amount,'created_at':datetime.now(timezone.utc)})
    await m.answer(f'✅ Removed ₹{amount:.2f}.')
    try: await bot.send_message(u['_id'],f'💰 ₹{amount:.2f} was removed from your wallet by admin.')
    except: pass

@router.callback_query(F.data=='products')
async def show_products(c:CallbackQuery):
    if not await is_joined(c.from_user.id):
        await c.answer('❌ Please join the channel first.', show_alert=True)
        return
    await save_user(c.from_user)
    ps=await products.find({'active':True}).to_list(30)
    rows=[[InlineKeyboardButton(text=f"{p['name']} — ₹{p['price']:.2f} • Stock: {int(p.get('stock',0))}",callback_data=f"buy:{p['_id']}")] for p in ps if int(p.get('stock',0)) > 0]
    rows.append([InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')])
    await c.answer()
    await c.message.answer('🛒 <b>Products</b>\n\nChoose a product:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data.startswith('buy:'))
async def buy(c:CallbackQuery):
    try: pid=ObjectId(c.data.split(':')[1])
    except: return await c.answer('Invalid product.',show_alert=True)
    p=await products.find_one({'_id':pid,'active':True})
    if not p: return await c.answer('Unavailable.',show_alert=True)
    stock=int(p.get('stock',0))
    if stock<=0: return await c.answer('Out of stock.',show_alert=True)
    u=await users.find_one({'_id':c.from_user.id}); bal=float((u or {}).get('balance',0))
    if bal<float(p['price']): return await c.answer('Insufficient wallet balance.',show_alert=True)
    # Atomically reserve one unit so two buyers cannot purchase the same stock unit.
    reserved=await products.find_one_and_update({'_id':pid,'active':True,'stock':{'$gt':0}},{'$inc':{'stock':-1}})
    if not reserved: return await c.answer('Out of stock.',show_alert=True)
    await users.update_one({'_id':c.from_user.id},{'$inc':{'balance':-float(p['price'])}})
    o={'user_id':c.from_user.id,'product_id':p['_id'],'product_name':p['name'],'amount':float(p['price']),'status':'pending_admin','created_at':datetime.now(timezone.utc)}
    r=await orders.insert_one(o)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Confirm',callback_data=f"ord_ok:{r.inserted_id}"),InlineKeyboardButton(text='↩️ Refund',callback_data=f"ord_ref:{r.inserted_id}")]])
    for aid in ADMIN_IDS:
        await bot.send_message(aid,f"🛒 <b>New Order</b>\nBuyer: {c.from_user.full_name}\nUser ID: <code>{c.from_user.id}</code>\nProduct: <b>{p['name']}</b>\nAmount: ₹{float(p['price']):.2f}\nRemaining stock: {stock-1}\nOrder ID: <code>{r.inserted_id}</code>",reply_markup=kb)
    await c.answer('Purchase created.')
    await c.message.answer(f"✅ <b>Order created</b>\n\nProduct: {p['name']}\nAmount: ₹{float(p['price']):.2f}\nOrder ID: <code>{r.inserted_id}</code>\n\nAdmin will confirm your order.")

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
    if not await is_joined(c.from_user.id):
        await c.answer('❌ Please join the channel first.', show_alert=True)
        return
    docs=await orders.find({'user_id':c.from_user.id}).sort('created_at',-1).to_list(10)
    text='📦 <b>My Orders</b>\n\n'+('\n'.join(f"• {o['product_name']} — ₹{o['amount']:.2f} — {o['status']}" for o in docs) if docs else 'No orders yet.')
    await c.answer()
    await c.message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]]))

@router.callback_query(F.data=='support')
async def support_start(c:CallbackQuery):
    if not await is_joined(c.from_user.id):
        await c.answer('❌ Please join the channel first.', show_alert=True)
        return
    now=datetime.now(timezone.utc)
    await support.update_many({'user_id':c.from_user.id,'status':'open'},{'$set':{'status':'closed','closed_at':now}})
    await support.insert_one({'user_id':c.from_user.id,'status':'open','expires_at':now+timedelta(minutes=5),'created_at':now})
    await c.message.answer('💬 <b>Support session started.</b>\nYou have 5 minutes to send your payment/order questions.')
    await c.answer()

async def cleanup():
    while True:
        now=datetime.now(timezone.utc)
        expired=await support.find({'status':'open','expires_at':{'$lte':now}}).to_list(50)
        for sess in expired:
            await support.update_one({'_id':sess['_id']},{'$set':{'status':'closed','closed_at':now}})
            try: await bot.send_message(sess['user_id'],'⏱️ <b>Your service time has ended.</b>\nPlease start a new support session if you need further help.')
            except Exception: pass
        await asyncio.sleep(10)

async def main():
    logging.basicConfig(level=logging.INFO)
    await asyncio.gather(dp.start_polling(bot),cleanup())

if __name__=='__main__': asyncio.run(main())
