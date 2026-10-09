use crate::telemetry::Reading;
use libloading::Library;
use std::ffi::{CString,c_void};
type Handle=*mut c_void;
type Initialize=unsafe extern "C" fn()->i32;
type Shutdown=unsafe extern "C" fn()->i32;
type GetDevice=unsafe extern "C" fn(*const i8,*mut Handle)->i32;
type Query=unsafe extern "C" fn(Handle,*mut u32)->i32;
type Selector=unsafe extern "C" fn(Handle,u32,*mut u32)->i32;
#[repr(C)] struct Utilization {gpu:u32,memory:u32}
type GetUtilization=unsafe extern "C" fn(Handle,*mut Utilization)->i32;
pub struct Telemetry{_lib:Library,handle:Handle,shutdown:Shutdown,power:Query,fan:Query,temperature:Selector,clock:Selector,utilization:GetUtilization}
impl Telemetry {
    pub fn new(pci:&str)->Option<Self>{unsafe{Self::load(pci).ok()}}
    unsafe fn load(pci:&str)->Result<Self,String>{
        #[cfg(windows)] let candidates=["nvml.dll","C:\\Windows\\System32\\nvml.dll"];
        #[cfg(not(windows))] let candidates=["libnvidia-ml.so.1","libnvidia-ml.so"];
        let lib=candidates.iter().find_map(|p|Library::new(p).ok()).ok_or("NVML library unavailable")?;
        let initialize=*lib.get::<Initialize>(b"nvmlInit_v2\0").map_err(|e|e.to_string())?;
        let shutdown=*lib.get::<Shutdown>(b"nvmlShutdown\0").map_err(|e|e.to_string())?;
        let get_device=*lib.get::<GetDevice>(b"nvmlDeviceGetHandleByPciBusId_v2\0").map_err(|e|e.to_string())?;
        let power=*lib.get::<Query>(b"nvmlDeviceGetPowerUsage\0").map_err(|e|e.to_string())?;
        let fan=*lib.get::<Query>(b"nvmlDeviceGetFanSpeed\0").map_err(|e|e.to_string())?;
        let temperature=*lib.get::<Selector>(b"nvmlDeviceGetTemperature\0").map_err(|e|e.to_string())?;
        let clock=*lib.get::<Selector>(b"nvmlDeviceGetClockInfo\0").map_err(|e|e.to_string())?;
        let utilization=*lib.get::<GetUtilization>(b"nvmlDeviceGetUtilizationRates\0").map_err(|e|e.to_string())?;
        let pci=CString::new(pci).map_err(|e|e.to_string())?;
        if initialize()!=0{return Err("NVML initialization failed".into());}
        let mut handle=std::ptr::null_mut();
        if get_device(pci.as_ptr(),&mut handle)!=0||handle.is_null(){shutdown();return Err("Matching NVML PCI device unavailable".into());}
        Ok(Self{_lib:lib,handle,shutdown,power,fan,temperature,clock,utilization})
    }
    pub fn read(&self)->Reading{unsafe{
        let query=|f:Query|{let mut value=0;if f(self.handle,&mut value)==0{Some(value)}else{None}};
        let selector=|f:Selector,kind:u32|{let mut value=0;if f(self.handle,kind,&mut value)==0{Some(value)}else{None}};
        let mut utilization=Utilization{gpu:0,memory:0};
        Reading{power:query(self.power).map(|v|f64::from(v)/1000.),temperature:selector(self.temperature,0).map(|v|v as i32),utilization:if (self.utilization)(self.handle,&mut utilization)==0{Some(utilization.gpu as i32)}else{None},hotspot:None,fan_percent:query(self.fan).map(|v|v as i32),core_clock:selector(self.clock,0).map(|v|v as i32),memory_clock:selector(self.clock,2).map(|v|v as i32)}
    }}
}
impl Drop for Telemetry{fn drop(&mut self){unsafe{(self.shutdown)();}}}
