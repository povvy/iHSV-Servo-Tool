#!/usr/bin/env python3
#
# iHSV Servo Tool
# Copyright (C) 2018 Robert Budde

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

from iHSV_Properties import iHSV

import os
import ctypes
import serial
import minimalmodbus
import re

class ServoiHSV:

    def __init__(self, serial_port, motor_version = 'v6'):
        if motor_version in iHSV.supported_motor_versions.values():
            self.motorversion = motor_version
            self.ihsv = iHSV(self.motorversion)

            try:
                self.modbus = minimalmodbus.Instrument(serial_port, 1) # port name, slave address (in decimal)
                self.modbus.serial.baudrate = self.ihsv.get_rs232_settings('baudrate')
                self.modbus.serial.bytesize = self.ihsv.get_rs232_settings('bytesize')
                self.modbus.serial.parity   = self.ihsv.get_rs232_settings('parity')
                self.modbus.serial.stopbits = self.ihsv.get_rs232_settings('stopbits')
                self.modbus.serial.timeout  = self.ihsv.get_rs232_settings('timeout')
            except Exception as e:
                print(e)
                print("Failed to open port")
                return

            try:
                if not self.modbus.serial.isOpen():
                    self.modbus.serial.open()
                self.modbus.read_register(0x80)
                print("Port opened successfully")
                self.connected = True
            except Exception as e:
                print(e)
                self.modbus.serial.close()
                print("Device does not respond")
                return
        else:
            raise ValueError('Motor Version not supported')


    # register as int, length as int
    def read_register(self, register, length=1):
        return self.modbus.read_registers(register, length)

    # register as int, value as int
    def write_register(self, register, value):
        if not self.connected:
            return
            
        self.modbus.write_register(register, ctypes.c_uint16(value).value, functioncode=6)

    def dump_motor_parameters(self):
        # get all parameters group
        parameterGroupList = self.ihsv.get_parameter_group_list()
        parameterList = self.ihsv.get_parameter_list(parameterGroupList)
        # print(parameter_list)
        len(parameterList)

        for configDataInfo in parameterList:

            register = int(configDataInfo['Address'], 16)
            # read data from modbus
            registerValue = self.modbus.read_register(register)

            # move decimal point
            if 'decimal_place' in configDataInfo.keys():
                decimal = int(configDataInfo['decimal_place'])
                if decimal != 0:
                    registerValue /= 10**int(configDataInfo['decimal_place'])

            configDataInfo['Value'] = registerValue

            print("{}, {}: {} \t {}".format(configDataInfo['Address'], configDataInfo['Code'], configDataInfo['Value'], configDataInfo['Name']))
        print("Loading System Params done!")

    def read_live_data(self):
        
        liveDataList = self.ihsv.get_live_data_list()
        # data = json.
        for liveData in liveDataList:
            print(liveData)
            register = liveData[0]
            signed = liveData[1]
            name = liveData[2]

            values = self.read_register(register[0], len(register))
            
            if signed:
                for i, value in enumerate(values):
                    values[i] = ctypes.c_short(value)
            print(values)

    def read_real_velocity(self):

        # value = self.read_register(0x91)
        velocity_value = self.modbus.read_registers(0x0842, 1)
        # self.read_live_data()
        return ctypes.c_short(velocity_value[0]).value

        # use aggregated regs to read all values and create dictionary with reg:value pairs
        # if self.connected:
        #     regs_values = dict([reg_value for regs in regs_aggr for reg_value in zip(regs, self.servo.read_registers(int(regs[0]), len(regs)))])
        # else:
        #     regs_values = dict([reg_value for regs in regs_aggr for reg_value in zip(regs, [int(value*100) for value in np.random.randn(len(regs))])])

    def write_parameter_speed(self, code, value):
        
        speedParameter = self.ihsv.parameter['P04_Speed_parameters']
        parameter = speedParameter[code]
        register = int(parameter['Address'], 16)
        
        if(value < int(parameter['Min']) or value > int(parameter['Max'])):
            print('Parameter value out of Range')
            return
        
        self.write_register(register, value)


    def parse_parameter(self, code, value):

        pattern=re.compile(r'P[0,1][0-9]-[0-9]+')
        # Checks whether the whole string matches the pattern or not
        test = code
        if re.fullmatch(pattern, test):
            pass
        else:
            print(f"'{test}' is not valid register!")
            return 

        groupcode = code[0:3]

        if groupcode == 'P00':
            group = "P00_Parameter_of_motor_and_driver"
        elif groupcode == 'P01':
            group = "P01_main_control_parameter"
        elif groupcode == 'P02':
            group = "P02_Gain_parameter"
        elif groupcode == 'P03':
            group = "P03_Position_parameters"
        elif groupcode == 'P04':
            group = "P04_Speed_parameters"
        elif groupcode == 'P05':
            group = "P05_Torque_parameters"
        elif groupcode == 'P06':
            group = "P06_IO_parameters"
        elif groupcode == 'P08':
            group = "P08_advanced_function_parameter"
        elif groupcode == 'P10':
            group = "P10_Factory_parameter"

        # Checks whether the whole string matches the pattern or not
        parameterGroup = self.ihsv.parameter[group]
        parameter = parameterGroup[code]

        if(value < float(parameter['Min']) or value > float(parameter['Max'])):
            print('Parameter value out of Range')
            return

        if parameter['decimal_place'] != 0:
            value *= 10**int(parameter['decimal_place'])

        return {"register": int(parameter['Address'], 16), "value": int(value)}

if __name__ == '__main__':
    import argparse
    import logging
    import asyncio
    import json
    import websockets

    
    logging.basicConfig(level=logging.INFO)

    connected_clients = set()
 
    async def run_deamon_socket(websocket, path):
        consumer_task = asyncio.ensure_future(
            consumer_handler(websocket, path))
        producer_task = asyncio.ensure_future(
            producer_handler(websocket, path))
        done, pending = await asyncio.wait(
            [consumer_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    async def consumer_handler(websocket, path):
        # https://websockets.readthedocs.io/en/stable/intro.html#synchronization-example
        # register(websocket) sends user_event() to websocket
        # await connected_clients.add(websocket)
        try:
            # await websocket.send(send_motor_state()) # send state of motor
            async for message in websocket:
                data = json.loads(message)
                if data["action"] == "rpm":
                   servo.write_parameter_speed('P04-02', int(data["value"])) 
                else:
                    logging.error("unsupported event: %s", data)
        finally:
            pass
            # await connected_clients.remove(websocket)

    async def producer_handler(websocket, path):
        while True:
            value = servo.read_real_velocity()
            message = json.dumps({"type": "rpm", "value": value})
            await websocket.send(message)
            await asyncio.sleep(0.1)

    def parse_args():
        parser = argparse.ArgumentParser(prog='ihsv servo controller', description='interface with a JMC iHSV60 servo motor')
        # parser.add_argument('--port', '-p', nargs=2, default=["/dev/ttyUSB0", "57600"], metavar=('SERIALPORT', 'BAUDRATE'), type=str, help='RS232 serial port', required=True) # action = 'store_true'
        parser.add_argument('--port', '-p', help='RS232 serial port', required=True) # action = 'store_true'
        parser.add_argument('--version', '-v', default='v6', choices=['v5', 'v6'], help='define version')
        parser.add_argument('--rpm', '-s', help='set motor rpm speed in register P04-02')
        parser.add_argument('--daemon', '-d', help='start deamon websocket on localhost:8765', action='store_true')
        parser.add_argument('--register', '-r', nargs='*', metavar=['REGISTER','VALUE'], help='set motor register, e.g. P04-02 20, for speed command 20 rpm')
        # parser.add_argument('--debug', '-d', default=[20], type=int, metavar='verbosity level', help='10 debug, 20 info, 30 warning, 40 error, 50 critical')
        return parser.parse_args()

    try:

        args = parse_args()

        servo = ServoiHSV(args.port, args.version)  

        # servo.read_live_data()
        # servo.dump_motor_parameters()
        
        if(args.rpm):
            # set Source of rotational speed to digital Modbus command
            servo.write_parameter_speed('P04-00', 1)
            # write digital speed command
            servo.write_parameter_speed('P04-02', int(args.rpm))

        if(args.register):
            register_value_pair = servo.parse_parameter(args.register[0], float(args.register[1]))
            servo.write_parameter(register_value_pair["register"], register_value_pair["value"])

        if(args.daemon):
            # https://websockets.readthedocs.io/en/stable/intro.html
            daemon_server = websockets.serve(run_deamon_socket, "localhost", 8765)
            asyncio.get_event_loop().run_until_complete(daemon_server)
            asyncio.get_event_loop().run_forever()
            logging.info("Running websocket daemon on localhost:8765...")


    except (KeyboardInterrupt, SystemExit):

        logging.info('\n\nExiting...')
        servo.modbus.serial.close()
        exit()    