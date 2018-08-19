import json
import logging
import time
import configparser
from paho import mqtt
from datetime import date

MANUAL = False
MQTTC = None
CONFIG_PATH = '/home/pi/indra_target/config.txt'
LAST_UPDATE = 0
WATERINGS = [[] for i in range(7)]
VALVE_OPEN = False
OPEN_TIME = 0

# TODO Add callback to handle toggle of hardware switch


def check_schedule():
    global MANUAL
    log.info('Checking schedule')
    # Get any waterings that wrap from previous day
    wrapped = []
    for watering in WATERINGS[get_day() - 1 if get_day() > 0 else 7]:
        if (watering[0] + int((watering[1] + watering[2]) / 60)) > 23:
            tmp_hour = watering[0] + int((watering[1] + watering[2]) / 60) - 24
            tmp_min = (watering[1] + watering[2]) % 60
            tmp_dur = watering[2] - (60 - watering[1]) - ((23 - watering[0]) * 60)
            wrapped.append(tmp_hour, tmp_min, tmp_dur)
    # Check waterings for current day
    for watering in wrapped + WATERINGS[get_day()]:
        curr_time = tuple(int(num) for num in time.strftime('%H:%M').split(':'))
        start_time = (watering[0], watering[1])
        finish_time = (watering[0] + int((watering[1] + watering[2]) / 60), (watering[1] + watering[2]) % 60)
        if start_time <= curr_time <= finish_time:
            # Remove manual mode if manual and schedule states align
            if VALVE_OPEN and MANUAL:
                MANUAL = False
            elif not VALVE_OPEN:
                valve(True)
    # No waterings are currently scheduled
    else:
        # Close valve if opened and not in manual
        if VALVE_OPEN and not MANUAL:
            valve(False)
        # Remove manual mode if states align
        elif not VALVE_OPEN and MANUAL:
            MANUAL = False


def valve(open_valve):
    global VALVE_OPEN
    log.info('{} valve'.format('Opening' if open_valve else 'Closing'))
    # TODO Change pin value to open or close valve, possibly publish status message
    VALVE_OPEN = open_valve


def on_disconnect(client, userdata, flags, rc):
    log.error('Device disconnected from AWS')
    # TODO Update LED


def on_connect(client, userdata, flags, rc):
    global MQTTC
    log.info('Connected/Reconnected to AWS')
    MQTTC.publish('indra/schedule_request',
                  payload=json.dump(LAST_UPDATE),
                  qos=2)
    # TODO Update LED


def on_schedule_receive(client, userdata, message):
    global LAST_UPDATE, WATERINGS
    log.info('Received watering schedule from AWS')
    WATERINGS = json.loads(message.payload.decode('UTF-8'))
    LAST_UPDATE = int(time.time())


def on_manual_receive(client, userdata, message):
    global MANUAL, OPEN_TIME
    command = json.loads(message.payload.decode('UTF-8'))['valve']
    if not VALVE_OPEN and command == 'open':
        log.info('Manually opening valve')
        MANUAL = True
        valve(True)
        OPEN_TIME = time.time()
    elif VALVE_OPEN and command == 'close':
        log.info('Manually closing valve')
        MANUAL = True
        valve(False)


def initialize_client():
    global MQTTC
    log.info('Initializing MQTT client')
    # Init MQTT client
    MQTTC = mqtt.Client()
    MQTTC.on_connect = on_connect
    MQTTC.on_disconnect = on_disconnect
    MQTTC.tls_set(ca_certs=config['MQTT_CA_CERT'],
                  certfile=config['MQTT_CERTFILE'],
                  keyfile=config['MQTT_KEYFILE'])
    MQTTC.connect(host=config['MQTT_HOST'],
                  port=config['MQTT_PORT'],
                  keepalive=config['MQTT_KEEPALIVE'])
    MQTTC.loop_start()

    # Subscribe to topic for receiving schedule
    MQTTC.subscribe('indra/schedule', 0)
    MQTTC.message_callback_add('indra/schedule', on_schedule_receive)

    # Subscribe to topic for manual commands
    MQTTC.subscribe('indra/manual', 0)
    MQTTC.message_callback_add('indra/manual', on_manual_receive)


def get_day():
    return date.isoweekday(date.today()) if date.isoweekday(date.today()) != 7 else 0


if __name__ == '__main__':
    # Create logging object
    log = logging()

    # Parse config file
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    # Initialize MQTT Client
    initialize_client()

    while True:
        if WATERINGS:
            check_schedule()
        if VALVE_OPEN and MANUAL and time.time() - OPEN_TIME > 30000:
            MANUAL = False
            valve(False)
        time.sleep(60)
