import time

class DispatchPacer:

    def __init__(self, intensity, clock=time.monotonic):
        self.debt = 0.0
        self.clock = clock
        self.intensity = None
        self.set_intensity(intensity)

    def set_intensity(self, intensity):
        if type(intensity) is not int or not 1 <= intensity <= 100:
            raise ValueError('Invalid intensity')
        if self.intensity != intensity:
            self.debt = 0.0
        self.intensity = intensity
        self.ratio = (100 - intensity) / intensity

    def after_dispatch(self, seconds, stop):
        self.debt += max(0.0, seconds) * self.ratio
        if self.debt < 0.02:
            return
        started = self.clock()
        stop.wait(min(0.05, self.debt))
        self.debt -= max(0.0, self.clock() - started)

class DeadlineBoost:

    def __init__(self, base):
        self.base = base
        self.active = False

    def select(self, enabled, remaining, gpu, max_power):
        values = [gpu.get(k) for k in ('hotspot_c', 'temperature_c', 'asic_power_w')]
        import math
        valid = all((isinstance(v, (int, float)) and math.isfinite(v) for v in values))
        if not enabled or self.base >= 100 or remaining > 180 or (not valid):
            self.active = False
            return self.base
        hotspot, temperature, power = values
        safe = hotspot < 75 and temperature < 70 and (power < max_power) if self.active else hotspot <= 70 and temperature <= 65 and (power < max_power * 0.9)
        self.active = bool(safe)
        return 100 if self.active else self.base
