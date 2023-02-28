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
       'Unknown':100}
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
        self.outcome = ['Timeout', 0] # ответ клиенту
        self.bindAddr = (getIP(), bindPort) # порт, который я слушаю, приёмник

        ServerUDP.__count += 1
        self.name = ServerUDP.__count # порядковый номер
        print('[+] I am object #%d'%(self.name,))

    def startSocket(self):
        #% Сокет приёмника
        print('[+] Starting server: %s' %(self.name,))
        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.bind(self.bindAddr)  # Привязка адреса и порта к сокету.
        self.server.settimeout(1.5)
        print('[*] Ready to receive Ack on %s:%d' %(self.bindAddr))

    def close(self):
        self.server.close()
        print('[+] server closed...')

    def __enter__(self):
        self.startSocket()
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def cmdIsReceived(self):
        """ слушаем порт и определяем команду """
        try:
            packet, self.senderAddr = self.server.recvfrom(64)
            cmdIdx, data = struct.unpack(self.packetStruct, packet)
            self.income = (CMDR[cmdIdx], data)
        except socket.timeout:
            self.income = ('Timeout', 0.)
            return False
        # except KeyboardInterrupt:
        #     print('\n[!] Ctrl+C, exiting...')
        #     exit()
        # except Exception():
        #     self.incomeCmd = ['Unknown', 0.]
        print('[*] Got cmd: %s, %.2f'%(self.income))
        return True

    def Answer(self, Ans, Address):
        # отвечаем клиенту
        msg = struct.pack(self.packetStruct, *Ans)
        self.server.sendto(msg, Address) # send ack

    def Exec(self):
        """ выполняем команду """
        cmd = self.income[0]
        if cmd=='GetName':
            self.outcome = (CMD[cmd], float(self.name))
            self.Answer(self.outcome, self.senderAddr)


        # if command=='GetI':
        #     return (CMD[command], self.I)
        # if command=='GetU':
        #     return (CMD[command], self.U)
        # if command=='SetI':
        #     self.setI(data)
        #     return (CMD[command], self.I)
        # if command=='SetU':
        #     self.setU(data)
        #     return (CMD[command], self.U)

    # def setI(self, I):
    #     self.I = I
    # def setU(self, U):
    #     self.U = U

#%%

with ServerUDP(bindPort=7003) as dev:
    while True:
        if dev.cmdIsReceived():
            dev.Exec()


# %%
# Класс приёмопередатчика UDP (основа для ЗУ и нагрузки)
class ServerClientUDP(ServerUDP):
    """ добавляется клиент, транслирующий команды последующему серверу """
    def __init__(self, bindPort, hostPort, hostIP=None):
        super().__init__(bindPort)
        if self.hostIP is None:
            self.hostAddr = (getIP(), hostPort)
        else:
            self.hostAddr = (hostIP, hostPort)

        self.outCmd = ['Timeout', 0] # исходящая команда, на сервер
        self.outAns = ['Timeout', 0] # ответ сервера

    def startSocket(self):
        super().startSocket()
        #% Достраиваем сокет
        if self.hostIP is None:
            self.hostIP = getIP()
        self.hostAddr = (self.hostIP, self.hostPort)
        self.server.connect(self.hostAddr)
        print('[+] Connected to %s:%d' %(self.hostIP, self.hostPort))

    def cliAck(self):
        # запрашиваем сервер
        msg = struct.pack(self.packetStruct,
                          CMD[self.outCmd[0]], float(self.outCmd[1]))
        self.server.sendto(msg, self.hostAddr) # send ack

    def cliIsReceived(self):
        """ слушаем порт и определяем команду """
        try:
            packet, self.senderAddr = self.server.recvfrom(64)
            #print('[*] ack from %s:%d'%(senderAddr[0], senderAddr[1]))
            cmdIdx, data = struct.unpack(self.packetStruct, packet)
            self.incomeCmd = [CMDR[cmdIdx], data]
        except socket.timeout:
            self.incomeCmd = ['Timeout', 0.]
            return False
        except KeyboardInterrupt:
            print('\n[!] Ctrl+C, exiting...')
            exit()
        except Exception():
            self.incomeCmd = ['Unknown', 0.]
        finally:
            print('[*] Got cmd: %s, %.2f'%(self.cmd, self.data))
            return True


class Charger(Device):
    def execute(self, command, data):
        """ выполняем команду """
        super().execute(self, command, data) # метод родителя
        if command=='SetI' or command=='GetI':
            self.I = data
            return (CMD[command], self.I)
        if command=='SetI' or command=='GetI':
            self.I = data
            return (CMD[command], self.I)
    def setI(self, I):
        super().setI(I) # метод родителя, запись соотв. свойства
        self.send((CMD['SetI'], I)) # дополняем отправкой в хост-объект

#%% Класс аккумулятора
def fun(x,a,b,c,d,e):
    return c+a*np.exp(b*x)+d*np.exp(e*x)

class Accumulator():
    def __init__(self, Cnom=2.7):
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
        self.C = np.clip(self.C, 0, self.Cnom)
        self.SoC = self.C/self.Cnom
        self.tPrev = tNow
        SoC1 = 1-self.SoC
        self.U = fun(SoC1, *self.__UocParams) + self.I*fun(SoC1, *self.__RintParams)/self.Cnom

# acc = Accumulator()
# %%
# acc.I = -10
# acc.calcState()
# acc.U

#%% Основной код
if __name__ == "__main__":
    if len(sys.argv)<2:
        bind_port = 6505
    else:
        bind_port = int(sys.argv[1])

    with Device() as dev:
        while dev.listen():
            pass

else:
    with Device() as dev:
        while dev.listen():
            pass
