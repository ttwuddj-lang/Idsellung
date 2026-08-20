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
users, deposits, products, orders, support, settings, admin_states=(db[x] for x in ('users','deposits','products','orders','support','settings','admin_states'))

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
    if not await is_joined(c.from_user.id): return await send_join_gate(c.message)
    await c.message.answer('🛍️ <b>Digital Store</b>\n\nChoose an option:',reply_markup=main_kb()); await c.answer()

@router.callback_query(F.data=='wallet')
async def wallet(c:CallbackQuery):
    if not await is_joined(c.from_user.id): return await send_join_gate(c.message)
    u=await users.find_one({'_id':c.from_user.id}); bal=float((u or {}).get('balance',0))
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Deposit',callback_data='deposit')],[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]])
    await c.message.answer(f'💰 <b>Wallet</b>\n\nBalance: <b>₹{bal:.2f}</b>',reply_markup=kb); await c.answer()

@router.callback_query(F.data=='deposit')
async def deposit(c:CallbackQuery):
    if not await is_joined(c.from_user.id): return await send_join_gate(c.message)
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
async def amount_or_transaction(m:Message):
    dep = await deposits.find_one({'user_id':m.from_user.id,'status':'awaiting_transaction'},sort=[('created_at',-1)])
    if dep:
        expires=dep.get('expires_at')
        if expires and expires <= datetime.now(timezone.utc):
            await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'expired'}})
            return await m.answer('⏱️ This deposit request has expired. Please start a new deposit.')
        await deposits.update_one({'_id':dep['_id']},{'$set':{'transaction_id':m.text.strip(),'status':'awaiting_screenshot'}})
        return await m.answer('✅ Transaction ID received. Now send your payment screenshot here.')
    if m.from_user.id in ADMIN_IDS:
        st=await admin_states.find_one({'_id':m.from_user.id})
        if st and st.get('expires_at') and st['expires_at'] > datetime.now(timezone.utc) and st.get('action') in ('min','max'):
            v=float(m.text.strip())
            p=await get_payment_settings(); mn=float(p.get('min_deposit',1)); mx=float(p.get('max_deposit',0))
            if v<0: return await m.answer('Amount cannot be negative.')
            if st['action']=='min' and mx>0 and v>mx: return await m.answer(f'Minimum cannot be greater than maximum ₹{mx:.2f}.')
            if st['action']=='max' and v>0 and v<mn: return await m.answer(f'Maximum cannot be less than minimum ₹{mn:.2f}.')
            field='min_deposit' if st['action']=='min' else 'max_deposit'
            await settings.update_one({'_id':'payment'},{'$set':{field:v}},upsert=True)
            await admin_states.delete_one({'_id':m.from_user.id})
            label='Minimum' if st['action']=='min' else 'Maximum'
            return await m.answer(f"✅ {label} Deposit set to " + ('No limit.' if st['action']=='max' and v==0 else f'₹{v:.2f}.'))
    await save_user(m.from_user)
    amt=float(m.text); p=await get_payment_settings()
    if amt<=0: return await m.answer('Enter a valid amount.')
    if amt<float(p.get('min_deposit',1)): return await m.answer(f"Minimum deposit is ₹{float(p.get('min_deposit',1)):.2f}.")
    if float(p.get('max_deposit',0))>0 and amt>float(p['max_deposit']): return await m.answer(f"Maximum deposit is ₹{float(p['max_deposit']):.2f}.")
    now=datetime.now(timezone.utc); expires=now+timedelta(minutes=30)
    await deposits.insert_one({'user_id':m.from_user.id,'amount':amt,'status':'awaiting_transaction','created_at':now,'expires_at':expires})
    text=(f"💳 <b>Deposit Request</b>\nAmount: ₹{amt:.2f}\nUPI: <code>{p['upi_id']}</code>\n\n"
          f"{p['instructions']}\n\n⏱️ Request expires in <b>30 minutes</b>.\n"
          "After payment, send the transaction ID, then send the payment screenshot.")
    if p.get('qr_file_id'): await bot.send_photo(m.chat.id,p['qr_file_id'],caption=text)
    else: await m.answer(text)


@router.message(F.text=='/admin')
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
    await admin_states.update_one({'_id':c.from_user.id},{'$set':{'action':action,'expires_at':datetime.now(timezone.utc)+timedelta(minutes=5)}},upsert=True)
    await c.message.answer('✏️ '+prompts[action])
    await c.answer()

@router.message(F.photo)
async def payment_or_qr_photo(m:Message):
    if m.from_user.id in ADMIN_IDS:
        p=await get_payment_settings()
        st=await admin_states.find_one({'_id':m.from_user.id})
        if st and st.get('action')=='qr' and st.get('expires_at',datetime.min.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc):
            await settings.update_one({'_id':'payment'},{'$set':{'qr_file_id':m.photo[-1].file_id}},upsert=True)
            await admin_states.delete_one({'_id':m.from_user.id})
            return await m.answer('✅ QR Code uploaded/changed successfully.')
    dep=await deposits.find_one({'user_id':m.from_user.id,'status':'awaiting_screenshot'},sort=[('created_at',-1)])
    if not dep: return await m.answer('First send the transaction ID for your active deposit.')
    
    if dep.get('expires_at') and dep['expires_at'] <= datetime.now(timezone.utc):
        await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'expired'}})
        return await m.answer('⏱️ This deposit request has expired. Please start a new deposit.')
    await deposits.update_one({'_id':dep['_id']},{'$set':{'status':'pending_review','screenshot_file_id':m.photo[-1].file_id}})
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Approve',callback_data=f"dep_ok:{dep['_id']}"),InlineKeyboardButton(text='❌ Reject',callback_data=f"dep_no:{dep['_id']}")]])
    for aid in ADMIN_IDS:
        caption=(f"💳 <b>Deposit Request</b>\nBuyer: {m.from_user.full_name}\n"
                 f"User ID: <code>{m.from_user.id}</code>\nAmount: ₹{dep['amount']:.2f}\n"
                 f"Transaction ID: <code>{dep.get('transaction_id','Not provided')}</code>")
        await bot.send_photo(aid,m.photo[-1].file_id,caption=caption,reply_markup=kb)
    await m.answer('📨 Screenshot received. Admin will verify it.')

@router.message(F.text)
async def admin_payment_text(m:Message):
    if m.from_user.id not in ADMIN_IDS: return
    st=await admin_states.find_one({'_id':m.from_user.id})
    if not st or not st.get('expires_at') or st['expires_at'] <= datetime.now(timezone.utc): return
    action=st.get('action'); value=m.text.strip()
    if action=='upi':
        await settings.update_one({'_id':'payment'},{'$set':{'upi_id':value}},upsert=True); await admin_states.delete_one({'_id':m.from_user.id})
        return await m.answer(f'✅ UPI ID changed to <code>{value}</code>.')
    if action=='text':
        await settings.update_one({'_id':'payment'},{'$set':{'instructions':value}},upsert=True); await admin_states.delete_one({'_id':m.from_user.id})
        return await m.answer('✅ Payment Instructions updated.')
    if action in ('min','max'):
        try: v=float(value)
        except: return await m.answer('Send a number, e.g. 100.')
        p=await get_payment_settings(); mn=float(p.get('min_deposit',1)); mx=float(p.get('max_deposit',0))
        if v<0: return await m.answer('Amount cannot be negative.')
        if action=='min' and mx>0 and v>mx: return await m.answer(f'Minimum cannot be greater than maximum ₹{mx:.2f}.')
        if action=='max' and v>0 and v<mn: return await m.answer(f'Maximum cannot be less than minimum ₹{mn:.2f}.')
        field='min_deposit' if action=='min' else 'max_deposit'
        await settings.update_one({'_id':'payment'},{'$set':{field:v}},upsert=True); await admin_states.delete_one({'_id':m.from_user.id})
        label='Minimum' if action=='min' else 'Maximum'
        return await m.answer(f'✅ {label} Deposit set to '+('No limit.' if action=='max' and v==0 else f'₹{v:.2f}.'))



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
    if not await is_joined(c.from_user.id): return await send_join_gate(c.message)
    ps=await products.find({'active':True}).to_list(30)
    rows=[[InlineKeyboardButton(text=f"{p['name']} — ₹{p['price']:.2f}",callback_data=f"buy:{p['_id']}")] for p in ps]
    rows.append([InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')])
    await c.message.answer('🛒 <b>Products</b>\n\nChoose a product:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@router.callback_query(F.data.startswith('buy:'))
async def buy(c:CallbackQuery):
    if not await is_joined(c.from_user.id): return await send_join_gate(c.message)
    p=await products.find_one({'_id':ObjectId(c.data.split(':')[1]),'active':True})
    if not p: return await c.answer('Unavailable.',show_alert=True)
    u=await users.find_one({'_id':c.from_user.id}); bal=float((u or {}).get('balance',0))
    if bal<p['price']: return await c.answer('Insufficient wallet balance.',show_alert=True)
    await users.update_one({'_id':c.from_user.id},{'$inc':{'balance':-p['price']}})
    o={'user_id':c.from_user.id,'product_id':p['_id'],'product_name':p['name'],'amount':p['price'],'status':'pending_admin','created_at':datetime.now(timezone.utc)}
    r=await orders.insert_one(o)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Confirm',callback_data=f"ord_ok:{r.inserted_id}"),InlineKeyboardButton(text='↩️ Refund',callback_data=f"ord_ref:{r.inserted_id}")]])
    for aid in ADMIN_IDS:
        await bot.send_message(aid,f"🛒 <b>New Order</b>\nBuyer: {c.from_user.full_name}\nUser ID: <code>{c.from_user.id}</code>\nProduct: <b>{p['name']}</b>\nAmount: ₹{p['price']:.2f}\nOrder ID: <code>{r.inserted_id}</code>",reply_markup=kb)
    await c.message.edit_text(f"✅ <b>Order created</b>\n\nProduct: {p['name']}\nAmount: ₹{p['price']:.2f}\nOrder ID: <code>{r.inserted_id}</code>\n\nAdmin will confirm your order.")
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
    if not await is_joined(c.from_user.id): return await send_join_gate(c.message)
    docs=await orders.find({'user_id':c.from_user.id}).sort('created_at',-1).to_list(10)
    text='📦 <b>My Orders</b>\n\n'+('\n'.join(f"• {o['product_name']} — ₹{o['amount']:.2f} — {o['status']}" for o in docs) if docs else 'No orders yet.')
    await c.message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]])); await c.answer()

async def require_join_message(m:Message):
    if not await is_joined(m.from_user.id):
        await send_join_gate(m)
        return False
    return True

@router.message(Command("buy"))
async def cmd_buy(m:Message):
    if not await require_join_message(m): return
    ps=await products.find({'active':True}).to_list(30)
    rows=[[InlineKeyboardButton(text=f"{p['name']} — ₹{p['price']:.2f}",callback_data=f"buy:{p['_id']}")] for p in ps]
    rows.append([InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')])
    await m.answer('🛒 <b>Products</b>\n\nChoose a product:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.message(Command("wallet"))
async def cmd_wallet(m:Message):
    if not await require_join_message(m): return
    u=await users.find_one({'_id':m.from_user.id}); bal=float((u or {}).get('balance',0))
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Deposit',callback_data='deposit')],[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]])
    await m.answer(f'💰 <b>Wallet</b>\n\nBalance: <b>₹{bal:.2f}</b>',reply_markup=kb)

@router.message(Command("orders"))
async def cmd_orders(m:Message):
    if not await require_join_message(m): return
    docs=await orders.find({'user_id':m.from_user.id}).sort('created_at',-1).to_list(10)
    text='📦 <b>My Orders</b>\n\n'+('\\n'.join(f"• {o['product_name']} — ₹{o['amount']:.2f} — {o['status']}" for o in docs) if docs else 'No orders yet.')
    await m.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🏠 Main Menu',callback_data='home')]]))

@router.message(Command("support"))
async def cmd_support(m:Message):
    if not await require_join_message(m): return
    now=datetime.now(timezone.utc)
    await support.insert_one({'user_id':m.from_user.id,'status':'open','expires_at':now+timedelta(minutes=5),'created_at':now})
    await m.answer('💬 <b>Support session started.</b>\nYou have 5 minutes to send your payment/order questions.')

@router.message(Command("broadcast"))
async def broadcast(m:Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.answer('Not authorized.')
    src=m.reply_to_message
    if not src:
        return await m.answer('📢 Reply to the message you want to broadcast, then send /broadcast.')
    sent=0; failed=0
    async for u in users.find({}, {'_id':1}):
        uid=u['_id']
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=src.chat.id, message_id=src.message_id)
            sent+=1
        except Exception:
            failed+=1
    await m.answer(f'📢 <b>Broadcast completed</b>\n\n✅ Sent: {sent}\n❌ Failed: {failed}')

@router.callback_query(F.data=='support')
async def support_start(c:CallbackQuery):
    if not await is_joined(c.from_user.id): return await send_join_gate(c.message)
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
    from aiogram.types import BotCommand
    await bot.set_my_commands([BotCommand(command='start',description='Start / verify'),BotCommand(command='buy',description='Buy products'),BotCommand(command='wallet',description='Wallet / Deposit'),BotCommand(command='orders',description='My orders'),BotCommand(command='support',description='Support (5 min)'),BotCommand(command='admin',description='Admin panel'),BotCommand(command='broadcast',description='Broadcast a replied message')])
    await asyncio.gather(dp.start_polling(bot),cleanup())

if __name__=='__main__': asyncio.run(main())
