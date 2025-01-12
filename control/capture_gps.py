#! /usr/bin/env python3

##############################################################
# Script for capturing GPS Primary and Secondary data from the 
# GPS Receiver and writing their associated values into the 
# Redis database. All packet information is time stamped by the
# computer and added to each set of values with a variable 
# labeled as 'Computer_UTC'.
##############################################################
import time, sys
import serial
import struct
import redis
from influxdb import InfluxDBClient
from signal import signal, SIGINT
from datetime import datetime
from datetime import timezone
from redis_utils import *
import util
sys.path.insert(0, '../util')
import config_file


BYTEORDER = 'big'
RKEY = 'GPSPRIM'
RKEYsupp = 'GPSSUPP'

lastTime = ''
lastTimeUpdated = False

def handler(signal_recieved, frame):
    print('\nSIGINT or CTRL-C detected. Exiting')
    exit(0)

def floatfrom_bytes(bytesData, bytesorder=BYTEORDER):
    if BYTEORDER == 'little':
        f = '<f'
    else:
        f = '>f'

    return struct.unpack(f, bytesData)[0]

def doublefrom_bytes(bytesData, bytesorder=BYTEORDER):
    if BYTEORDER == 'little':
        d = '<d'
    else:
        d = '>d'

    return struct.unpack(d, bytesData)[0]

timingFlagValues = {0:'GPS', 1:'UTC'}

# OutputID 0x8F-AB
def primaryTimingPacket(data, r):
    global lastTime, lastTimeUpdated
    if len(data) != 17:
        print(RKEY, ' is malformed ignoring the following data packet')
        print(data)
        print('Packet size is ', len(data))
        return
    tvUTC = str(datetime.now(timezone.utc))
    
    timeofWeek = int.from_bytes(data[1:5], byteorder=BYTEORDER, signed=False)
    
    weekNumber = int.from_bytes(data[5:7], byteorder=BYTEORDER, signed=False)
    
    UTCOffset = int.from_bytes(data[7:9], byteorder=BYTEORDER, signed=True)
    
    timingFlag = int.from_bytes(data[9:10], byteorder=BYTEORDER, signed=False)
    timeFlagIndex = timingFlag & 0x01
    PPS = (timingFlag & 0x02) >> 1
    timeSet = (timingFlag & 0x04) >> 2
    UTCinfo = (timingFlag & 0x08) >> 3
    timeFrom = (timingFlag & 0x10) >> 4
    
    seconds = int.from_bytes(data[10:11], byteorder=BYTEORDER, signed=False)
    minutes = int.from_bytes(data[11:12], byteorder=BYTEORDER, signed=False)
    hours = int.from_bytes(data[12:13], byteorder=BYTEORDER, signed=False)
    dayofMonth = int.from_bytes(data[13:14], byteorder=BYTEORDER, signed=False)
    month = int.from_bytes(data[14:15], byteorder=BYTEORDER, signed=False)
    year = int.from_bytes(data[15:17], byteorder=BYTEORDER, signed=False)
    
    lastTime = str(year)+'-'+str(month)+'-'+str(dayofMonth)+'T'+str(hours)+':'+str(minutes)+':'+str(seconds) + 'Z'
    lastTimeUpdated = True
    print(lastTime)
    
    redis_set = { 'Computer_UTC': time.time(),#datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        'GPSTIME': lastTime,
        'TOW': timeofWeek,
        'WEEKNUMBER': weekNumber,
        'UTCOFFSET': UTCOffset,
        'TIMEFLAG': timingFlagValues[timeFlagIndex],
        'PPSFLAG': timingFlagValues[PPS],
        'TIMESET': (timeSet+1)%2,
        'UTCINFO': (UTCinfo+1)%2,
        'TIMEFROMGPS': (timeFrom+1)%2
    }

    for key in redis_set.keys():
        r.hset(RKEY, key, redis_set[key])
    

    
recModeValues = {0:'Automatic (2D/3D)', 1:'Single Satellite (Time)', 3:'Horizontal (2D)', 4:'Full Position (3D)', 7:'Over-Determined Clock'}
disModeValues = {0:'Normal (Locked to GPS)', 1:'Power Up', 2:'Auto Holdover', 3:'Manual Holdover', 4:'Recovery', 5:'Not used', 6:'Disciplining Disabled'}
GPSDecodeValues = {0:'Doing fixes', 1:'Don\'t have GPS time', 3:'PDOP is too high', 
                   8:'No usable sats', 9:'Only 1 usable sat', 10:'Only 2 usable sats', 11:'Only 3 usable sats', 12:'The chosen sat is unusable', 
                   16:'TRAIM rejected the fix'}
disActivityValues = {0:'Phase locking', 1:'Oscillator warm-up', 2:'Frequency locking', 3:'Placing PPS', 4:'Initializing loop filter', 
                     5:'Compensating OCXO (holdover)', 6:'Inactive', 7:'Not used', 8:'Recovery mode', 9:'Calibration/control voltage'}
DEFAULTVALUE = 'Uknown Value {0}'
# OutputID 0x8F-AC
def supplementaryTimingPacket(data, r):
    global lastTimeUpdated
    if len(data) != 68:
        print(RKEYsupp, ' is malformed ignoring the following data packet')
        print(data)
        print('Packet size is ', len(data))
        lastTimeUpdated = False
        return
    if not lastTimeUpdated:
        print("Primary Packet Failed not saving Supplementary Packet")
        return
    
    receiverMode = int.from_bytes(data[1:2], byteorder=BYTEORDER, signed=False)
    discipliningMode = int.from_bytes(data[2:3], byteorder=BYTEORDER, signed=False)
    selfSurveyProgress = int.from_bytes(data[3:4], byteorder=BYTEORDER, signed=False)
    holdOverDuration = int.from_bytes(data[4:8], byteorder=BYTEORDER, signed=False)
    criticalAlarms = int.from_bytes(data[8:10], byteorder=BYTEORDER, signed=False)
    minorAlarms = int.from_bytes(data[10:12], byteorder=BYTEORDER, signed=False)
    GPSDecodingStatus = int.from_bytes(data[12:13], byteorder=BYTEORDER, signed=False)
    discipliningActivity = int.from_bytes(data[13:14], byteorder=BYTEORDER, signed=False)
    spareStatus1 = int.from_bytes(data[14:15], byteorder=BYTEORDER, signed=False)
    spareStatus2 = int.from_bytes(data[15:16], byteorder=BYTEORDER, signed=False)

    PPSOffset = floatfrom_bytes(data[16:20])
    clockOffset = floatfrom_bytes(data[20:24])
    DACValue = int.from_bytes(data[24:28], byteorder=BYTEORDER, signed=False)
    DACVoltage = floatfrom_bytes(data[28:32])
    temp = floatfrom_bytes(data[32:36])
    latitude = doublefrom_bytes(data[36:44])
    longitude = doublefrom_bytes(data[44:52])
    altitude = doublefrom_bytes(data[52:60])
    PPSQuantizationError = floatfrom_bytes(data[60:64])

    redis_set = { 'Computer_UTC': time.time(),#datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        'GPSTIME': lastTime,
        'RECEIVERMODE': DEFAULTVALUE.format(receiverMode),
        'DISCIPLININGMODE': DEFAULTVALUE.format(disModeValues),
        'SELFSURVEYPROGRESS': selfSurveyProgress,
        'HOLDOVERDURATION': holdOverDuration,
        'DACatRail': (criticalAlarms & 0x08) >> 3,
        'DACnearRail': minorAlarms & 0x0001,
        'AntennaOpen': (minorAlarms & 0x0002) >> 1,
        'AntennaShorted': (minorAlarms & 0x0004) >> 2,
        'NotTrackingSatellites': (minorAlarms & 0x0008) >> 3,
        'NotDiscipliningOscillator': (minorAlarms & 0x0010) >> 4,
        'SurveyInProgress': (minorAlarms & 0x0020) >> 5,
        'NoStoredPosition': (minorAlarms & 0x0040) >> 6,
        'LeapSecondPending': (minorAlarms & 0x0080) >> 7,
        'InTestMode': (minorAlarms & 0x0100) >> 8,
        'PositionIsQuestionable': (minorAlarms & 0x0200) >> 9,
        'EEPROMCorrupt': (minorAlarms & 0x0400) >> 10,
        'AlmanacNotComplete': (minorAlarms & 0x0800) >> 11,
        'PPSNotGenerated': (minorAlarms & 0x1000) >> 12,
        'GPSDECODINGSTATUS': DEFAULTVALUE.format(GPSDecodingStatus),
        'DISCIPLININGACTIVITY': DEFAULTVALUE.format(discipliningActivity),
        'SPARESTATUS1': spareStatus1,
        'SPARESTATUS2': spareStatus2,
        'PPSOFFSET': PPSOffset,
        'CLOCKOFFSET': clockOffset,
        'DACVALUE': DACValue,
        'DACVOLTAGE': DACVoltage,
        'TEMPERATURE': temp,
        'LATITUDE': latitude,
        'LONGITUDE': longitude,
        'ALTITUDE': altitude,
        'PPSQUANTIZATIONERROR': PPSQuantizationError
    }
    if receiverMode in recModeValues:
        redis_set['RECEIVERMODE'] = recModeValues[receiverMode]
    if discipliningMode in disModeValues:
        redis_set['DISCIPLININGMODE'] = disModeValues[discipliningMode]
    if GPSDecodingStatus in GPSDecodeValues:
        redis_set['GPSDECODINGSTATUS'] = GPSDecodeValues[GPSDecodingStatus]
    if discipliningActivity in disActivityValues:
        redis_set['DISCIPLININGACTIVITY'] = disActivityValues[discipliningActivity]
    
    for key in redis_set.keys():
        r.hset(RKEYsupp, key, redis_set[key])
    
    lastTimeUpdated = False
    
    #print('ID = ', data[0:1])
    #print('ReceiverMode = ', receiverMode, ' bytes = ', data[1:2])
    #print('DiscipliningMode = ', discipliningMode, ' bytes = ', data[2:3])
    #print('Self-SurveyProgress = ', selfSurveyProgress, ' bytes = ', data[3:4])
    #print('Holdover Duration = ', holdOverDuration, ' bytes = ', data[4:8])
    #print('Critical Alarms = ', criticalAlarms, ' bytes = ', data[8:10])
    #print('Minor Alarms = ', minorAlarms, ' bytes = ', data[10:12])
    #print('GPS Decoding Status = ', GPSDecodingStatus, ' bytes = ', data[12:13])
    #print('Disciplining Activity = ', discipliningActivity, ' bytes = ', data[13:14])
    #print('Spare Status1 = ', spareStatus1, ' bytes = ', data[14:15])
    #print('Spare Status2 = ', spareStatus2, ' bytes = ', data[15:16])
    #print('PPSOffset = ', PPSOffset, ' bytes = ', data[16:20])
    #print('Clock Offset = ', clockOffset, ' bytes = ', data[20:24])
    #print('DAC Values = ', DACValue, ' bytes = ', data[24:28])
    #print('DAC Voltage = ', DACVoltage, ' bytes = ', data[28:32])
    #print('Temperature = ', temp, ' bytes = ', data[32:36])
    #print('Lat = ', latitude, ' Long = ', longitude, ' Altitude = ', altitude)
    #print('PPS Quantization Error = ', PPSQuantizationError, ' bytes = ', data[60:64])




# Reading the data from the serial port. This will be running in an infinite loop.

signal(SIGINT, handler)

def initialize():
    r = redis_init()

    # configure the serial connections (the parameters differs on the device you are connecting to)
    ser = serial.Serial(
        port=util.get_gps_port(config_file.get_obs_config()),
        baudrate=9600,
        timeout=None,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS
    )
    ser.isOpen()

    return ser, r


def main():
    data = b''
    data_size = 0
    last_recv_byte = 0

    ser, r = initialize()

    print('Running')
    while True:
        recv_byte = ser.read()
        if recv_byte == b'\x10' and last_recv_byte == b'\x10':
            pass
        else:
            data += recv_byte
            data_size += 1
        last_recv_byte = recv_byte
        if data[data_size - 1:data_size] == b'\x03' and data[data_size - 2:data_size - 1] == b'\x10':
            if data[0:1] == b'\x10':
                id = data[1:3]
                if id == b'\x8f\xab':
                    primaryTimingPacket(data[2:data_size - 2], r)
                elif id == b'\x8f\xac':
                    supplementaryTimingPacket(data[2:data_size - 2], r)
                else:
                    print('****fishy packet')
                    print(data[1:data_size - 2])
                    print(len(data[2:data_size - 2]))
            data = b''
            data_size = 0


if __name__ == "__main__":
    main()
