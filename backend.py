import ctypes as C
import ctypes.util
import os
import pathlib, struct, re, sys
ROOT = pathlib.Path(getattr(sys, '_MEIPASS', pathlib.Path(__file__).resolve().parent))
P = C.c_void_p
U = C.c_uint
Z = C.c_size_t
I = C.c_int
UL = C.c_ulonglong
IV = [1779033703, 3144134277, 1013904242, 2773480762, 1359893119, 2600822924, 528734635, 1541459225]
K = [int(s, 16) for s in re.findall('0x[0-9a-f]+', (ROOT / 'sha256.cl').read_text())[:64]]

def rr(x, n):
    return (x >> n | x << 32 - n) & 4294967295

def compress(st, block):
    w = list(struct.unpack('>16I', block))
    a, b, c, d, e, f, g, h = st
    for i in range(64):
        if i >= 16:
            x, y = (w[i - 15], w[i - 2])
            w.append(w[i - 16] + (rr(x, 7) ^ rr(x, 18) ^ x >> 3) + w[i - 7] + (rr(y, 17) ^ rr(y, 19) ^ y >> 10) & 4294967295)
        t1 = h + (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25)) + (e & f ^ ~e & g) + K[i] + w[i] & 4294967295
        t2 = (rr(a, 2) ^ rr(a, 13) ^ rr(a, 22)) + (a & b ^ a & c ^ b & c) & 4294967295
        a, b, c, d, e, f, g, h = (t1 + t2 & 4294967295, a, b, c, d + t1 & 4294967295, e, f, g)
    return [x + y & 4294967295 for x, y in zip(st, (a, b, c, d, e, f, g, h))]

class OpenCL:

    def __init__(self, source=None, device=0):
        self.cl = load_opencl()
        signatures = {'clGetPlatformIDs': ([U, P, P], I), 'clGetDeviceIDs': ([P, UL, U, P, P], I), 'clGetDeviceInfo': ([P, U, Z, P, P], I), 'clCreateContext': ([P, U, P, P, P, P], P), 'clCreateCommandQueue': ([P, P, UL, P], P), 'clCreateBuffer': ([P, UL, Z, P, P], P), 'clCreateProgramWithSource': ([P, U, P, P, P], P), 'clBuildProgram': ([P, U, P, C.c_char_p, P, P], I), 'clGetProgramBuildInfo': ([P, P, U, Z, P, P], I), 'clCreateKernel': ([P, C.c_char_p, P], P), 'clSetKernelArg': ([P, U, Z, P], I), 'clEnqueueWriteBuffer': ([P, P, U, Z, Z, P, U, P, P], I), 'clEnqueueReadBuffer': ([P, P, U, Z, Z, P, U, P, P], I), 'clEnqueueNDRangeKernel': ([P, P, U, P, P, P, U, P, P], I), 'clFinish': ([P], I), 'clReleaseMemObject': ([P], I), 'clReleaseKernel': ([P], I), 'clReleaseProgram': ([P], I), 'clReleaseCommandQueue': ([P], I), 'clReleaseContext': ([P], I)}
        for name, (args, result) in signatures.items():
            fn = getattr(self.cl, name)
            fn.argtypes = args
            fn.restype = result
        count = U()
        self.check(self.cl.clGetPlatformIDs(0, None, C.byref(count)))
        platforms = (P * count.value)()
        self.check(self.cl.clGetPlatformIDs(count, platforms, None))
        available = []
        for platform in platforms:
            n = U()
            if self.cl.clGetDeviceIDs(platform, 4, 0, None, C.byref(n)):
                continue
            devs = (P * n.value)()
            self.check(self.cl.clGetDeviceIDs(platform, 4, n, devs, None))
            available.extend(devs)
        if not 0 <= device < len(available):
            raise RuntimeError('OpenCL device is unavailable')
        self.device = available[device]
        name = C.create_string_buffer(512)
        self.check(self.cl.clGetDeviceInfo(self.device, 4139, 512, name, None))
        self.name = name.value.decode(errors='replace')
        maximum = Z()
        self.check(self.cl.clGetDeviceInfo(self.device, 4100, C.sizeof(maximum), C.byref(maximum), None))
        self.max_workgroup = maximum.value
        err = I()
        dev = P(self.device)
        self.context = self.cl.clCreateContext(None, 1, C.byref(dev), None, None, C.byref(err))
        self.check(err.value)
        self.queue = self.cl.clCreateCommandQueue(self.context, self.device, 0, C.byref(err))
        self.check(err.value)
        source = (ROOT / 'sha256.cl').read_bytes() if source is None else source.encode()
        sources = (C.c_char_p * 1)(source)
        self.program = self.cl.clCreateProgramWithSource(self.context, 1, sources, None, C.byref(err))
        self.check(err.value)
        result = self.cl.clBuildProgram(self.program, 1, C.byref(dev), b'-cl-std=CL1.2', None, None)
        if result:
            log = C.create_string_buffer(65536)
            self.cl.clGetProgramBuildInfo(self.program, self.device, 4483, len(log), log, None)
            raise RuntimeError(log.value.decode(errors='replace'))
        self.search_kernel = self.cl.clCreateKernel(self.program, b'search', C.byref(err))
        self.check(err.value)
        self.test_kernel = self.cl.clCreateKernel(self.program, b'test', C.byref(err))
        self.check(err.value)
        self.buffers = []
        for size in (65536, 32, 4, 512, 4096 * 32):
            mem = self.cl.clCreateBuffer(self.context, 1, size, None, C.byref(err))
            self.check(err.value)
            self.buffers.append(mem)
        self.cached = None
        self.cached_target = None
        self.zero_count = C.c_uint(0)
        for i, v in ((0, P(self.buffers[0])), (2, P(self.buffers[1])), (3, P(self.buffers[2])), (4, P(self.buffers[3])), (5, U(64))):
            self.arg(self.search_kernel, i, v)
        self.arg(self.test_kernel, 0, P(self.buffers[0]))
        self.arg(self.test_kernel, 2, P(self.buffers[4]))

    @staticmethod
    def check(code):
        if code:
            raise RuntimeError('OpenCL error ' + str(code))

    def arg(self, kernel, index, value):
        self.check(self.cl.clSetKernelArg(kernel, index, C.sizeof(value), C.byref(value)))

    def write(self, index, data):
        self.check(self.cl.clEnqueueWriteBuffer(self.queue, self.buffers[index], 1, 0, len(data), data, 0, None, None))

    def read(self, index, size):
        result = C.create_string_buffer(size)
        self.check(self.cl.clEnqueueReadBuffer(self.queue, self.buffers[index], 1, 0, size, result, 0, None, None))
        return result.raw

    def job(self, head, tail, base, count):
        digits = len(str(base))
        if len(str(base + count - 1)) != digits:
            raise ValueError('batch crosses decimal nonce width')
        key = (head, tail, digits)
        if key == self.cached:
            return
        fixed = len(head) // 64 * 64
        st = IV.copy()
        for n in range(0, fixed, 64):
            st = compress(st, head[n:n + 64])
        remaining = head[fixed:] + b'0' * digits + tail
        full_len = fixed + len(remaining)
        remaining += b'\x80'
        remaining += b'\x00' * ((56 - len(remaining)) % 64)
        remaining += (full_len * 8).to_bytes(8, 'big')
        words = st + [len(head) - fixed, digits, len(remaining) // 64, 0]
        for block in range(0, len(remaining), 64):
            w = list(struct.unpack('>16I', remaining[block:block + 64]))
            for i in range(16, 64):
                x, y = (w[i - 15], w[i - 2])
                w.append(w[i - 16] + (rr(x, 7) ^ rr(x, 18) ^ x >> 3) + w[i - 7] + (rr(y, 17) ^ rr(y, 19) ^ y >> 10) & 4294967295)
            offset = len(head) - fixed
            if block + 64 <= offset or block >= offset + digits:
                w = [value + K[i] & 4294967295 for i, value in enumerate(w)]
            words += w
        if words[9] == 13 and (words[8] == 40 and words[10] == 1 or (words[8] in (42, 43) and words[10] in (5, 6, 7, 8))):
            a, b, c, d, e, f, g, h = st
            for i in range(10):
                t1 = h + (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25)) + (e & f ^ ~e & g) + K[i] + words[12 + i] & 4294967295
                t2 = (rr(a, 2) ^ rr(a, 13) ^ rr(a, 22)) + (a & b ^ a & c ^ b & c) & 4294967295
                a, b, c, d, e, f, g, h = (t1 + t2 & 4294967295, a, b, c, d + t1 & 4294967295, e, f, g)
            words += [a, b, c, d, e, f, g, h]
        data = struct.pack('<' + 'I' * len(words), *words)
        if len(data) > 65536:
            raise ValueError('LBTC task exceeds GPU constant memory')
        self.write(0, data)
        self.cached = key

    def dispatch(self, kernel, count, worksize):
        if worksize > self.max_workgroup:
            raise ValueError('Workgroup exceeds device limit')
        gs = Z(count)
        ls = Z(worksize)
        self.check(self.cl.clEnqueueNDRangeKernel(self.queue, kernel, 1, None, C.byref(gs), C.byref(ls), 0, None, None))

    def search(self, head, tail, base, count, target, worksize=128):
        self.job(head, tail, base, count)
        if target != self.cached_target:
            self.write(1, struct.pack('<8I', *struct.unpack('>8I', target.to_bytes(32, 'big'))))
            self.cached_target = target
        self.check(self.cl.clEnqueueWriteBuffer(self.queue, self.buffers[2], 0, 0, 4, C.byref(self.zero_count), 0, None, None))
        self.arg(self.search_kernel, 1, UL(base))
        self.dispatch(self.search_kernel, count, worksize if count % worksize == 0 else 1)
        found = struct.unpack('<I', self.read(2, 4))[0]
        if found > 64:
            raise RuntimeError('Result buffer full: use smaller nonce batch')
        return list(struct.unpack('<' + 'Q' * found, self.read(3, found * 8))) if found else []

    def hashes(self, head, tail, base, count=1):
        if count > 4096:
            raise ValueError('test buffer capacity')
        self.job(head, tail, base, count)
        self.arg(self.test_kernel, 1, UL(base))
        self.dispatch(self.test_kernel, count, 1)
        words = struct.unpack('<' + 'I' * (count * 8), self.read(4, count * 32))
        return [struct.pack('>8I', *words[n * 8:n * 8 + 8]) for n in range(count)]

    def close(self):
        for buffer in self.buffers:
            self.cl.clReleaseMemObject(buffer)
        for obj, fn in ((self.search_kernel, 'clReleaseKernel'), (self.test_kernel, 'clReleaseKernel'), (self.program, 'clReleaseProgram'), (self.queue, 'clReleaseCommandQueue'), (self.context, 'clReleaseContext')):
            getattr(self.cl, fn)(obj)

def load_opencl():
    if os.name == 'nt':
        return C.WinDLL('OpenCL.dll')
    return C.CDLL(ctypes.util.find_library('OpenCL') or ('/System/Library/Frameworks/OpenCL.framework/OpenCL' if sys.platform == 'darwin' else 'libOpenCL.so.1'))

def list_devices():
    try:
        cl = load_opencl()
    except OSError:
        return []
    cl.clGetPlatformIDs.argtypes = [U, P, P]
    cl.clGetDeviceIDs.argtypes = [P, UL, U, P, P]
    cl.clGetDeviceInfo.argtypes = [P, U, Z, P, P]
    n = U()
    if cl.clGetPlatformIDs(0, None, C.byref(n)):
        return []
    platforms = (P * n.value)()
    cl.clGetPlatformIDs(n, platforms, None)
    result = []
    for platform in platforms:
        count = U()
        if cl.clGetDeviceIDs(platform, 4, 0, None, C.byref(count)):
            continue
        devs = (P * count.value)()
        cl.clGetDeviceIDs(platform, 4, count, devs, None)
        for dev in devs:
            row = {'id': len(result), 'backend': 'OpenCL'}
            for key, param in [('name', 4139), ('vendor', 4140), ('driver', 4141)]:
                text = C.create_string_buffer(512)
                cl.clGetDeviceInfo(dev, param, 512, text, None)
                row[key] = text.value.decode(errors='replace')
            maximum = Z()
            cl.clGetDeviceInfo(dev, 4100, C.sizeof(maximum), C.byref(maximum), None)
            row['max_workgroup'] = maximum.value
            pci = (U * 4)()
            if cl.clGetDeviceInfo(dev, 16655, C.sizeof(pci), pci, None) == 0:
                row['pci'] = '%04x:%02x:%02x.%x' % tuple(pci)
            elif 'NVIDIA' in row['vendor'].upper():
                bus = U()
                slot = U()
                if cl.clGetDeviceInfo(dev, 16392, 4, C.byref(bus), None) == 0 and cl.clGetDeviceInfo(dev, 16393, 4, C.byref(slot), None) == 0:
                    row['pci'] = '0000:%02x:%02x.%x' % (bus.value, slot.value >> 3, slot.value & 7)
            elif 'AMD' in row['vendor'].upper() or 'ADVANCED MICRO' in row['vendor'].upper():
                topology = C.create_string_buffer(24)
                if cl.clGetDeviceInfo(dev, 16439, 24, topology, None) == 0 and struct.unpack_from('<I', topology.raw)[0] == 1:
                    row['pci'] = '0000:%02x:%02x.%x' % tuple(topology.raw[21:24])
            result.append(row)
    return result
