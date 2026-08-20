import asyncio, logging, os
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

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
users, deposits, products, orders, support, settings, admin_states=(db[x] for x in ('users','deposits','products','orders','support','settings','admin_states'))

async def joined_or_gate(c_or_m):
    uid=c_or_m.from_user.id
    if not await is_joined(uid):
        if isinstance(c_or_m, CallbackQuery):
            await c_or_m.answer('❌ Please join the channel first.', show_alert=True)
            await bot.send_message(uid, '📢 Please join our channel first.', reply_markup=join_kb())
        else:
            await send_join_gate(c_or_m)
        return False
    return True

async def get_admin_state(admin_id:int):
    d=await admin_states.find_one({'_id':admin_id})
    if not d: return None
    exp=d.get('expires_at')
    if exp:
        if exp.tzinfo is None: exp=exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            await admin_states.delete_one({'_id':admin_id}); return None
    return d.get('action')

async def set_admin_state(admin_id:int, action:str):
    await admin_states.update_one({'_id':admin_id},{'$set':{'action':action,'expires_at':datetime.now(timezone.utc)+timedelta(minutes=5)}},upsert=True)

async def clear_admin_state(admin_id:int):
    await admin_states.delete_one({'_id':admin_id})

def stock_value(p):
    return int(p.get('stock',0))

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
    if not await joined_or_gate(c): return
    await c.answer()
    await bot.send_message(c.from_user.id,'🛍️ <b>Digital Store</b>\n\nChoose an option:',reply_markup=main_kb())

@router.callback_query(F.data=='wallet')
async def wallet(c:CallbackQuery):
    if not await joined_or_gate(c): return
    u=await users.find_one({'_id':c.from_user.id}); bal=float((u or {}).get('balance',0))
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Deposit',callback_data='deposit')],[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]])
    await c.answer(); await bot.send_message(c.from_user.id,f'💰 <b>Wallet</b>\n\nBalance: <b>₹{bal:.2f}</b>',reply_markup=kb)

@router.callback_query(F.data=='deposit')
async def deposit(c:CallbackQuery):
    if not await joined_or_gate(c): return
    p=await get_payment_settings()
    text=(f"💳 <b>Deposit</b>\n\nSend any amount between ₹{float(p.get('min_deposit',1)):.2f}"
          f" and {('₹'+format(float(p['max_deposit']),'.2f')) if float(p.get('max_deposit',0))>0 else 'No maximum limit'}.\n\n"
          f"UPI ID: <code>{p['upi_id']}</code>\n\n{p['instructions']}\n\nAfter payment, send the Transaction ID.")
    await c.answer()
    if p.get('qr_file_id'):
        await bot.send_photo(c.from_user.id,p['qr_file_id'],caption=text)
    else:
        await bot.send_message(c.from_user.id,text)

@router.message(F.text.regexp(r'^\d+(\.\d{1,2})?$'))
async def amount(m:Message):
    # If the user is currently expected to send a transaction ID, ALWAYS
    # treat the message as the transaction ID, even when it is only digits.
    # This prevents numeric transaction IDs from being mistaken for deposit
    # amounts or admin min/max settings.
    active_dep=await deposits.find_one({'user_id':m.from_user.id,'status':'awaiting_txid'},sort=[('created_at',-1)])
    if active_dep:
        exp=active_dep.get('expires_at'); now=datetime.now(timezone.utc)
        if exp and exp.tzinfo is None: exp=exp.replace(tzinfo=timezone.utc)
        if exp and exp<=now:
            await deposits.update_one({'_id':active_dep['_id']},{'$set':{'status':'expired'}})
            return await m.answer('⏱️ This deposit request has expired. Start a new deposit.')
        await deposits.update_one({'_id':active_dep['_id']},{'$set':{'status':'awaiting_screenshot','transaction_id':m.text.strip()}})
        return await m.answer('🧾 Transaction ID received. Now send the payment screenshot.')

    if m.from_user.id in ADMIN_IDS:
        action=await get_admin_state(m.from_user.id)
        if action in ('min','max'):
            v=float(m.text.strip())
            if v<0: return await m.answer('Amount cannot be negative.')
            p=await get_payment_settings()
            mn=float(p.get('min_deposit',1)); mx=float(p.get('max_deposit',0))
            if action=='min' and mx>0 and v>mx: return await m.answer('Minimum cannot be greater than maximum.')
            if action=='max' and v>0 and v<mn: return await m.answer('Maximum cannot be less than minimum.')
            field='min_deposit' if action=='min' else 'max_deposit'
            await settings.update_one({'_id':'payment'},{'$set':{field:v}})
            await clear_admin_state(m.from_user.id)
            return await m.answer(f"✅ {'Minimum' if action=='min' else 'Maximum'} Deposit set to " + ('No limit.' if action=='max' and v==0 else f'₹{v:.2f}.'))
    await save_user(m.from_user)
    amt=float(m.text)
    p=await get_payment_settings()
    if amt<=0: return await m.answer('Enter a valid amount.')
    if amt<float(p.get('min_deposit',1)): return await m.answer(f"Minimum deposit is ₹{float(p.get('min_deposit',1)):.2f}.")
    if float(p.get('max_deposit',0))>0 and amt>float(p['max_deposit']): return await m.answer(f"Maximum deposit is ₹{float(p['max_deposit']):.2f}.")
    await deposits.insert_one({'user_id':m.from_user.id,'amount':amt,'status':'awaiting_txid','created_at':datetime.now(timezone.utc),'expires_at':datetime.now(timezone.utc)+timedelta(minutes=30)})
    text=(f"💳 <b>Deposit Request</b>\nAmount: ₹{amt:.2f}\nUPI: <code>{p['upi_id']}</code>\n\n"
          f"{p['instructions']}\n\n⏱️ Request expires in <b>30 minutes</b>.\nAfter payment, send the Transaction ID.")
    if p.get('qr_file_id'): await bot.send_photo(m.chat.id,p['qr_file_id'],caption=text)
    else: await m.answer(text)

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
    await set_admin_state(c.from_user.id, action)
    await c.message.answer('✏️ '+prompts[action])
    await c.answer()

@router.message(F.text & ~F.text.startswith('/') & ~F.reply_to_message)
async def admin_payment_text(m:Message):
    # Transaction IDs and support messages are handled here only when a user has an active deposit/support flow.
    if m.from_user.id in ADMIN_IDS:
        action=await get_admin_state(m.from_user.id)
        if action in ('upi','text','min','max'):
            value=m.text.strip()
            if action=='upi':
                await settings.update_one({'_id':'payment'},{'$set':{'upi_id':value}}); await clear_admin_state(m.from_user.id)
                return await m.answer(f'✅ UPI ID changed to <code>{value}</code>.')
            if action=='text':
                await settings.update_one({'_id':'payment'},{'$set':{'instructions':value}}); await clear_admin_state(m.from_user.id)
                return await m.answer('✅ Payment Instructions updated.')
            if action in ('min','max'):
                try: v=float(value)
                except: return await m.answer('Send a number, e.g. 100.')
                p=await get_payment_settings(); mn=float(p.get('min_deposit',1)); mx=float(p.get('max_deposit',0))
                if v<0: return await m.answer('Amount cannot be negative.')
                if action=='min' and mx>0 and v>mx: return await m.answer('Minimum cannot be greater than maximum.')
                if action=='max' and v>0 and v<mn: return await m.answer('Maximum cannot be less than minimum.')
                await settings.update_one({'_id':'payment'},{'$set':{'min_deposit':v} if action=='min' else {'max_deposit':v}}); await clear_admin_state(m.from_user.id)
                return await m.answer(f"✅ {'Minimum' if action=='min' else 'Maximum'} Deposit set to " + ('No limit.' if action=='max' and v==0 else f'₹{v:.2f}.'))
    # Active deposit transaction ID
    dep=await deposits.find_one({'user_id':m.from_user.id,'status':'awaiting_txid'},sort=[('created_at',-1)])
    if dep:
        exp=dep.get('expires_at'); now=datetime.now(timezone.utc)
        if exp and exp.tzinfo is None: exp=exp.replace(tzinfo=timezone.utc)
        if exp and exp<=now:
            await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'expired'}}); return await m.answer('⏱️ This deposit request has expired. Start a new deposit.')
        await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'awaiting_screenshot','transaction_id':m.text.strip()}})
        return await m.answer('🧾 Transaction ID received. Now send the payment screenshot.')
    # Support relay: user -> admins
    sess=await support.find_one({'user_id':m.from_user.id,'status':'open'},sort=[('created_at',-1)])
    if sess:
        exp=sess.get('expires_at'); now=datetime.now(timezone.utc)
        if exp and exp.tzinfo is None: exp=exp.replace(tzinfo=timezone.utc)
        if exp and exp<=now:
            await support.update_one({'_id':sess['_id']},{'$set':{'status':'closed','closed_at':now}}); return await m.answer('⏱️ Your service time has ended.')
        for aid in ADMIN_IDS:
            try: await bot.send_message(aid,f'💬 <b>Support message</b>\n👤 {m.from_user.full_name} (@{m.from_user.username or "no_username"})\n🆔 <code>{m.from_user.id}</code>\n\n{m.text}')
            except Exception: pass
        return await m.answer('📨 Message sent to support.')

@router.message(F.photo)
async def screenshot(m:Message):
    if m.from_user.id in ADMIN_IDS and await get_admin_state(m.from_user.id)=='qr':
        await settings.update_one({'_id':'payment'},{'$set':{'qr_file_id':m.photo[-1].file_id}}); await clear_admin_state(m.from_user.id)
        return await m.answer('✅ QR Code uploaded/changed successfully.')
    dep=await deposits.find_one({'user_id':m.from_user.id,'status':'awaiting_screenshot'},sort=[('created_at',-1)])
    if not dep: return await m.answer('Start a deposit first.')
    exp=dep.get('expires_at'); now=datetime.now(timezone.utc)
    if exp and exp.tzinfo is None: exp=exp.replace(tzinfo=timezone.utc)
    if exp and exp<=now:
        await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'expired'}}); return await m.answer('⏱️ This deposit request has expired. Start a new deposit.')
    await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'pending_review','screenshot_file_id':m.photo[-1].file_id}})
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Approve',callback_data=f"dep_ok:{dep['_id']}"),InlineKeyboardButton(text='❌ Decline',callback_data=f"dep_no:{dep['_id']}")]])
    username=f'@{m.from_user.username}' if m.from_user.username else 'No username'
    for aid in ADMIN_IDS:
        try:
            await bot.send_photo(aid,m.photo[-1].file_id,caption=f"💳 <b>Deposit Request</b>\n👤 {m.from_user.full_name} ({username})\n🆔 <code>{m.from_user.id}</code>\n💰 Amount: ₹{dep['amount']:.2f}\n🧾 Transaction ID: <code>{dep.get('transaction_id','')}</code>",reply_markup=kb)
        except Exception as e:
            logging.exception('Could not send deposit request to admin %s: %s', aid, e)
    await m.answer('📨 Screenshot received. Your request has been sent to the admin for approval.')

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
    if not await joined_or_gate(c): return
    ps=await products.find({'active':True,'stock':{'$gt':0}}).to_list(30)
    rows=[[InlineKeyboardButton(text=f"{p['name']} — ₹{p['price']:.2f} ({int(p.get('stock',0))} left)",callback_data=f"buy:{p['_id']}")] for p in ps]
    rows.append([InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')])
    await c.answer(); await bot.send_message(c.from_user.id,'🛒 <b>Products</b>\n\nChoose a product:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data.startswith('buy:'))
async def buy(c:CallbackQuery):
    if not await joined_or_gate(c): return
    pid=ObjectId(c.data.split(':')[1])
    # Atomic stock reservation: only one buyer can take the last stock item.
    p=await products.find_one_and_update({'_id':pid,'active':True,'stock':{'$gt':0}},{'$inc':{'stock':-1}} ,return_document=ReturnDocument.AFTER)
    if not p: return await c.answer('Out of stock.',show_alert=True)
    u=await users.find_one({'_id':c.from_user.id}); bal=float((u or {}).get('balance',0))
    if bal<p['price']:
        await products.update_one({'_id':pid},{'$inc':{'stock':1}})
        return await c.answer('Insufficient wallet balance.',show_alert=True)
    await users.update_one({'_id':c.from_user.id},{'$inc':{'balance':-p['price']}})
    o={'user_id':c.from_user.id,'product_id':p['_id'],'product_name':p['name'],'amount':p['price'],'status':'pending_admin','created_at':datetime.now(timezone.utc)}
    r=await orders.insert_one(o)
    for aid in ADMIN_IDS:
        try: await bot.send_message(aid,f"🛒 <b>New Order</b>\n👤 {c.from_user.full_name}\n🆔 <code>{c.from_user.id}</code>\nProduct: <b>{p['name']}</b>\nAmount: ₹{p['price']:.2f}\nRemaining stock: {max(0,int(p.get('stock',1))-1)}\nOrder ID: <code>{r.inserted_id}</code>")
        except Exception: pass
    await c.answer('Purchase successful!')
    await bot.send_message(c.from_user.id,f"✅ <b>Order created</b>\n\nProduct: {p['name']}\nAmount: ₹{p['price']:.2f}\nOrder ID: <code>{r.inserted_id}</code>\n\nAdmin will confirm your order.")

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
    await products.update_one({'_id':o['product_id']},{'$inc':{'stock':1},'$set':{'active':True}})
    await bot.send_message(o['user_id'],f'↩️ Order <code>{oid}</code> refunded to your wallet.')
    await c.message.edit_reply_markup(reply_markup=None); await c.answer('Refunded')

@router.callback_query(F.data=='orders')
async def orders_list(c:CallbackQuery):
    docs=await orders.find({'user_id':c.from_user.id}).sort('created_at',-1).to_list(10)
    text='📦 <b>My Orders</b>\n\n'+('\n'.join(f"• {o['product_name']} — ₹{o['amount']:.2f} — {o['status']}" for o in docs) if docs else 'No orders yet.')
    await c.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]])); await c.answer()

@router.callback_query(F.data=='support')
async def support_start(c:CallbackQuery):
    if not await joined_or_gate(c): return
    now=datetime.now(timezone.utc)
    await support.update_many({'user_id':c.from_user.id,'status':'open'},{'$set':{'status':'closed','closed_at':now}})
    await support.insert_one({'user_id':c.from_user.id,'status':'open','expires_at':now+timedelta(minutes=5),'created_at':now})
    await bot.send_message(c.from_user.id,'💬 <b>Support session started.</b>\nYou have 5 minutes to send your payment/order questions.')
    await c.answer()

@router.message(Command('stock'))
async def stock_cmd(m:Message):
    if m.from_user.id not in ADMIN_IDS: return await m.answer('Not authorized.')
    ps=await products.find({}).to_list(100)
    if not ps: return await m.answer('No products found.')
    await m.answer('📦 <b>Stock</b>\n\n'+'\n'.join(f"• {p['name']}: {int(p.get('stock',0))}" for p in ps))

@router.message(Command('setstock'))
async def setstock_cmd(m:Message):
    if m.from_user.id not in ADMIN_IDS: return await m.answer('Not authorized.')
    parts=m.text.split(maxsplit=2)
    if len(parts)!=3: return await m.answer('Usage: /setstock PRODUCT_ID QUANTITY')
    try: pid=ObjectId(parts[1]); qty=int(parts[2])
    except: return await m.answer('Invalid product ID or quantity.')
    if qty<0: return await m.answer('Quantity cannot be negative.')
    r=await products.update_one({'_id':pid},{'$set':{'stock':qty,'active':qty>0}})
    if not r.matched_count: return await m.answer('Product not found.')
    await m.answer(f'✅ Stock updated to {qty}.')

@router.message(Command('broadcast'))
async def broadcast_cmd(m:Message):
    if m.from_user.id not in ADMIN_IDS: return await m.answer('Not authorized.')
    src=m.reply_to_message
    if not src:
        return await m.answer('Reply to the message you want to broadcast, then send /broadcast.')
    sent=failed=0
    async for u in users.find({}, {'_id':1}):
        uid=u['_id']
        try:
            await bot.copy_message(uid, m.chat.id, src.message_id)
            sent+=1
        except Exception:
            failed+=1
    await m.answer(f'📢 <b>Broadcast completed</b>\n\n✅ Sent: {sent}\n❌ Failed: {failed}')

@router.message(F.reply_to_message, F.from_user.id.in_(ADMIN_IDS))
async def admin_reply_to_support(m:Message):
    replied=m.reply_to_message
    text=replied.text or replied.caption or ''
    import re
    match=re.search(r'ID:</code>\s*(\d+)', text)
    if not match: return
    uid=int(match.group(1))
    sess=await support.find_one({'user_id':uid,'status':'open'},sort=[('created_at',-1)])
    if not sess: return await m.answer('Support session is closed.')
    exp=sess.get('expires_at'); now=datetime.now(timezone.utc)
    if exp and exp.tzinfo is None: exp=exp.replace(tzinfo=timezone.utc)
    if exp and exp<=now:
        await support.update_one({'_id':sess['_id']},{'$set':{'status':'closed','closed_at':now}}); return await m.answer('Support session expired.')
    try:
        await bot.copy_message(uid,m.chat.id,m.message_id)
        await m.answer('✅ Reply sent.')
    except Exception as e:
        await m.answer(f'❌ Could not send reply: {e}')

async def cleanup():
    while True:
        now=datetime.now(timezone.utc)
        expired=await support.find({'status':'open','expires_at':{'$lte':now}}).to_list(50)
        for sess in expired:
            await support.update_one({'_id':sess['_id']},{'$set':{'status':'closed','closed_at':now}})
            try: await bot.send_message(sess['user_id'],'⏱️ <b>Your service time has ended.</b>')
            except Exception: pass
        await admin_states.delete_many({'expires_at':{'$lte':now}})
        await asyncio.sleep(10)

async def main():
    logging.basicConfig(level=logging.INFO)
    await asyncio.gather(dp.start_polling(bot),cleanup())

if __name__=='__main__': asyncio.run(main())
