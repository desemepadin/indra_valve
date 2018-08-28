# indra_pi_valve

#### Irrigation valve controller written in Python for a Raspberry Pi

Designed to dynamically control drip line irrigation by connecting to a home LAN server via AWS IoT over a CDMA connection.

## Hardware

* Raspberry Pi 3
* Adafruit Fona
* 4 status LEDs (Red, yellow, green, and blue)
* 2 manual switches
* 2-wire normaly closed motorized ball valve
* Power distribution board

## Pinout
| GPIO Pin | Input / Output | Connected to...       |
| :------: | :------------: | :-------------------: |
| 17       | Input          | Manual switch         |
| 14       | Output         | Adafruit Fona Rx      |
| 15       | Input          | Adafruit Fona Tx      |
| 5        | Input          | Valve position switch |
| 18       | Output         | Red LED               |
| 20       | Output         | Valve control         |
| 23       | Output         | Yellow LED            |
| 24       | Output         | Green LED             |
| 25       | Output         | Blue LED              |

## AWS IoT

Must have an AWS account to use AWS IoT.  In order for the device to connect to AWS, the following values must be stored in a config file...

* MQTT_CA_CERT
* MQTT_CERTFILE
* MQTT_KEYFILE
* MQTT_HOST
* MQTT_PORT
* MQTT_KEEPALIVE

## CDMA
