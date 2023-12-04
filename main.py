from keys import api_key, secret_key
import hmac
from binance.spot import Spot
import hashlib
import time
import requests
import json
import pandas as pd
import sys

class ScriptError(Exception):
    pass
class ScriptQuitCondition(Exception):
    pass

def get_ticker(coins):
    url = 'https://api.binance.com/api/v3/ticker/'
    ticker = requests.get(url + "price?symbol=" + coins)
    print(ticker.text)

#Возвращаем тукущую цену по паре
def get_current_price(pair):
    get_ticker(pair)

#Возвращает лучшие биды и аски по цене и количеству для даннной пары
def best_price(client, symbol):
    print(client.book_ticker(symbol))


#Возвращает все сделки всех состояний
def get_order(client, pair):
    print("Your actual orders")
    '''df = pd.DataFrame('''
    return client.get_orders(pair)
    #return df

#Создаем ордер лимитного или маркетного типа
def make_new_order(client, pair):
    side = input('Input side >>').upper()
    type = input('Input type >>').upper()
    quantity = input('Input quantity >>')
    if (type == "MARKET"):
         client.new_order(
            symbol=pair,
            side=side,
            type=type,
            quantity = quantity
            )
    elif (type == "LIMIT"):
        price = input('Input price >>')
        client.new_order(
            symbol=pair,
            side=side,
            type=type,
            quantity = quantity,
            price = price,
            timeInForce = 'GTC'
        )

#Создает лимитный ордер на продажу базовой валюты и выводит его на экран
def sell_currency(cl, pair, price, quantity):
        order = cl.new_order(
            symbol=pair,
            side="SELL",
            type="LIMIT",
            quantity = quantity,
            price = price,
            timeInForce = 'GTC'
        )
        print(order)
        return order

#Создает лимитный ордер на покупку базовой валюты и выводит его на экран
def buy_currency(cl, pair, price, quantity):
        order = cl.new_order(
            symbol=pair,
            side="BUY",
            type="LIMIT",
            quantity = quantity,
            price = price,
            timeInForce = 'GTC'
        )
        print(order)
        return order

#Удаление существующего невыполненного ордера
def cancel_order(cl, order_id, pair):
    cl.cancel_order(pair, order_id)

#сортирует ордера и оставляет только открытые и частично исполненные
def opened_orders(cl, CURRENT_PAIR):
    orders = get_order(cl, CURRENT_PAIR)
    open_orders=[]
    for order in orders:
        if ((order['status'] == 'NEW') or (order['status'] == 'PARTIALLY_FILLED')):
            open_orders.append(order)
    return open_orders

#возвращает информацию о CURRENT_PAIR на аккаунте
def get_balance(cl, CURRENCY_1, CURRENCY_2):
    account_info = {}
    balance = cl.account().get('balances') #массив словарей по каждой валюте
    for currency_info in balance:
        if (currency_info.get('asset') == CURRENCY_1):
            account_info['CURRENCY_1'] = currency_info
        if (currency_info.get('asset') == CURRENCY_2):
            account_info['CURRENCY_2'] = currency_info
    return account_info #содержит информацию кошелька о нашей паре

def get_count(number):
    s = str(number)
    if '.' in s:
        return abs(s.find('.') - len(s)) - 1
    else:
        return 0

def main(*args):
    try:
        # Получаем список активных ордеров
        try:
            open_orders = opened_orders(cl, CURRENT_PAIR)
            print("open_orders=", open_orders)
        except KeyError:
            if DEBUG:
                print('Открытых ордеров нет')
            open_orders = []

        sell_orders = []
        # Есть ли неисполненные ордера на продажу CURRENCY_1?
        for order in open_orders:
            if (order.get('side') == 'SELL'):
                # Есть неисполненные ордера на продажу CURRENCY_1, выход
                raise ScriptQuitCondition('Выход, ждем пока не исполнятся/закроются все ордера на продажу (один ордер может быть разбит биржей на несколько и исполняться частями)')
            else:
                # Запоминаем ордера на покупку CURRENCY_1
                sell_orders.append(order) #хранятся ордера side = BUY

        # Проверяем, есть ли открытые ордера на покупку CURRENCY_1
        if sell_orders: # открытые ордера есть
            for order in sell_orders:
                # Проверяем, есть ли частично исполненные
                if DEBUG:
                    print('Проверяем, что происходит с отложенным ордером', order['orderId'])

                if(order.get('status') == 'PARTIALLY_FILLED'):
                    raise ScriptQuitCondition('Выход, продолжаем надеяться докупить валюту по тому курсу, по которому уже купили часть')
                else:
                    if DEBUG:
                        print('Частично исполненных ордеров нет')

                    time_passed = time.time() + STOCK_TIME_OFFSET*60*60 - int(order['created'])

                    if time_passed > ORDER_LIFE_TIME * 60:
                        # Ордер уже давно висит, никому не нужен, отменяем
                        cancel_order(CURRENT_PAIR, order['order_id'])
                        raise ScriptQuitCondition('Отменяем ордер -за ' + str(ORDER_LIFE_TIME) + ' минут не удалось купить '+ str(CURRENCY_1))
                    else:
                        raise ScriptQuitCondition('Выход, продолжаем надеяться купить валюту по указанному ранее курсу, со времени создания ордера прошло %s секунд' % str(time_passed))

        else: # Открытых ордеров нет
            balances = get_balance(cl, CURRENCY_1, CURRENCY_2)
            free_quantity = balances.get('CURRENCY_1').get('free')
            if float(free_quantity) >= CURRENCY_1_MIN_QUANTITY: # Есть ли в наличии CURRENCY_1, которую можно продать?
                wanna_get = CAN_SPEND + CAN_SPEND * (STOCK_FEE+PROFIT_MARKUP)  # сколько хотим получить за наше кол-во
                price= "{price:0.{prec}f}".format(prec=PRICE_PRECISION, price=wanna_get/float(balances[CURRENCY_1]))
                exact_price = round(float(price), TICK_SIZE) #Получили цену, округленную по параметру TICK_SIZE
                new_order = sell_currency(cl, CURRENT_PAIR, exact_price, free_quantity)
                if DEBUG:
                    print("Создан ордер на продажу", CURRENCY_1, "orderId =", new_order['orderId'])
            else:
                # CURRENCY_1 нет, надо докупить
                # Достаточно ли денег на балансе в валюте CURRENCY_2
                if float(balances[CURRENCY_2]) >= CAN_SPEND:
                    # Узнать среднюю цену за AVG_PRICE_PERIOD, по которой продают CURRENCY_1
                        bid_price = BID_ASK['bidPrice'] #лучшая цена покупки(бид — это цена спроса или максимальная цена, по которой покупатель согласен купить товар.)
                        # купить больше, потому что биржа потом заберет кусок
                        my_need_price = bid_price - bid_price * (STOCK_FEE+PROFIT_MARKUP)
                        my_amount = CAN_SPEND/my_need_price

                        print('buy', my_amount, my_need_price)

                        # Допускается ли покупка такого кол-ва валюты (т.е. не нарушается минимальная сумма сделки)
                        if my_amount >= CURRENCY_1_MIN_QUANTITY:
                            price="{price:0.{prec}f}".format(prec=PRICE_PRECISION, price=my_need_price)
                            exact_price = round(float(price), TICK_SIZE) #Получили цену, округленную по параметру TICK_SIZE
                            new_order = buy_currency(cl, CURRENT_PAIR, exact_price, my_amount)
                            if DEBUG:
                                print('Создан ордер на покупку', new_order['orderIdd'])
                        else: # мы можем купить слишком мало на нашу сумму
                            raise ScriptQuitCondition('Выход, сумма для торгов (CAN_SPEND) меньше минимально разрешенной биржей')
                else:
                    raise ScriptQuitCondition('Выход, не хватает денег')
    except ScriptError as e:
        print(e)
    except ScriptQuitCondition as e:
        if DEBUG:
            print(e)
        pass
    except Exception as e:
        print("!!!!",e)

cl = Spot(
    api_key,#открытый ключ
    secret_key,#секретный ключ
    base_url = 'https://testnet.binance.vision'#основной адрес для работы
    )

CURRENCY_1 = 'BTC'
CURRENCY_2 = 'USDT'

CURRENT_PAIR = CURRENCY_1 + CURRENCY_2 # пара с которой происходит работа

ORDER_LIFE_TIME = 3 # через сколько минут отменять неисполненный ордер на покупку CURRENCY_1
STOCK_FEE = 0.001 # Комиссия, которую берет биржа (0.001 = 0.1%)
AVG_PRICE_PERIOD = 15 # За какой период брать среднюю цену (мин)
CAN_SPEND = 10 # Сколько тратить CURRENCY_2 каждый раз при покупке CURRENCY_1
PROFIT_MARKUP = 0.001 # Какой навар нужен с каждой сделки? (0.001 = 0.1%)
DEBUG = True # True - выводить отладочную информацию, False - писать как можно меньше
STOCK_TIME_OFFSET = 0 # Если расходится время биржи с текущим

pair_info = cl.exchange_info("BTCUSDT") #вощвращает словарь с информацией по паре включая ошибки создания ордера
CURRENCY_1_MIN_QUANTITY = float(pair_info['symbols'][0]['filters'][1]['minQty']) #минимальное количество базовой валюты для ордераY)
PRICE_PRECISION = int(pair_info['symbols'][0]['quotePrecision']) #точность с которой необходимо указать цену
TICK_SIZE = get_count(float(pair_info['symbols'][0]['filters'][0]['tickSize']))
STEP_SIZE = float(pair_info['symbols'][0]['filters'][1]['stepSize'])
BID_ASK = best_price(cl, CURRENT_PAIR)  #возвращает словарь, содержащий лучшие биды и аски в виде:
                                        #{'symbol': 'BTCUSDT', 'bidPrice': 'price', 'bidQty': 'qty', 'askPrice': 'price', 'askQty': 'qty'}

try:
    balances = get_balance(cl, CURRENCY_1, CURRENCY_2)
    print("balances =", balances)
    alt_balance = float(balances[CURRENCY_1])

    poss_profit = (CAN_SPEND*(1+STOCK_FEE) + CAN_SPEND * PROFIT_MARKUP) / (1 - STOCK_FEE)

    if float(balances[CURRENCY_1]) > 0:
        decision = input("""
            У вас на балансе есть {amount:0.8f} {curr1}
            Вы действительно хотите, что бы бот продал все это по курсу {rate:0.8f}, выручив {wanna_get:0.8f} {curr2}?
            Введите Д/Y или Н/N
        """.format(
            amount=alt_balance,
            curr1=CURRENCY_1,
            curr2=CURRENCY_2,
            wanna_get=poss_profit,
            rate=poss_profit/alt_balance
        ))
        if decision in ('N','n','Н','н'):
            print("Тогда избавьтесь от {curr} (как вариант создайте ордер с ними по другой паре) и перезапустите бота".format(curr=CURRENCY_1))
            sys.exit(0)
except Exception as e:
    print(str(e))

while(True):
    main(cl, CURRENT_PAIR, ORDER_LIFE_TIME, STOCK_FEE, CAN_SPEND, PROFIT_MARKUP, DEBUG, STOCK_TIME_OFFSET, CURRENCY_1_MIN_QUANTITY, PRICE_PRECISION, TICK_SIZE, STEP_SIZE, BID_ASK)
    time.sleep(1)
