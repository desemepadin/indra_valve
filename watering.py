import json
import logging
import time
import configparser
from paho import mqtt
from datetime import date
from gpiozero import LEDBoard, Button, LED

MANUAL = False
MQTTC = None
CONFIG_PATH = '/home/pi/indra_target/config'
LAST_UPDATE = 0
WATERINGS = [[] for i in range(7)]
VALVE_OPEN = False
OPEN_TIME = 0
LEDS = LEDBoard(red=18, yellow=23, green=24, blue=25)
MANUAL_SWITCH = Button(12)
VALVE_SWITCH = Button(16)
VALVE = LED(20)


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
            # Watering is currently scheduled
            return True
    # No waterings are currently scheduled
    return False


def valve(open_valve):
    global VALVE_OPEN, OPEN_TIME
    log.info('{} valve'.format('Opening' if open_valve else 'Closing'))
    if open_valve:
        # Change pin value to open valve
        VALVE.on()
        # Turn on blue LED
        LEDS.blue.on()
        # Store time when valve was opened
        OPEN_TIME = time.time()
    else:
        # Change pin value to close valve
        VALVE.off()
        # Turn off blue LED
        LEDS.blue.off()
    VALVE_OPEN = open_valve


def on_disconnect(client, userdata, flags, rc):
    log.error('Device disconnected from AWS')
    # Denote that device is disconnected from AWS
    LEDS.green.off()
    # Indicate network is down if while loop below locks
    LEDS.yellow.off()
    while not check_connection():
        time.sleep(1)
    # Indicate that network is up
    LEDS.yellow.on()


def on_connect(client, userdata, flags, rc):
    global MQTTC
    log.info('Connected/Reconnected to AWS')
    MQTTC.publish('indra/schedule_request',
                  payload=json.dump(LAST_UPDATE),
                  qos=2)
    LEDS.green.on()


def on_schedule_receive(client, userdata, message):
    global LAST_UPDATE, WATERINGS
    log.info('Received watering schedule from AWS')
    payload = json.loads(message.payload.decode('UTF-8'))
    WATERINGS = payload['waterings']
    LAST_UPDATE = payload['timestamp']


def on_command(client, userdata, message):
    command = json.loads(message.payload.decode('UTF-8'))
    if command == 'status':
        # TODO Send status: Temp, valve, uptime, etc.
        print('Creating status')

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

    # Subscribe to topic for status queries
    MQTTC.subscribe('indra/status', 0)
    MQTTC.message_callback_add('indra/command', on_command)


def check_connection():
    # TODO Implement way to check if serial network interface is up
    time.sleep(1)


def get_day():
    return date.isoweekday(date.today()) if date.isoweekday(date.today()) != 7 else 0


if __name__ == '__main__':
    # Create logging object
    log = logging()

    # Parse config file
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    # Turn on Red LED to indicate successful startup
    LEDS.red.on()

    # Ensure 3G connection has been established
    while not check_connection():
        time.sleep(1)

    # Turn on Yellow LED to indicate network attachment
    LEDS.yellow.on()

    # Initialize MQTT Client
    initialize_client()

    while True:
        # Check manual switch and schedule
        valve(VALVE_SWITCH.is_pressed() if MANUAL_SWITCH.is_pressed() else check_schedule())
        # Sleep for 10 seconds
        time.sleep(10)
