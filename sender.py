#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 25 21:50:21 2023
@author: alex
"""
import socket
import struct
# import sys

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


#%% Communicator
def getIP():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('192.168.1.1', 1)) # doesn't even have to be reachable
    IP = s.getsockname()[0]
    s.close()
    return IP

class Communicator():
    """ organizes communication with the simulator, 1 socket """
    def __init__(self, hostIP = None,
                 hostPort=6700, bindPort=6701):
        self.packetStruct = 'if' # структура пакета
        self.hostAddr = (hostIP, hostPort)
        if hostIP is None:
            self.hostAddr = (getIP(), self.hostAddr[1])

        self.bindAddr = (getIP(), bindPort)

    def connect(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.bind(self.bindAddr)  # Binding an address and port to a socket.
        print('[+] Ready to receive data on %s:%d' %(self.bindAddr[0],
                                                         self.bindAddr[1]))
        self.server.connect(self.hostAddr)
        print('[+] Connected to %s:%d' %(self.hostAddr[0], self.hostAddr[1]))
        self.server.settimeout(0.25)

    def send(self, cmd, data=0):
        msg = struct.pack(self.packetStruct, CMD[cmd], float(data))
        self.server.send(msg) # send ack

    def listen(self):
        try:
            msg, _ = self.server.recvfrom(256) # receiving..
            cmd, data = struct.unpack(self.packetStruct, msg)
            command = CMDR[cmd]
            print('[+] Got %s, %.2f'%(command, data))
            return cmd, data
        except (socket.error, socket.timeout, struct.error):
            print('[+] No data available', socket.error)
            return None, None

    def close(self):
        self.server.close()
        print('[+] server closed...')

    def __enter__(self):
        self.connect()
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        self.close()






#%%
comm = Communicator(hostPort=7003)
comm.connect()

#%%
comm.send('GetName', 0.)
Ans = comm.listen()
print(Ans)


#%%
comm.close()




