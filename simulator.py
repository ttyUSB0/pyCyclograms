#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 25 17:42:06 2023
@author: alex

Сервер UDP, симуляторы ЛИА (6701), ЗУ (6702), управл. нагрузки (6703)
слушает порты, возврат данных в порт источника
"""
# коды команд
CMD = {'Timeout':-2, #выход по таймауту
       'Break':-1, # пользователь нажал Ctrl+C
       'GetName':0,
       'GetU':1, 'SetU':2,
       'GetI':3, 'SetI':4,
       'GetC':5, 'SetC':6,
       'GetChildName':7,
       'Unknown':100, 'NoAnsFromChild':101}
CMDR = {} # ревёрснутый массив кодов
for key, val in CMD.items():
    CMDR[val] = key

timeoutGreat = 90 # за это время НУ становятся нулевыми

import socket
import numpy as np
# from scipy.integrate import odeint
import time
# import matplotlib.pyplot as plt
import struct
import sys

# %% функции общего назначения
clip = lambda n, minn, maxn: max(min(maxn, n), minn) # https://stackoverflow.com/a/5996949/5355749

def getIP():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('192.168.1.1', 1)) # doesn't even have to be reachable
    IP = s.getsockname()[0]
    s.close()
    return IP

# %% Класс приёмника UDP (основа для аккумулятора)
class ServerUDP():
    """ Базовый класс, может принимать UDP.
    Отвечает только на запрос имени, возвращает порядковый номер экземпляра """
    __count = 0
    def __init__(self, bindPort):
        self.packetStruct = 'if' # структура пакета
        self.income = ['Timeout', 0] # входящая команда, со стороны клиента, я - сервер
        # self.outcome = ['Timeout', 0] # ответ клиенту
        self.bindAddr = (getIP(), bindPort) # порт, который я слушаю, приёмник

        ServerUDP.__count += 1
        self.name = ServerUDP.__count # порядковый номер

    def startSocket(self):
        #% Сокет приёмника
        print('[+] Starting server: %s' %(self.name,))
        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.bind(self.bindAddr)  # Привязка адреса и порта к сокету.
        self.server.settimeout(1.5)
        print('[*] Ready to receive Ack on %s:%d' %(self.bindAddr))

    def closeSocket(self):
        self.server.close()
        print('[+] server closed...')

    def __enter__(self):
        self.startSocket()
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        self.closeSocket()

    def cmdIsReceived(self):
        """ слушаем порт и определяем команду """
        try:
            packet, self.senderAddr = self.server.recvfrom(64)
            self.income = struct.unpack(self.packetStruct, packet)
        except socket.timeout:
            return False
        except struct.error:
            print('[!] Unknown packet format: ', packet)
            return False
        print('[*] Got cmd: %d, %.2f'%(self.income))
        return True

    def Send(self, Ans, Address):
        # отвечаем клиенту
        msg = struct.pack(self.packetStruct, *Ans)
        self.server.sendto(msg, Address) # send ack

    def Exec(self):
        """ выполняем команду """
        if self.income[0] in CMDR.keys():
            cmd = CMDR[self.income[0]] # если команда известна, идём на её обработку
        else:
            cmd = 'Unknown'

        if cmd=='GetName':
            outcome = (CMD[cmd], float(self.name))
        else:
            print('[*] no code for execute this command...')
            outcome = self.income
        self.Send(outcome, self.senderAddr)

# #%% Проверка
# with ServerUDP(bindPort=7003) as dev:
#     while True:
#         if dev.cmdIsReceived():
#             dev.Exec()

# %%
# Класс приёмопередатчика UDP (основа для ЗУ и нагрузки)
class ServerClientUDP(ServerUDP):
    """ добавляется клиент, транслирующий команды последующему серверу """
    def __init__(self, bindPort, hostPort, hostIP=None):
        super().__init__(bindPort)
        if hostIP is None:
            self.hostAddr = (getIP(), hostPort)
        else:
            self.hostAddr = (hostIP, hostPort)

    def AckChild(self, outcome, Address):
        # запрос слейва hostAddr, потом реконнект к Address
        self.server.connect(self.hostAddr)
        self.Send(outcome, self.hostAddr)
        while True: # циклимся на время ожидания ответа
            if self.cmdIsReceived(): # когда получили (здесь пауза)
                outcome = self.income # транслируем наверх
                # if self.senderAddr==self.hostAddr: # и если от слейва
            else: # иначе - ответ "нет ответа от слейва"
                outcome = (CMD['NoAnsFromChild'], 0.)
            break
        self.server.connect(Address)
        return outcome

    def Exec(self): # переопределяем метод
        """ выполняем принятую команду """
        serverAddr = self.senderAddr # адрес, с которого пришла команда
        if self.income[0] in CMDR.keys():
            cmd = CMDR[self.income[0]] # если команда известна, идём на её обработку
        else:
            cmd = 'Unknown'
        # отрабатываем команды
        if cmd=='GetName':
            outcome = (CMD[cmd], float(self.name))
        elif cmd=='GetChildName':
            outcome = self.AckChild((CMD['GetName'], 0.), serverAddr)
        else:
            print('[*] no code for execute this command...')
            outcome = self.income

        self.Send(outcome, serverAddr)

# #%% Проверка
# with ServerClientUDP(bindPort=7004, hostPort=7003) as dev:
#     while True:
#         if dev.cmdIsReceived():
#             dev.Exec()

#%%
class CDU(ServerClientUDP):
    def __init__(self, bindPort, hostPort, hostIP=None):
        super().__init__(bindPort, hostPort, hostIP)
        self.I = 0.
        self.U = 0.

    def Exec(self): # переопределяем метод
        """ выполняем принятую команду """
        serverAddr = self.senderAddr # адрес, с которого пришла команда
        if self.income[0] in CMDR.keys():
            cmd = CMDR[self.income[0]] # если команда известна, идём на её обработку
        else:
            cmd = 'Unknown'
        data = self.income[1]
        # отрабатываем команды
        if cmd=='GetName':
            outcome = (CMD[cmd], float(self.name))
        elif cmd=='GetChildName':
            outcome = self.AckChild((CMD['GetName'], 0.), serverAddr)
        elif cmd=='GetI':
            outcome = (CMD[cmd], self.I)
        elif cmd=='SetI':
            self.I = data
            outcome = self.AckChild(self.income, serverAddr) # ставим ток
        elif cmd=='GetU':
            outcome = self.AckChild(self.income, serverAddr) # ставим напряжение
            self.U = outcome[1]
        else:
            print('[*] no code for execute this command...')
            outcome = self.income
        self.Send(outcome, serverAddr)

#%% Класс аккумулятора
def fun(x,a,b,c,d,e):
    return c+a*np.exp(b*x)+d*np.exp(e*x)

class Accumulator(ServerUDP):
    def __init__(self, bindPort, Cnom=2.7):
        super().__init__(bindPort)
        # параметры аккумулятора
        self.Cnom = Cnom
        self.I = 0
        self.SoC = 0.8
        self.C = self.SoC*Cnom
        self.tPrev = time.time() # время предыдущего вызова

    # параметры модели ЛИА SAFT МР144350
    __UocParams = [8.33752633e-01, -1.88138703e+00, 3.32153789e+00,
                   -2.54041769e-07, 1.37282219e+01]
    __RintParams= [ 9.51701058e-10,  2.04170058e+01,  2.04979934e-01, -6.54341513e-02,
                   -4.36651040e+01]
    def calcState(self):
        # нагрузка и зарядное работают в режиме стабилизации тока
        tNow = time.time()
        # t = np.linspace(0, tNow-tPrev, 2)
        # sol = odeint(myode, y0, t, args=(fan,), hmax=0.01) #, hmax=0.01
        # y0 = sol[-1,:]
        self.C += self.I *(tNow - self.tPrev)/3600
        self.C = np.clip(self.C, 0, self.Cnom) # без эффектов перезаряда/переразряда
        self.SoC = self.C/self.Cnom
        self.tPrev = tNow
        SoC1 = 1-self.SoC
        self.U = fun(SoC1, *self.__UocParams) + self.I*fun(SoC1, *self.__RintParams)/self.Cnom

    def Exec(self): # переопределяем метод
        if self.income[0] in CMDR.keys():
            cmd = CMDR[self.income[0]] # если команда известна, идём на её обработку
        else:
            cmd = 'Unknown'
        data = self.income[1]
        if cmd=='GetName':
            outcome = (CMD[cmd], float(self.name))
        elif cmd=='GetI':
            outcome = (CMD[cmd], self.I)
        elif cmd=='SetI':
            self.I = data # ставим ток
            outcome = self.income
        elif cmd=='GetU':
            self.calcState()
            outcome = (CMD[cmd], self.U)
        elif cmd=='GetC':
            outcome = (CMD[cmd], self.C)
        elif cmd=='SetC':
            self.C = data
            outcome = (CMD[cmd], self.C)
        else:
            print('[*] no code for execute this command...')
            outcome = self.income
        self.Send(outcome, self.senderAddr)

# acc = Accumulator()
# #%% Проверка кода аккумулятора
# acc.I = -10
# acc.calcState()
# acc.U

#%% Основной код
msg = """Программный симулятор литий-ионного аккумулятора,
зарядного и разрядного устройства (стабилизаторы тока).
Это простейшие сервера, обменивающиеся посылками и меняющие состояние друг друга.
Для деталей смотри документацию. """
""" Вызов: python3 simulator.py
Параметры:
    1. 'CDU'/'ACC'
    2. bindPort

"""
if __name__ == "__main__":
    import argparse

    # Initialize parser
    parser = argparse.ArgumentParser(description = msg)
    # Позиционные аргументы
    parser.add_argument("type", type=str, help = 'Тип устройства: CDU-зарядно-разрядное, ACC-аккумулятор (строки без кавычек)')
    parser.add_argument("bindPort", type=int, help = "Номер входящего (прослушиваемого) порта, для команд")
    # Опциональные аргументы
    parser.add_argument("--Cnom", type=float, default=2.7, help = '[ACC] Номинальная ёмкость ЛИА')
    parser.add_argument("--hostPort", help = '[CDU] порт, занятый симулятором аккумулятора')
    parser.add_argument("--hostIP", default=None, help = '[CDU] сетевой адрес, занятый симулятором аккумулятора')
    ns = parser.parse_args()

    if ns.type=='CDU':
        with CDU(bindPort=ns.bindPort, hostPort=ns.hostPort,
                 hostIP=ns.hostIP) as dev:
            while True:
                if dev.cmdIsReceived():
                    dev.Exec()

    elif ns.type=='ACC':
        with Accumulator(bindPort=ns.bindPort, Cnom=ns.Cnom) as dev:
            while True:
                if dev.cmdIsReceived():
                    dev.Exec()



