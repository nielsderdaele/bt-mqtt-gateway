import time
from interruptingcow import timeout

from exceptions import DeviceTimeoutError
from mqtt import MqttMessage
from workers.base import BaseWorker
import logger

REQUIREMENTS = ["bluepy"]

_LOGGER = logger.get(__name__)
# Bluepy might need special settings
# sudo setcap 'cap_net_raw,cap_net_admin+eip' /usr/local/lib/python3.6/dist-packages/bluepy/bluepy-helper


class Miscale2Worker(BaseWorker):
    def run(self, mqtt):
        from bluepy import btle

        weight_topic = self.format_topic("weight/kg")
        impedance_topic = self.format_topic("impedance")

        scan_processor = MiScale2ToMQTTScanProcessor(self.mac, mqtt, weight_topic, impedance_topic)
        scanner = btle.Scanner().withDelegate(scan_processor)
        scanner.start(passive=True)

        while True:
            scanner.process()
            
class MiScale2ToMQTTScanProcessor:
    def __init__(self, mac, mqtt, weightTopic, impedanceTopic):
        self._mac = mac
        self._mqtt = mqtt
        self._weightTopic = weightTopic
        self._impedanceTopic = impedanceTopic

    def handleDiscovery(self, dev, isNewDev, isNewData):
        #1b1802a4e3070a0d0f1f31fdffcc3d
        if dev.addr == self.mac.lower() and isNewData:
            for (sdid, desc, data) in dev.getScanData():
                if data.startswith("1b18") and sdid == 22:
                    _LOGGER.debug("Received data (sdid=%s): %s", sdid, data)
                    #control_byte_0 = int(data[4:6], 16)
                    control_byte_1 = int(data[6:8], 16)
                    stabilized = (control_byte_1 & 0b0100000) == 0b0100000
                    weightRemoved = (control_byte_1 & 0b10000000) == 0b10000000
                    hasImpedance = (control_byte_1 & 0b00000010) == 0b00000010
                    # TODO check weight unit => if kg divide by 200, otherwise device by 100

                    _LOGGER.debug("Control byte: %d, stabilized: %s, weightRemoved: %s, hasImpedance: %s", control_byte_1, stabilized, weightRemoved, hasImpedance)
                    if stabilized and not weightRemoved:
                        _LOGGER.debug("Stabilized data received")
                        measuredWeight = int((data[28:30] + data[26:28]), 16)
                        self.publishWeight(round(measuredWeight / 200, 2))
                        if hasImpedance: 
                            self.publishImpedance(int((data[24:26] + data[22:24]), 16))
                    
    @property
    def mac(self):
        return self._mac

    def publishWeight(self, weight):
        _LOGGER.debug("publishing weight to %s: %d", self._weightTopic, weight)
        self._mqtt.publish([MqttMessage(topic=self._weightTopic, payload=weight)])

    def publishImpedance(self, impedance):
        _LOGGER.debug("publishing impedance to %s: %d", self._impedanceTopic, impedance)
        self._mqtt.publish([MqttMessage(topic=self._impedanceTopic, payload=impedance)])
