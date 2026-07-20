import time
from hx711py.hx711 import HX711

hx = HX711(5, 6)
hx.set_reading_format("MSB", "MSB")

hx.set_reference_unit(400.80)

hx.reset()
hx.tare()

def get_weight():
	try:
		weight = hx.get_weight(5)

		hx.power_down()
		hx.power_up()
		time.sleep(0.1)

		if weight < 0:
			weight = 0

		return round(weight / 1000, 2)

	except:
		return 0
