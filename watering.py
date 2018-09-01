import json
import logging
import time
import configparser
from urllib import request
import os
import re
import paho.mqtt.client as mqtt
from datetime import date
from gpiozero import LEDBoard, Button, LED

MANUAL = False
MQTTC = None
CONFIG_PATH = '/home/pi/config'
LAST_UPDATE = 0
WATERINGS = [[] for i in range(7)]
VALVE_OPEN = False
OPEN_TIME = 0
LEDS = LEDBoard(red=18, yellow=23, green=24, blue=25)
MANUAL_SWITCH = Button(17)
VALVE_SWITCH = Button(5)
VALVE = LED(20)


def check_schedule():
    """
    Checks watering schedule
    :return: True if watering is currently scheduled, False otherwise
    """
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
    """
    Opens or closes valve
    :param open_valve: True to open valve, False to close valve
    """
    global VALVE_OPEN, OPEN_TIME
    log.info('{} valve'.format('Opening' if open_valve else 'Closing'))
    if open_valve:
        # Open valve
        VALVE.on()
        # Turn on blue LED
        LEDS.blue.on()
        # Store time when valve was opened
        OPEN_TIME = time.time()
    else:
        # Close valve
        VALVE.off()
        # Turn off blue LED
        LEDS.blue.off()
    VALVE_OPEN = open_valve


def on_disconnect(client, userdata, flags, rc):
    """
    Device disconnected from AWS, update LEDs and check for CDMA connection
    """
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
    """
    Device just connected, request new schedule
    """
    log.info('Connected/Reconnected to AWS')
    p = {'timestamp': LAST_UPDATE}
    MQTTC.publish('indra/schedule_request',
                  payload=json.dumps(p),
                  qos=1)
    LEDS.green.on()


def on_schedule_receive(client, userdata, message):
    """
    Parse and load schedule
    """
    global LAST_UPDATE, WATERINGS
    log.info('Received watering schedule from AWS')
    payload = json.loads(message.payload.decode('UTF-8'))
    WATERINGS = payload['waterings']
    LAST_UPDATE = payload['timestamp']


def on_command(client, userdata, message):
    """
    Respond to command sent to device
    """
    command = json.loads(message.payload.decode('UTF-8'))
    if command == 'status':
        # Get system uptime and load
        uptime, load = get_system_uptime_and_load()
        # Create status object
        status = {'temp': get_cpu_temp(),
                  'valve': 'open' if VALVE_OPEN else 'closed',
                  'load': load,
                  'uptime': uptime,
                  'voltage': get_cpu_voltage(),
                  'speed': get_cpu_speed()}
        # Send status object
        MQTTC.publish('indra/status',
                      payload=status,
                      qos=1)


def get_system_uptime_and_load():
    """
    Gets both system uptime and percent load over past 15 minutes using same call
    :return: Tuple of uptime and load stored as strings
    """
    output = os.popen('uptime').read().replace('\n', '')
    days, hour_min = re.search(r'up ([0-9]+) days,[ ]+([0-9]+:[0-9]+)', output).group(1, 2)
    hours, minutes = hour_min.split(':')
    uptime = '{0} days, {1} hours, {2} minutes'.format(days, hours, minutes)
    *_, load = re.search(r'load average: ([0-9]+.[0-9]+),[ ]+([0-9]+.[0-9]+),[ ]+([0-9]+.[0-9]+)',
                         output).group(1, 2, 3)
    return uptime, load


def get_cpu_temp():
    """
    Gets temperature of CPU
    :return: Temperature in degrees fahrenheit
    """
    temp = float(os.popen('vcgencmd measure_temp'.readline()).read().replace('\'C\n', '')[5:])
    # Convert celsius to fahrenheit
    return (temp * (9 / 5)) + 32


def get_cpu_voltage():
    """
    Gets voltage of CPU
    :return: Voltage of CPU
    """
    values = os.popen('vcgencmd pm_get_status').read().replace('\n', '').split()
    return float(values[2][8:].replace('v', ''))


def get_cpu_speed():
    """
    Gets targeted speed of CPU
    :return: Speed of CPU in Hz
    """
    values = os.popen('vcgencmd pm_get_status').read().replace('\n', '').split()
    return int(values[0][5:])


def initialize_client():
    """
    Initializes the MQTT client
    :return: None
    """
    global MQTTC
    log.info('Initializing MQTT client')

    # Init MQTT client
    MQTTC = mqtt.Client()
    MQTTC.on_connect = on_connect
    MQTTC.on_disconnect = on_disconnect
    MQTTC.tls_set(ca_certs=config['DEFAULT']['MQTT_CA_CERT'],
                  certfile=config['DEFAULT']['MQTT_CERTFILE'],
                  keyfile=config['DEFAULT']['MQTT_KEYFILE'])
    MQTTC.connect(host=config['DEFAULT']['MQTT_HOST'],
                  port=int(config['DEFAULT']['MQTT_PORT']),
                  keepalive=int(config['DEFAULT']['MQTT_KEEPALIVE']))
    MQTTC.loop_start()

    # Subscribe to topic for receiving schedule
    MQTTC.subscribe('indra/schedule', 0)
    MQTTC.message_callback_add('indra/schedule', on_schedule_receive)

    # Subscribe to topic for status queries
    MQTTC.subscribe('indra/command', 0)
    MQTTC.message_callback_add('indra/command', on_command)


def check_connection():
    """
    Ensures network interface is connected to the web
    :return: True if device is connected, else False
    """
    try:
        request.urlopen('http://1.1.1.1', timeout=5)
        return True
    except request.URLError:
        return False


def get_day():
    """
    Gets day of week as an integer value to use for week calendar list
    :return: 0 for Sunday, 1 for Monday, ... , 7 for Saturday
    """
    return date.isoweekday(date.today()) if date.isoweekday(date.today()) != 7 else 0


if __name__ == '__main__':
    # Create logging object
    log = logging
    log.basicConfig(filename='/tmp/watering.log', level=logging.ERROR)

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
        if MANUAL_SWITCH.is_pressed:
            valve(VALVE_SWITCH.is_pressed)
        else:
            check_schedule()
        # Sleep for 10 seconds
        time.sleep(10)
