import ctypes as c, threading

class Adapter(c.Structure):
    _fields_ = [('size', c.c_int), ('index', c.c_int), ('udid', c.c_char * 256), ('bus', c.c_int), ('device', c.c_int), ('function', c.c_int), ('vendor', c.c_int), ('name', c.c_char * 256), ('display', c.c_char * 256), ('present', c.c_int), ('exist', c.c_int), ('driver', c.c_char * 256), ('driver_ext', c.c_char * 256), ('pnp', c.c_char * 256), ('os_index', c.c_int)]

class Sensor(c.Structure):
    _fields_ = [('supported', c.c_int), ('value', c.c_int)]

class Metrics(c.Structure):
    _fields_ = [('size', c.c_int), ('sensors', Sensor * 256)]

class ADL:

    def __init__(self):
        self.lock = threading.Lock()
        self.dll = c.CDLL('atiadlxx.dll')
        self.context = c.c_void_p()
        crt = c.CDLL('msvcrt.dll')
        crt.malloc.argtypes = [c.c_size_t]
        crt.malloc.restype = c.c_void_p
        self.callback = c.WINFUNCTYPE(c.c_void_p, c.c_int)(lambda n: crt.malloc(n))
        self.dll.ADL2_Main_Control_Create.argtypes = [type(self.callback), c.c_int, c.POINTER(c.c_void_p)]
        self.dll.ADL2_Adapter_NumberOfAdapters_Get.argtypes = [c.c_void_p, c.POINTER(c.c_int)]
        self.dll.ADL2_Adapter_AdapterInfo_Get.argtypes = [c.c_void_p, c.POINTER(Adapter), c.c_int]
        self.dll.ADL2_New_QueryPMLogData_Get.argtypes = [c.c_void_p, c.c_int, c.POINTER(Metrics)]
        if self.dll.ADL2_Main_Control_Create(self.callback, 1, c.byref(self.context)):
            raise RuntimeError('ADL unavailable')
        count = c.c_int()
        self.dll.ADL2_Adapter_NumberOfAdapters_Get(self.context, c.byref(count))
        if not 0 < count.value <= 128:
            raise RuntimeError('Invalid ADL adapter list')
        adapters = (Adapter * count.value)()
        for a in adapters:
            a.size = c.sizeof(Adapter)
        if self.dll.ADL2_Adapter_AdapterInfo_Get(self.context, adapters, c.sizeof(adapters)):
            raise RuntimeError('ADL enumeration failed')
        self.adapters = {}
        for a in adapters:
            if a.present and a.bus >= 0:
                self.adapters.setdefault('0000:%02x:%02x.%x' % (a.bus, a.device, a.function), a.index)

    def read(self, pci):
        with self.lock:
            index = self.adapters.get(pci)
            if index is None:
                return {}
            metrics = Metrics()
            metrics.size = c.sizeof(metrics)
            if self.dll.ADL2_New_QueryPMLogData_Get(self.context, index, c.byref(metrics)):
                return {}

            def v(i):
                return metrics.sensors[i].value if metrics.sensors[i].supported else None
            return {'temperature_c': v(8), 'hotspot_c': v(27), 'utilization_percent': v(19), 'power_w': v(23), 'core_mhz': v(1), 'memory_mhz': v(2), 'fan_rpm': v(14), 'fan_percent': v(15), 'adl_index': index}
