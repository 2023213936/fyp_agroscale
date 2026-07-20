import time
import sys
import RPi.GPIO as GPIO
from hx711 import HX711

hx = HX711(5,6)
hx.set_reading_format("MSB","MSB")
hx.set_reference_unit(390.78)
hx.reset()
hx.tare()

ZERO_THRESHOLD = 2.0

print("Scale ready!")
print("press ctrl+c")

try:
	while True:
		weight = hx.get_weight(3)

		if abs(weight) < ZERO_THRESHOLD:
			weight = 0.0

		print(f"\rWeight: {weight:.1f}g", end="", flush=True)

		hx.power_down()
		hx.power_up()
		time.sleep(0.5)

except KeyboardInterrupt:
	print("\nExiting..")
	GPIO.cleanup()
